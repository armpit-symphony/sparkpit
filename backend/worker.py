import os
import logging
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from arq import cron
from arq.connections import RedisSettings
import time

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sparkpit-worker")

mongo_url = os.environ.get("MONGO_URL")
db_name = os.environ.get("DB_NAME")
client = AsyncIOMotorClient(mongo_url)
db = client[db_name]

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")


async def process_audit_event(ctx, audit_event):
    logger.info("Processing audit event %s", audit_event.get("event_type"))


async def index_message(ctx, message):
    index_doc = {
        "id": message.get("id"),
        "channel_id": message.get("channel_id"),
        "content": message.get("content"),
        "created_at": message.get("created_at"),
        "indexed_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.message_index.update_one({"id": index_doc["id"]}, {"$set": index_doc}, upsert=True)


async def process_bounty_status(ctx, payload):
    logger.info("Processing bounty status %s", payload)


async def generate_daily_room_summary(ctx, room_id="all"):
    logger.info("Generating daily summaries for room scope: %s", room_id)


async def worker_heartbeat(ctx):
    await ctx["redis"].set("sparkpit:worker:heartbeat", int(time.time()))


async def startup(ctx):
    logger.info("SparkPit ARQ worker online")


async def shutdown(ctx):
    logger.info("SparkPit ARQ worker shutting down")


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(REDIS_URL)
    functions = [
        process_audit_event,
        index_message,
        process_bounty_status,
        generate_daily_room_summary,
        worker_heartbeat,
    ]
    cron_jobs = [
        cron(generate_daily_room_summary, hour=2, minute=0),
        cron(worker_heartbeat, second={0, 15, 30, 45}),
    ]
    on_startup = startup
    on_shutdown = shutdown
