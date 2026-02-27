"""
ARQ Worker for The-Spark-Pit

Background worker that processes audit events, indexes activity feed,
and handles background jobs using ARQ (Async Redis Queue).
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional
from pathlib import Path

import redis.asyncio as redis
from arq.connections import RedisSettings
from arq.connections import RedisSettings
from pydantic import BaseModel, Field

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")


# Data Models
class AuditEvent(BaseModel):
    """Audit event model for tracking system activities."""
    id: str = Field(default_factory=lambda: f"audit_{datetime.utcnow().isoformat()}")
    event_type: str
    user_id: Optional[str] = None
    action: str
    resource: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    severity: str = "info"  # info, warning, error, critical


class ActivityFeedItem(BaseModel):
    """Activity feed item for indexing."""
    id: str = Field(default_factory=lambda: f"activity_{datetime.utcnow().isoformat()}")
    event_type: str
    user_id: Optional[str] = None
    description: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class WorkerSettings:
    functions = ["backend.worker.process_audit_event", "backend.worker.index_activity_feed", "backend.worker.cleanup_old_data", "backend.worker.handle_background_job"]
    """ARQ worker settings."""
    redis_settings = RedisSettings.from_dsn(REDIS_URL)
    max_jobs = 100
    keep_results = 3600  # Keep results for 1 hour
    job_timeout = 300  # 5 minute timeout
    loop = asyncio.get_event_loop()


# Worker Functions (called by ARQ)
async def process_audit_event(ctx, event_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process an audit event.
    
    Args:
        ctx: ARQ context containing redis connection
        event_data: Audit event data dictionary
    
    Returns:
        Processing result
    """
    redis_conn = ctx["redis"]
    
    try:
        # Validate and parse audit event
        audit_event = AuditEvent(**event_data)
        
        logger.info(f"Processing audit event: {audit_event.event_type} - {audit_event.action}")
        
        # Store audit event in Redis
        audit_key = f"tsp:audits:{audit_event.id}"
        await redis_conn.set(
            audit_key,
            audit_event.model_dump_json(),
            ex=86400 * 7  # 7 day TTL
        )
        
        # Add to audit log list (sorted set by timestamp)
        audit_log_key = "tsp:audit_log"
        await redis_conn.zadd(
            audit_log_key,
            {audit_event.id: audit_event.timestamp.timestamp()}
        )
        
        # Index for activity feed if applicable
        if audit_event.event_type in ["user_action", "system_event", "data_access"]:
            activity_key = f"tsp:activity:{audit_event.user_id or 'system'}"
            activity_item = ActivityFeedItem(
                event_type=audit_event.event_type,
                user_id=audit_event.user_id,
                description=f"{audit_event.action} on {audit_event.resource or 'unknown'}",
                metadata=audit_event.metadata
            )
            await redis_conn.lpush(
                activity_key,
                activity_item.model_dump_json()
            )
            # Trim to last 100 items
            await redis_conn.ltrim(activity_key, 0, 99)
            
            # Also add to global activity feed
            global_activity_key = "tsp:activity:global"
            await redis_conn.zadd(
                global_activity_key,
                {activity_item.id: activity_item.created_at.timestamp()}
            )
            # Keep last 1000 global activities
            await redis_conn.zremrangebyrank(global_activity_key, 0, -1001)
        
        # Trigger any registered webhooks or notifications
        await trigger_audit_notifications(ctx, audit_event)
        
        logger.info(f"Successfully processed audit event: {audit_event.id}")
        return {
            "success": True,
            "event_id": audit_event.id,
            "processed_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to process audit event: {e}")
        return {
            "success": False,
            "error": str(e),
            "event_id": event_data.get("id", "unknown")
        }


