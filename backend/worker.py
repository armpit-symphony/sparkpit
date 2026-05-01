import time
"""
ARQ Worker for The-Spark-Pit

Background worker that processes audit events, indexes activity feed,
and handles background jobs using ARQ (Async Redis Queue).
"""

import asyncio
import contextlib
import json
import logging
import os
import base64
import hashlib
import hmac
import ipaddress
import socket
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from motor.motor_asyncio import AsyncIOMotorClient
from cryptography.fernet import Fernet

# ---- Worker heartbeat (Redis) ----
HEARTBEAT_KEY = "sparkpit:worker:heartbeat"

async def _heartbeat_loop(redis):
    """Write a simple unix-epoch heartbeat every 10s."""
    while True:
        try:
            ts = str(int(time.time()))
            # set with TTL so stale workers expire automatically
            await redis.set(HEARTBEAT_KEY, ts, ex=120)
        except Exception as e:
            # do not crash worker; log once per loop
            print("HEARTBEAT_WRITE_FAIL:", repr(e))
        await asyncio.sleep(10)


async def arq_on_startup(ctx):
    """ARQ startup hook for `arq backend.worker.WorkerSettings`."""
    redis_conn = ctx["redis"]
    mongo_client = AsyncIOMotorClient(MONGO_URL)
    ctx["mongo_client"] = mongo_client
    ctx["db"] = mongo_client[DB_NAME]
    ctx["heartbeat_task"] = asyncio.create_task(_heartbeat_loop(redis_conn))
    print("HEARTBEAT_LOOP_STARTED")


async def arq_on_shutdown(ctx):
    """Cancel the heartbeat task on worker shutdown."""
    task = ctx.get("heartbeat_task")
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    mongo_client = ctx.get("mongo_client")
    if mongo_client is not None:
        mongo_client.close()

import redis.asyncio as redis
from arq.connections import RedisSettings
from arq.worker import Retry
from pydantic import BaseModel, Field

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://mongodb:27017")
DB_NAME = os.environ.get("DB_NAME", "thesparkpit")
BOT_SECRET_KEY = os.environ.get("BOT_SECRET_KEY")


# Data Models
class AuditEvent(BaseModel):
    """Audit event model for tracking system activities."""
    id: str = Field(default_factory=lambda: f"audit_{datetime.utcnow().isoformat()}")
    event_type: str
    user_id: Optional[str] = None
    actor_type: Optional[str] = None
    actor_id: Optional[str] = None
    action: Optional[str] = None
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
    functions = [
        "backend.worker.process_audit_event",
        "backend.worker.index_message",
        "backend.worker.retry_probe",
        "backend.worker.deliver_bot_webhook",
        "backend.jobs.bot_reply.generate_bot_reply",
        "backend.jobs.room_summary.summarize_room",
        "backend.worker.process_bounty_status",
        "backend.worker.index_activity_feed",
        "backend.worker.cleanup_old_data",
        "backend.worker.handle_background_job",
    ]
    """ARQ worker settings."""
    redis_settings = RedisSettings.from_dsn(REDIS_URL)
    on_startup = arq_on_startup
    on_shutdown = arq_on_shutdown
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
        if not audit_event.action:
            audit_event.action = audit_event.event_type
        
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


async def index_message(ctx, message_data: Dict[str, Any]) -> Dict[str, Any]:
    """Index a posted message into Redis for lightweight lookup/feed views."""
    redis_conn = ctx["redis"]
    try:
        message_id = message_data.get("id")
        channel_id = message_data.get("channel_id")
        if not message_id or not channel_id:
            return {"success": False, "error": "missing message id or channel_id"}

        created_at = message_data.get("created_at")
        score = time.time()
        if isinstance(created_at, str):
            try:
                score = datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp()
            except ValueError:
                pass

        await redis_conn.set(
            f"tsp:message:{message_id}",
            json.dumps(message_data),
            ex=86400 * 7,
        )
        channel_index_key = f"tsp:channel:{channel_id}:messages"
        await redis_conn.zadd(channel_index_key, {message_id: score})
        await redis_conn.zremrangebyrank(channel_index_key, 0, -2001)

        return {
            "success": True,
            "message_id": message_id,
            "channel_id": channel_id,
            "indexed_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Failed to index message: {e}")
        return {"success": False, "error": str(e)}