async def index_activity_feed(ctx, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Index activity feed for a user or globally.
    """
    redis_conn = ctx["redis"]

    try:
        if user_id:
            activity_key = f"tsp:activity:{user_id}"
            activities = await redis_conn.lrange(activity_key, 0, 99)

            index_key = f"tsp:activity_index:{user_id}"
            await redis_conn.delete(index_key)

            for activity_json in activities:
                activity = json.loads(activity_json)
                await redis_conn.zadd(
                    index_key,
                    {activity["id"]: activity["created_at"].timestamp()}
                )

            count = len(activities)
            logger.info(f"Indexed {count} activities for user {user_id}")

            return {
                "success": True,
                "scope": "user",
                "user_id": user_id,
                "indexed_count": count,
                "indexed_at": datetime.utcnow().isoformat()
            }

        global_activity_key = "tsp:activity:global"
        activities = await redis_conn.zrange(
            global_activity_key, 0, 999, withscores=True
        )

        index_key = "tsp:activity_index:global"
        await redis_conn.delete(index_key)

        for activity_id, score in activities:
            await redis_conn.zadd(index_key, {activity_id: score})

        count = len(activities)
        logger.info(f"Indexed {count} activities for global feed")

        return {
            "success": True,
            "scope": "global",
            "indexed_count": count,
            "indexed_at": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to index activity feed: {e}")
        return {"success": False, "error": str(e)}
async def cleanup_old_data(ctx, retention_days: int = 30) -> Dict[str, Any]:
    """
    Clean up old audit logs and activity data.
    
    Args:
        ctx: ARQ context
        retention_days: How many days of data to keep
    
    Returns:
        Cleanup result with deleted count
    """
    redis_conn = ctx["redis"]
    cutoff_timestamp = (datetime.utcnow() - timedelta(days=retention_days)).timestamp()
    
    try:
        # Clean up audit log
        audit_log_key = "tsp:audit_log"
        deleted_audits = await redis_conn.zremrangebyscore(
            audit_log_key, "-inf", cutoff_timestamp
        )
        
        # Clean up global activity
        global_activity_key = "tsp:activity:global"
        deleted_activities = await redis_conn.zremrangebyscore(
            global_activity_key, "-inf", cutoff_timestamp
        )
        
        # Clean up old audit event keys
        old_audit_keys = []
        async for key in redis_conn.scan_iter("tsp:audits:*"):
            audit_data = await redis_conn.get(key)
            if audit_data:
                audit = json.loads(audit_data)
                if audit["timestamp"].timestamp() < cutoff_timestamp:
                    old_audit_keys.append(key)
        
        if old_audit_keys:
            await redis_conn.delete(*old_audit_keys)
        
        logger.info(
            f"Cleanup complete: deleted {deleted_audits} audits, "
            f"{deleted_activities} activities, {len(old_audit_keys)} old event keys"
        )
        
        return {
            "success": True,
            "deleted_audits": deleted_audits,
            "deleted_activities": deleted_activities,
            "deleted_event_keys": len(old_audit_keys),
            "cleaned_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to cleanup old data: {e}")
        return {"success": False, "error": str(e)}


async def trigger_audit_notifications(ctx, audit_event: AuditEvent) -> None:
    """
    Trigger notifications for audit events based on severity.
    
    Args:
        ctx: ARQ context
        audit_event: The audit event to process
    """
    redis_conn = ctx["redis"]
    
    # Only process high-severity events
    if audit_event.severity in ["warning", "error", "critical"]:
        notification_key = f"tsp:notifications:{audit_event.severity}"
        await redis_conn.lpush(
            notification_key,
            json.dumps({
                "event_id": audit_event.id,
                "event_type": audit_event.event_type,
                "action": audit_event.action,
                "severity": audit_event.severity,
                "timestamp": audit_event.timestamp.isoformat()
            })
        )
        
        # Keep only last 100 notifications per severity
        await redis_conn.ltrim(notification_key, 0, 99)


async def handle_background_job(ctx, job_name: str, job_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generic background job handler.
    
    Args:
        ctx: ARQ context
        job_name: Name of the job to execute
        job_data: Job parameters
    
    Returns:
        Job execution result
    """
    logger.info(f"Processing background job: {job_name}")
    
    # Route to appropriate handler
    job_handlers = {
        "cleanup": cleanup_old_data,
        "reindex": index_activity_feed,
        "audit_process": process_audit_event,
    }
    
    if job_name not in job_handlers:
        return {"success": False, "error": f"Unknown job type: {job_name}"}
    
    handler = job_handlers[job_name]
    
    # Handle different job signatures
    if job_name in ["cleanup", "reindex"]:
        return await handler(ctx, **job_data)
    elif job_name == "audit_process":
        return await handler(ctx, job_data)
    else:
        return await handler(ctx)


class ARQWorker:
    """ARQ Worker manager for The-Spark-Pit."""
    
    def __init__(self):
        self.redis_pool = None
        self.redis_conn: Optional[redis.Redis] = None
        
    async def startup(self):
        """Initialize Redis connection pool."""
        logger.info("Starting ARQ worker...")
        
        self.redis_conn = redis.from_url(
            REDIS_URL,
            encoding="utf-8",
            decode_responses=True
        )
        
        # Test connection
        await self.redis_conn.ping()
        logger.info(f"Connected to Redis at {REDIS_URL}")
        
        # Initialize Redis pool for ARQ
        self.redis_pool = await RedisPool.create(REDIS_URL)
        
    async def shutdown(self):
        """Clean up connections."""
        logger.info("Shutting down ARQ worker...")
        
        if self.redis_pool:
            await self.redis_pool.close()
        if self.redis_conn:
            await self.redis_conn.close()
    
    async def health_check(self) -> Dict[str, Any]:
        """Check worker health."""
        try:
            await self.redis_conn.ping()
            return {
                "status": "healthy",
                "redis": "connected",
                "worker": "running"
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "redis": "disconnected",
                "error": str(e)
            }


async def main():
    """Run the ARQ worker."""
    from arq.worker import Worker
    
    worker_manager = ARQWorker()
    await worker_manager.startup()
    
    # Create ARQ worker
    worker = Worker(
        functions=[
            process_audit_event,
            index_activity_feed,
            cleanup_old_data,
            handle_background_job,
        ],
        redis_pool=worker_manager.redis_pool,
        timeout=300,
        max_jobs=100,
    )
    
    logger.info("ARQ Worker started. Waiting for jobs...")
    
    try:
        await worker.run()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    finally:
        await worker_manager.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