async def process_bounty_status(ctx, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Track bounty status changes in Redis for fast ops visibility."""
    redis_conn = ctx["redis"]
    try:
        bounty_id = payload.get("bounty_id")
        status = payload.get("status")
        if not bounty_id or not status:
            return {"success": False, "error": "missing bounty_id or status"}

        now = datetime.utcnow().isoformat()
        history_key = f"tsp:bounty:{bounty_id}:status_history"
        await redis_conn.lpush(history_key, json.dumps({"status": status, "updated_at": now}))
        await redis_conn.ltrim(history_key, 0, 99)
        await redis_conn.set(f"tsp:bounty:{bounty_id}:status", status, ex=86400 * 30)

        return {"success": True, "bounty_id": bounty_id, "status": status, "updated_at": now}
    except Exception as e:
        logger.error(f"Failed to process bounty status: {e}")
        return {"success": False, "error": str(e)}


async def retry_probe(ctx, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Probe job for runbook retry/backoff verification.
    Fails for initial attempts, then succeeds once threshold is reached.
    """
    redis_conn = ctx["redis"]
    probe_id = payload.get("probe_id")
    if not probe_id:
        raise ValueError("probe_id is required")
    succeed_on = int(payload.get("succeed_on", 2))
    defer_seconds = int(payload.get("defer_seconds", 2))
    key = f"tsp:retry_probe:{probe_id}:attempts"
    attempt = await redis_conn.incr(key)
    await redis_conn.expire(key, 3600)
    if attempt < succeed_on:
        # Explicit retry with delay makes backoff visible in logs/timestamps.
        raise Retry(defer=defer_seconds)
    return {
        "success": True,
        "probe_id": probe_id,
        "attempt": int(attempt),
        "succeed_on": succeed_on,
        "completed_at": datetime.utcnow().isoformat(),
    }


def get_fernet() -> Fernet:
    if not BOT_SECRET_KEY:
        raise RuntimeError("BOT_SECRET_KEY must be set")
    key = base64.urlsafe_b64encode(hashlib.sha256(BOT_SECRET_KEY.encode()).digest())
    return Fernet(key)


def decrypt_secret(secret_value: str) -> str:
    return get_fernet().decrypt(secret_value.encode()).decode()


def webhook_matches_event(webhook: Dict[str, Any], event_type: str) -> bool:
    events = webhook.get("events") or []
    return "*" in events or event_type in events


def is_disallowed_webhook_host(hostname: str) -> bool:
    host = (hostname or "").strip().lower()
    if not host:
        return True
    if host in {"localhost", "mongodb", "redis", "backend_api"}:
        return True
    if host.endswith(".local") or host.endswith(".internal"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip:
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )
    try:
        records = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True
    for record in records:
        address = record[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return True
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return True
    return False


def _post_json(url: str, body: bytes, headers: Dict[str, str], timeout: int) -> Dict[str, Any]:
    request = Request(url=url, data=body, headers=headers, method="POST")
    with urlopen(request, timeout=timeout) as response:
        return {"status_code": int(response.status), "body": response.read().decode("utf-8", errors="replace")}


async def _update_bot_webhook_delivery_state(db, bot_id: str, webhook_id: str, updates: Dict[str, Any]) -> None:
    bot = await db.bots.find_one({"id": bot_id}, {"_id": 0, "webhooks": 1})
    if not bot:
        return
    webhooks = list(bot.get("webhooks") or [])
    changed = False
    for webhook in webhooks:
        if webhook.get("id") != webhook_id:
            continue
        webhook.update(updates)
        webhook["updated_at"] = datetime.utcnow().isoformat()
        changed = True
        break
    if changed:
        await db.bots.update_one(
            {"id": bot_id},
            {"$set": {"webhooks": webhooks, "updated_at": datetime.utcnow().isoformat()}},
        )


async def deliver_bot_webhook(ctx, payload: Dict[str, Any]) -> Dict[str, Any]:
    db = ctx.get("db")
    if db is None:
        return {"success": False, "error": "missing db in worker context"}

    bot_id = payload.get("bot_id")
    webhook_id = payload.get("webhook_id")
    event_type = payload.get("event_type")
    event = payload.get("event") or {}
    delivery_id = payload.get("delivery_id")
    force_delivery = bool(payload.get("force_delivery"))
    if not bot_id or not webhook_id or not event_type or not delivery_id:
        return {"success": False, "error": "missing webhook delivery fields"}

    bot = await db.bots.find_one({"id": bot_id}, {"_id": 0})
    if not bot:
        return {"success": False, "error": "bot not found", "bot_id": bot_id}

    webhook = next((item for item in bot.get("webhooks") or [] if item.get("id") == webhook_id), None)
    if not webhook:
        return {"success": False, "error": "webhook not found", "webhook_id": webhook_id}
    if not webhook.get("enabled", True) and not force_delivery:
        return {"success": False, "error": "webhook not found or disabled", "webhook_id": webhook_id}
    if not force_delivery and not webhook_matches_event(webhook, event_type):
        return {"success": False, "error": "event not subscribed", "webhook_id": webhook_id}

    parsed = urlparse(webhook.get("url") or "")
    if parsed.scheme != "https" or not parsed.hostname or is_disallowed_webhook_host(parsed.hostname):
        await _update_bot_webhook_delivery_state(
            db,
            bot_id,
            webhook_id,
            {
                "last_delivery_status": "blocked",
                "last_delivery_at": datetime.utcnow().isoformat(),
                "last_error": "webhook host blocked",
                "last_http_status": None,
                "last_event_type": event_type,
                "last_delivery_id": delivery_id,
            },
        )
        return {"success": False, "error": "webhook host blocked", "webhook_id": webhook_id}

    timestamp = str(int(time.time()))
    body = json.dumps(
        {
            "delivery_id": delivery_id,
            "event_type": event_type,
            "bot_id": bot_id,
            "webhook_id": webhook_id,
            "timestamp": timestamp,
            "event": event,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    signing_secret = decrypt_secret(webhook["signing_secret_encrypted"])
    signed_payload = f"{timestamp}.".encode("utf-8") + body
    signature = hmac.new(signing_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "SparkPit-BotWebhook/1.0",
        "X-SparkPit-Event": event_type,
        "X-SparkPit-Bot-Id": bot_id,
        "X-SparkPit-Webhook-Id": webhook_id,
        "X-SparkPit-Delivery-Id": delivery_id,
        "X-SparkPit-Timestamp": timestamp,
        "X-SparkPit-Signature-256": f"sha256={signature}",
    }

    try:
        response = await asyncio.to_thread(_post_json, webhook["url"], body, headers, 10)
        status_code = int(response["status_code"])
    except HTTPError as error:
        status_code = int(getattr(error, "code", 0) or 0)
        if status_code >= 500:
            attempt = int(ctx.get("job_try", 1))
            defer_seconds = min(300, 2 ** min(attempt, 8))
            await _update_bot_webhook_delivery_state(
                db,
                bot_id,
                webhook_id,
                {
                    "last_delivery_status": "retrying",
                    "last_delivery_at": datetime.utcnow().isoformat(),
                    "last_error": f"server responded {status_code}",
                    "last_http_status": status_code,
                    "last_event_type": event_type,
                    "last_delivery_id": delivery_id,
                },
            )
            raise Retry(defer=defer_seconds) from error
        await _update_bot_webhook_delivery_state(
            db,
            bot_id,
            webhook_id,
            {
                "last_delivery_status": "failed",
                "last_delivery_at": datetime.utcnow().isoformat(),
                "last_error": f"server responded {status_code or 'error'}",
                "last_http_status": status_code or None,
                "last_event_type": event_type,
                "last_delivery_id": delivery_id,
            },
        )
        return {
            "success": False,
            "bot_id": bot_id,
            "webhook_id": webhook_id,
            "delivery_id": delivery_id,
            "status_code": status_code or None,
        }
    except (URLError, TimeoutError, OSError) as error:
        attempt = int(ctx.get("job_try", 1))
        defer_seconds = min(300, 2 ** min(attempt, 8))
        await _update_bot_webhook_delivery_state(
            db,
            bot_id,
            webhook_id,
            {
                "last_delivery_status": "retrying",
                "last_delivery_at": datetime.utcnow().isoformat(),
                "last_error": str(error)[:280],
                "last_http_status": None,
                "last_event_type": event_type,
                "last_delivery_id": delivery_id,
            },
        )
        raise Retry(defer=defer_seconds) from error

    if status_code >= 500:
        attempt = int(ctx.get("job_try", 1))
        defer_seconds = min(300, 2 ** min(attempt, 8))
        await _update_bot_webhook_delivery_state(
            db,
            bot_id,
            webhook_id,
            {
                "last_delivery_status": "retrying",
                "last_delivery_at": datetime.utcnow().isoformat(),
                "last_error": f"server responded {status_code}",
                "last_http_status": status_code,
                "last_event_type": event_type,
                "last_delivery_id": delivery_id,
            },
        )
        raise Retry(defer=defer_seconds)

    updates = {
        "last_delivery_status": "delivered" if 200 <= status_code < 300 else "failed",
        "last_delivery_at": datetime.utcnow().isoformat(),
        "last_error": None if 200 <= status_code < 300 else f"server responded {status_code}",
        "last_http_status": status_code,
        "last_event_type": event_type,
        "last_delivery_id": delivery_id,
    }
    await _update_bot_webhook_delivery_state(db, bot_id, webhook_id, updates)
    return {
        "success": 200 <= status_code < 300,
        "bot_id": bot_id,
        "webhook_id": webhook_id,
        "delivery_id": delivery_id,
        "status_code": status_code,
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
