from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path
from urllib.parse import urlparse
import ipaddress
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timezone, timedelta
from backend.research_protocol import (
    apply_bot_protocol_defaults,
    apply_research_protocol_defaults,
    normalize_participation_cadence,
    record_bot_research_activity,
)
from backend.stripe_integration import StripeCheckout, CheckoutSessionRequest
from arq import create_pool
from arq.connections import RedisSettings
from cryptography.fernet import Fernet
import os
import uuid
import logging
import json
import base64
import hashlib
import hmac
import re
import secrets
import time

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

JWT_SECRET = os.environ.get("JWT_SECRET")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 7
BOT_TOKEN_EXPIRE_DAYS = 30
BOT_REFRESH_TOKEN_DAYS = 60
BOT_SECRET_KEY = os.environ.get("BOT_SECRET_KEY")

if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET must be set")
if not BOT_SECRET_KEY:
    raise RuntimeError("BOT_SECRET_KEY must be set")

ENV_STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY")
ENV_STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
ENV_STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY")
ENV_STRIPE_MEMBERSHIP_MONTHLY_PRICE_ID = os.environ.get("STRIPE_MEMBERSHIP_MONTHLY_PRICE_ID")
ENV_STRIPE_MEMBERSHIP_YEARLY_PRICE_ID = os.environ.get("STRIPE_MEMBERSHIP_YEARLY_PRICE_ID")
ENV_STRIPE_BOT_INVITE_PRICE_ID = os.environ.get("STRIPE_BOT_INVITE_PRICE_ID")
BOT_INVITE_DEFAULT_EXPIRY_DAYS = 30
MEMBERSHIP_MONTHLY_DURATION_DAYS = 30
MEMBERSHIP_YEARLY_DURATION_DAYS = 365

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
redis_settings = RedisSettings.from_dsn(REDIS_URL)
redis_pool = None

ACTIVITY_EVENTS = [
    "room.created",
    "room.joined",
    "bot.joined",
    "bounty.created",
    "bounty.claimed",
    "bounty.submitted",
    "bounty.approved",
]
BOT_WEBHOOK_EVENT_TYPES = {
    "message.created",
    "room.joined",
    "bot.joined",
    "bounty.created",
    "bounty.claimed",
    "bounty.submitted",
    "bounty.approved",
}
BOT_WEBHOOK_TEST_EVENT_TYPE = "webhook.test"
BOT_WEBHOOK_MAX_PER_BOT = 5

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())

def now_epoch() -> int:
    return int(time.time())

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def create_token(user: Dict[str, Any]) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRE_DAYS)
    payload = {"sub": user["id"], "exp": expire, "iat": now_epoch()}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_bot_token(bot_id: str, scopes: Dict[str, List[str]]) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=BOT_TOKEN_EXPIRE_DAYS)
    payload = {"sub": bot_id, "type": "bot", "scopes": scopes, "exp": expire, "iat": now_epoch(), "jti": new_id()}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(BOT_SECRET_KEY.encode()).digest())
    return Fernet(key)


def encrypt_secret(secret_value: str) -> str:
    return get_fernet().encrypt(secret_value.encode()).decode()


def decrypt_secret(secret_value: str) -> str:
    return get_fernet().decrypt(secret_value.encode()).decode()


def generate_bot_secret() -> str:
    return secrets.token_urlsafe(32)


def generate_bot_recovery_code() -> str:
    return secrets.token_urlsafe(24)

def normalize_terms(raw: str) -> List[str]:
    return [term.strip().lower() for term in raw.split(",") if term.strip()]


def get_blocked_terms() -> List[str]:
    return normalize_terms(os.environ.get("BLOCKED_TERMS", ""))


def get_max_message_length() -> int:
    try:
        return int(os.environ.get("MAX_MESSAGE_LENGTH", "2000"))
    except ValueError:
        return 2000


def get_rate_limit(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def get_duplicate_window_seconds() -> int:
    return get_rate_limit("DUPLICATE_WINDOW_SECONDS", 120)


def get_duplicate_threshold() -> int:
    return get_rate_limit("DUPLICATE_THRESHOLD", 3)


def hash_content(content: str) -> str:
    normalized = (content or "").strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()


def truncate_content(content: str, limit: int = 500) -> str:
    if content is None:
        return ""
    return content if len(content) <= limit else content[:limit]


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def normalize_invite_expiration_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    date_part = raw.split("T", 1)[0].strip()
    try:
        parsed = datetime.strptime(date_part, "%Y-%m-%d")
    except ValueError:
        parsed_dt = parse_iso_datetime(raw)
        if not parsed_dt:
            return None
        return parsed_dt.date().isoformat()
    return parsed.date().isoformat()


def invite_expiration_boundary(value: Optional[str]) -> Optional[datetime]:
    normalized_date = normalize_invite_expiration_date(value)
    if not normalized_date:
        return None
    try:
        day = datetime.strptime(normalized_date, "%Y-%m-%d").date()
    except ValueError:
        return None
    return datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)


def is_invite_expired(value: Optional[str], *, reference: Optional[datetime] = None) -> bool:
    boundary = invite_expiration_boundary(value)
    if not boundary:
        return False
    current = reference or datetime.now(timezone.utc)
    return current >= boundary


def normalize_invite_type(value: Optional[str]) -> str:
    normalized = (value or "membership").strip().lower()
    if normalized not in {"membership", "bot"}:
        raise HTTPException(status_code=400, detail="Invite type must be membership or bot")
    return normalized


def get_default_bot_invite_expiration_date() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=BOT_INVITE_DEFAULT_EXPIRY_DAYS)).date().isoformat()


def normalize_scope_ids(values: Optional[List[str]]) -> List[str]:
    normalized: List[str] = []
    seen = set()
    for value in values or []:
        item = (value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def normalize_bot_type(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = " ".join((value or "").strip().split())
    if not normalized:
        return None
    if len(normalized) > 80:
        raise HTTPException(status_code=400, detail="Bot label/type is too long")
    return normalized


def build_bot_handle_seed(value: str) -> str:
    chars: List[str] = []
    for char in (value or "").lower():
        if char.isalnum():
            chars.append(char)
            continue
        if chars and chars[-1] != "-":
            chars.append("-")
    seed = "".join(chars).strip("-")
    return seed or "agent"


async def build_unique_bot_handle(seed_value: str) -> str:
    seed = build_bot_handle_seed(seed_value)
    candidate = seed
    suffix = 1
    while await db.bots.find_one({"handle": candidate}, {"_id": 1}):
        suffix += 1
        candidate = f"{seed}-{suffix}"
    return candidate


def normalize_membership_plan(value: Optional[str], *, default: str = "monthly") -> str:
    normalized = (value or default).strip().lower()
    if normalized not in {"monthly", "yearly"}:
        raise HTTPException(status_code=400, detail="Membership plan must be monthly or yearly")
    return normalized


def membership_duration_days(plan: str) -> int:
    return MEMBERSHIP_YEARLY_DURATION_DAYS if plan == "yearly" else MEMBERSHIP_MONTHLY_DURATION_DAYS


def compute_membership_expiration(start_at: datetime, plan: str) -> str:
    return (start_at + timedelta(days=membership_duration_days(plan))).isoformat()


async def refresh_user_membership_state(user_doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not user_doc:
        return None
    if user_doc.get("role") == "admin":
        return user_doc
    if user_doc.get("membership_status") != "active":
        return user_doc
    expires_at = parse_iso_datetime(user_doc.get("membership_expires_at"))
    if not expires_at:
        return user_doc
    if expires_at > datetime.now(timezone.utc):
        return user_doc
    now = now_iso()
    await db.users.update_one(
        {"id": user_doc["id"]},
        {
            "$set": {
                "membership_status": "pending",
                "stripe_session_status": "expired",
                "updated_at": now,
            }
        },
    )
    user_doc["membership_status"] = "pending"
    user_doc["stripe_session_status"] = "expired"
    user_doc["updated_at"] = now
    return user_doc


def is_bot_session_user(user_doc: Optional[Dict[str, Any]]) -> bool:
    if not user_doc:
        return False
    return user_doc.get("account_source") in {"bot_public_entry", "bot_invite_claim"}


def can_user_post_conversations(user_doc: Optional[Dict[str, Any]]) -> bool:
    if not user_doc:
        return False
    return True


async def resolve_session_bot(user_doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not user_doc:
        return None
    owner_user_id = user_doc.get("id")
    if not owner_user_id:
        return None
    active_bot_id = user_doc.get("active_bot_id")
    bot_doc = None
    if active_bot_id:
        bot_doc = await db.bots.find_one({"id": active_bot_id, "owner_user_id": owner_user_id})
        if not bot_doc:
            user_doc["active_bot_id"] = None
            await db.users.update_one(
                {"id": owner_user_id},
                {"$set": {"active_bot_id": None, "updated_at": now_iso()}},
            )
    if not bot_doc and is_bot_session_user(user_doc):
        bot_doc = await db.bots.find_one(
            {"owner_user_id": owner_user_id},
            sort=[("created_at", -1)],
        )
        if bot_doc and bot_doc.get("id") and active_bot_id != bot_doc.get("id"):
            await db.users.update_one(
                {"id": owner_user_id},
                {"$set": {"active_bot_id": bot_doc["id"], "updated_at": now_iso()}},
            )
    return sanitize_bot(bot_doc) if bot_doc else None


def build_session_principal(user_doc: Dict[str, Any], bot_doc: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if bot_doc:
        return {
            "principal_type": "bot_operator_session",
            "actor_type": "bot",
            "actor_id": bot_doc.get("id"),
            "actor_handle": bot_doc.get("handle") or bot_doc.get("name"),
            "operator_user_id": user_doc.get("id"),
            "operator_handle": user_doc.get("operator_handle") or user_doc.get("handle"),
        }
    return {
        "principal_type": "human_user_session",
        "actor_type": "human",
        "actor_id": user_doc.get("id"),
        "actor_handle": user_doc.get("handle"),
        "operator_user_id": None,
        "operator_handle": None,
    }


async def hydrate_authenticated_user(user_doc: Dict[str, Any]) -> Dict[str, Any]:
    user_doc = sanitize_doc(user_doc)
    user_doc.pop("password_hash", None)
    active_bot = await resolve_session_bot(user_doc)
    user_doc["active_bot"] = active_bot
    user_doc["session_principal"] = build_session_principal(user_doc, active_bot)
    return user_doc


async def get_session_actor_context(user_doc: Dict[str, Any]) -> Dict[str, Any]:
    active_bot = user_doc.get("active_bot") or await resolve_session_bot(user_doc)
    if active_bot:
        return {
            "content_actor_type": "bot",
            "content_actor_id": active_bot["id"],
            "display_handle": active_bot.get("handle") or active_bot.get("name"),
            "audit_actor_type": "bot",
            "audit_actor_id": active_bot["id"],
            "author_user_id": None,
            "author_bot_id": active_bot["id"],
            "operator_user_id": user_doc.get("id"),
            "operator_handle": user_doc.get("operator_handle") or user_doc.get("handle"),
            "bot": active_bot,
        }
    return {
        "content_actor_type": "human",
        "content_actor_id": user_doc["id"],
        "display_handle": user_doc.get("handle"),
        "audit_actor_type": "user",
        "audit_actor_id": user_doc["id"],
        "author_user_id": user_doc["id"],
        "author_bot_id": None,
        "operator_user_id": None,
        "operator_handle": None,
        "bot": None,
    }


async def ensure_bot_room_membership(room_id: str, bot_doc: Optional[Dict[str, Any]], role: str = "member") -> bool:
    if not bot_doc or not bot_doc.get("id"):
        return False
    existing = await db.room_memberships.find_one(
        {"room_id": room_id, "member_type": "bot", "member_id": bot_doc["id"]}
    )
    if existing:
        return False
    await db.room_memberships.insert_one(
        {
            "id": new_id(),
            "room_id": room_id,
            "member_type": "bot",
            "member_id": bot_doc["id"],
            "role": role,
            "created_at": now_iso(),
        }
    )
    return True


async def get_room_membership_state(user: Dict[str, Any], room_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    user_membership = await db.room_memberships.find_one(
        {"room_id": room_id, "member_type": "user", "member_id": user["id"]},
        {"_id": 0},
    )
    active_bot = user.get("active_bot") or await resolve_session_bot(user)
    bot_membership = None
    if active_bot:
        bot_membership = await db.room_memberships.find_one(
            {"room_id": room_id, "member_type": "bot", "member_id": active_bot["id"]},
            {"_id": 0},
        )
    return (
        sanitize_doc(user_membership) if user_membership else None,
        sanitize_doc(bot_membership) if bot_membership else None,
    )


async def build_room_participants(room_id: str) -> Dict[str, Any]:
    memberships = await db.room_memberships.find({"room_id": room_id}, {"_id": 0}).to_list(500)
    user_ids = [item["member_id"] for item in memberships if item.get("member_type") == "user"]
    bot_ids = [item["member_id"] for item in memberships if item.get("member_type") == "bot"]
    users = {
        item["id"]: sanitize_doc(item)
        for item in await db.users.find({"id": {"$in": user_ids}}, {"_id": 0}).to_list(500)
    }
    for user in users.values():
        user.pop("password_hash", None)
    bots = {
        item["id"]: sanitize_bot(item)
        for item in await db.bots.find({"id": {"$in": bot_ids}}, {"_id": 0}).to_list(500)
    }

    human_participants: List[Dict[str, Any]] = []
    bot_participants: List[Dict[str, Any]] = []
    for membership in sorted(memberships, key=lambda item: item.get("created_at") or ""):
        if membership.get("member_type") == "user":
            participant = lobby_post_view(users.get(membership.get("member_id")))
            if participant:
                participant["room_role"] = membership.get("role")
                participant["joined_at"] = membership.get("created_at")
                human_participants.append(participant)
            continue
        if membership.get("member_type") == "bot":
            bot_doc = bots.get(membership.get("member_id"))
            if not bot_doc:
                continue
            operator_doc = users.get(bot_doc.get("owner_user_id"))
            participant = lobby_bot_view(bot_doc, operator_doc)
            if participant:
                participant["room_role"] = membership.get("role")
                participant["joined_at"] = membership.get("created_at")
                bot_participants.append(participant)

    return {
        "humans": human_participants,
        "bots": bot_participants,
        "human_count": len(human_participants),
        "bot_count": len(bot_participants),
    }


async def build_unique_user_handle(seed_value: str) -> str:
    seed = build_bot_handle_seed(seed_value) or "agent"
    candidate = f"{seed}-ops"
    suffix = 1
    while await db.users.find_one({"handle": candidate}, {"_id": 1}):
        suffix += 1
        candidate = f"{seed}-ops-{suffix}"
    return candidate


async def generate_unique_invite_code(invite_type: str) -> str:
    prefix = "BOT" if invite_type == "bot" else "SPARK"
    while True:
        candidate = f"{prefix}-{uuid.uuid4().hex[:8].upper()}"
        existing = await db.invite_codes.find_one({"code": candidate}, {"_id": 1})
        if not existing:
            return candidate


def summarize_signal_severity(count_24h: int, count_7d: int) -> str:
    if count_24h >= 10 or count_7d >= 30:
        return "high"
    if count_24h >= 3 or count_7d >= 10:
        return "medium"
    if count_24h >= 1 or count_7d >= 1:
        return "low"
    return "clean"


def classify_rate_limit_severity(endpoint: str) -> str:
    if endpoint.startswith("/auth/") or endpoint.startswith("/payments/") or endpoint.startswith("/admin/"):
        return "high"
    if endpoint.startswith("/bots/") or endpoint.startswith("/security/") or endpoint.startswith("/channels/"):
        return "medium"
    return "low"


def classify_csp_report_severity(report: Dict[str, Any]) -> str:
    directive = (report.get("effective_directive") or report.get("violated_directive") or "").lower()
    if directive.startswith("script-src") or directive in {"frame-ancestors", "object-src", "base-uri"}:
        return "high"
    if directive.startswith("connect-src") or directive.startswith("style-src") or directive.startswith("form-action"):
        return "medium"
    return "low"


def format_invite_code_preview(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    code = code.strip()
    if len(code) <= 4:
        return "*" * len(code)
    return f"{code[:4]}..."


async def log_security_event(
    event_type: str,
    *,
    severity: str,
    actor_type: str,
    actor_id: str,
    route: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
):
    doc = {
        "id": new_id(),
        "event_type": event_type,
        "severity": severity,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "route": route,
        "payload": payload or {},
        "created_at": now_iso(),
    }
    try:
        await db.security_events.insert_one(doc)
    except Exception as error:
        logger.warning("Security event log error: %s", error)


async def log_rate_limit_event(
    actor_type: str,
    actor_id: str,
    endpoint: str,
    detail: str,
    metadata: Optional[Dict[str, Any]] = None,
):
    if not redis_pool:
        return
    event = {
        "actor_type": actor_type,
        "actor_id": actor_id,
        "endpoint": endpoint,
        "detail": detail,
        "metadata": metadata or {},
        "created_at": now_iso(),
    }
    await log_security_event(
        "rate_limit.hit",
        severity=classify_rate_limit_severity(endpoint),
        actor_type=actor_type,
        actor_id=actor_id,
        route=endpoint,
        payload=event,
    )
    try:
        await redis_pool.lpush("rl:events", json.dumps(event))
        await redis_pool.ltrim("rl:events", 0, 199)
    except Exception as error:
        logger.warning("Rate limit event log error: %s", error)


def get_shadow_ban_reason() -> str:
    return os.environ.get("SHADOW_BAN_REASON", "Policy violation")


def moderate_text(text: str) -> Optional[str]:
    if text is None:
        return None
    max_len = get_max_message_length()
    if len(text) > max_len:
        return f"Content too long (max {max_len} characters)"
    lowered = text.lower()
    for term in get_blocked_terms():
        if term and term in lowered:
            return "Content violates community rules"
    return None


async def rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    if not redis_pool:
        return True
    try:
        count = await redis_pool.incr(key)
        if count == 1:
            await redis_pool.expire(key, window_seconds)
        return count <= limit
    except Exception as error:
        logger.warning("Rate limit error: %s", error)
        return True


async def enforce_rate_limit(
    request: Request,
    *,
    key: str,
    limit: int,
    window_seconds: int,
    actor_type: str,
    actor_id: str,
    endpoint: str,
    detail: str,
    error_detail: str = "Rate limit exceeded",
):
    allowed = await rate_limit(key, limit, window_seconds)
    if allowed:
        return
    await log_rate_limit_event(
        actor_type,
        actor_id,
        endpoint,
        detail,
        metadata={
            **get_request_meta(request),
            "limit": limit,
            "window_seconds": window_seconds,
        },
    )
    raise HTTPException(status_code=429, detail=error_detail)


async def detect_duplicate_content(actor_type: str, actor_id: str, content: str) -> bool:
    if not redis_pool:
        return False
    key = f"dup:{actor_type}:{actor_id}:{hash_content(content)}"
    try:
        count = await redis_pool.incr(key)
        if count == 1:
            await redis_pool.expire(key, get_duplicate_window_seconds())
        return count > get_duplicate_threshold()
    except Exception as error:
        logger.warning("Duplicate detection error: %s", error)
        return False


async def log_moderation_event(
    actor_type: str,
    actor_id: str,
    content_type: str,
    content: str,
    reason: str,
    action: str = "rejected",
    metadata: Optional[Dict[str, Any]] = None,
):
    doc = {
        "id": new_id(),
        "actor_type": actor_type,
        "actor_id": actor_id,
        "content_type": content_type,
        "content": truncate_content(content),
        "reason": reason,
        "action": action,
        "status": "queued",
        "metadata": metadata or {},
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.moderation_queue.insert_one(doc)


async def should_alert_on_moderation(actor_type: str, actor_id: str) -> bool:
    recent_window = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    recent = await db.moderation_queue.count_documents({
        "actor_type": actor_type,
        "actor_id": actor_id,
        "created_at": {"$gte": recent_window},
    })
    return recent >= get_rate_limit("ALERT_MODERATION_THRESHOLD", 5)


async def log_alert_event(event_type: str, payload: Dict[str, Any]):
    doc = {
        "id": new_id(),
        "event_type": event_type,
        "payload": payload,
        "created_at": now_iso(),
    }
    await db.alert_events.insert_one(doc)


def clamp_score(value: int) -> int:
    return max(0, min(100, value))


async def compute_user_trust(user_id: str) -> Dict[str, Any]:
    user = await db.users.find_one({"id": user_id})
    if not user:
        return {"score": 0, "signals": {}}
    created_at = user.get("created_at")
    age_days = 0
    if created_at:
        try:
            created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - created_dt).days
        except Exception:
            age_days = 0
    messages_sent = await db.messages.count_documents({"sender_type": "user", "sender_id": user_id})
    moderation_count = await db.moderation_queue.count_documents({"actor_type": "user", "actor_id": user_id})
    score = 50
    score += min(age_days // 10, 20)
    score += min(messages_sent // 50, 10)
    score -= moderation_count * 10
    return {
        "score": clamp_score(score),
        "signals": {
            "age_days": age_days,
            "messages_sent": messages_sent,
            "moderation_flags": moderation_count,
        },
    }


async def compute_bot_trust(bot_id: str) -> Dict[str, Any]:
    bot = await db.bots.find_one({"id": bot_id})
    if not bot:
        return {"score": 0, "signals": {}}
    messages_sent = await db.messages.count_documents({"sender_type": "bot", "sender_id": bot_id})
    moderation_count = await db.moderation_queue.count_documents({"actor_type": "bot", "actor_id": bot_id})
    handshake_verified = 1 if bot.get("handshake_verified_at") else 0
    score = 50
    score += 10 if handshake_verified else 0
    score += min(messages_sent // 100, 10)
    score -= moderation_count * 10
    return {
        "score": clamp_score(score),
        "signals": {
            "messages_sent": messages_sent,
            "handshake_verified": bool(handshake_verified),
            "moderation_flags": moderation_count,
        },
    }


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def sanitize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


def sanitize_bot(bot: Dict[str, Any]) -> Dict[str, Any]:
    bot = apply_bot_protocol_defaults(sanitize_doc(bot))
    if not bot:
        return bot
    bot.pop("bot_secret_encrypted", None)
    bot.pop("bot_recovery_code_hash", None)
    bot.pop("handshake_challenge", None)
    bot.pop("handshake_expires_at", None)
    bot.pop("webhooks", None)
    return bot


def sanitize_bot_webhook(webhook: Dict[str, Any]) -> Dict[str, Any]:
    webhook = sanitize_doc(dict(webhook or {}))
    webhook.pop("signing_secret_encrypted", None)
    return webhook


def normalize_bot_webhook_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Webhook URL is required")
    parsed = urlparse(raw)
    if parsed.scheme != "https":
        raise HTTPException(status_code=400, detail="Webhook URL must use https")
    if not parsed.netloc or not parsed.hostname:
        raise HTTPException(status_code=400, detail="Webhook URL is invalid")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="Webhook URL cannot include credentials")

    hostname = parsed.hostname.lower()
    if hostname in {"localhost", "mongodb", "redis", "backend_api"}:
        raise HTTPException(status_code=400, detail="Webhook host is not allowed")
    if hostname.endswith(".local") or hostname.endswith(".internal"):
        raise HTTPException(status_code=400, detail="Webhook host is not allowed")
    if "." not in hostname and not hostname.startswith("xn--"):
        raise HTTPException(status_code=400, detail="Webhook host must be publicly routable")

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        ip = None
    if ip and (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        raise HTTPException(status_code=400, detail="Webhook host is not allowed")

    return parsed._replace(fragment="").geturl()


def normalize_bot_webhook_events(events: Optional[List[str]]) -> List[str]:
    normalized: List[str] = []
    for value in events or []:
        event_name = (value or "").strip().lower()
        if not event_name:
            continue
        if event_name in {"*", "all"}:
            return ["*"]
        if event_name not in BOT_WEBHOOK_EVENT_TYPES:
            raise HTTPException(status_code=400, detail=f"Unsupported webhook event: {value}")
        if event_name not in normalized:
            normalized.append(event_name)
    return normalized or ["*"]


def bot_webhook_matches_event(webhook: Dict[str, Any], event_type: str) -> bool:
    events = webhook.get("events") or []
    return "*" in events or event_type in events


async def get_owned_bot_or_404(bot_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    bot = await db.bots.find_one({"id": bot_id, "owner_user_id": user["id"]})
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    return sanitize_doc(bot)


async def update_bot_webhook_list(bot_id: str, webhooks: List[Dict[str, Any]]) -> Dict[str, Any]:
    await db.bots.update_one({"id": bot_id}, {"$set": {"webhooks": webhooks, "updated_at": now_iso()}})
    updated = await db.bots.find_one({"id": bot_id}, {"_id": 0})
    return sanitize_doc(updated)


async def enqueue_bot_webhook_delivery(
    *,
    bot_id: str,
    webhook_id: str,
    event_type: str,
    event: Dict[str, Any],
    force_delivery: bool = False,
) -> str:
    delivery_id = new_id()
    await enqueue_job(
        "deliver_bot_webhook",
        {
            "bot_id": bot_id,
            "webhook_id": webhook_id,
            "delivery_id": delivery_id,
            "event_type": event_type,
            "event": event,
            "force_delivery": force_delivery,
        },
    )
    return delivery_id


async def emit_bot_webhook_event(
    *,
    event_type: str,
    event: Dict[str, Any],
    room_id: Optional[str] = None,
    bot_ids: Optional[List[str]] = None,
    exclude_bot_ids: Optional[List[str]] = None,
):
    if not redis_pool:
        return

    target_bot_ids = bot_ids or []
    if room_id and not target_bot_ids:
        memberships = await db.room_memberships.find(
            {"room_id": room_id, "member_type": "bot"},
            {"_id": 0, "member_id": 1},
        ).to_list(500)
        target_bot_ids = [item["member_id"] for item in memberships if item.get("member_id")]

    excluded = {item for item in (exclude_bot_ids or []) if item}
    target_bot_ids = [bot_id for bot_id in list(dict.fromkeys(target_bot_ids)) if bot_id not in excluded]
    if not target_bot_ids:
        return

    bots = await db.bots.find({"id": {"$in": target_bot_ids}}, {"_id": 0, "id": 1, "webhooks": 1}).to_list(500)
    for bot in bots:
        for webhook in bot.get("webhooks") or []:
            if not webhook.get("enabled", True):
                continue
            if not bot_webhook_matches_event(webhook, event_type):
                continue
            await enqueue_bot_webhook_delivery(
                bot_id=bot["id"],
                webhook_id=webhook["id"],
                event_type=event_type,
                event=event,
            )


async def enqueue_job(job_name: str, payload: Dict[str, Any]):
    if not redis_pool:
        return
    job_name_map = {
        "process_audit_event": "backend.worker.process_audit_event",
        "index_message": "backend.worker.index_message",
        "generate_bot_reply": "backend.jobs.bot_reply.generate_bot_reply",
        "process_bounty_status": "backend.worker.process_bounty_status",
        "summarize_room": "backend.jobs.room_summary.summarize_room",
        "deliver_bot_webhook": "backend.worker.deliver_bot_webhook",
    }
    resolved_job_name = job_name_map.get(job_name, job_name)
    try:
        await redis_pool.enqueue_job(resolved_job_name, payload)
    except Exception as error:
        logger.warning("Queue enqueue failed: %s", error)


async def fetch_stripe_session(session_id: str) -> Dict[str, Any]:
    runtime_config = await get_runtime_stripe_config()
    if not runtime_config.get("secret_key"):
        return {}
    try:
        stripe_checkout = StripeCheckout(
            api_key=runtime_config["secret_key"],
            webhook_secret=runtime_config.get("webhook_secret"),
        )
        session = await stripe_checkout.get_checkout_session(session_id)
        return {
            "id": session.session_id,
            "status": session.status,
            "payment_status": session.payment_status,
            "amount_total": session.amount_total,
            "currency": session.currency,
            "customer": session.customer_id,
            "metadata": session.metadata or {},
        }
    except Exception as error:
        logger.warning("Unable to fetch Stripe session %s: %s", session_id, error)
        return {}


async def log_audit(
    event_type: str,
    actor_type: str,
    actor_id: str,
    room_id: Optional[str] = None,
    channel_id: Optional[str] = None,
    bounty_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
):
    audit_doc = {
        "id": new_id(),
        "event_type": event_type,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "room_id": room_id,
        "channel_id": channel_id,
        "bounty_id": bounty_id,
        "payload": payload or {},
        "created_at": now_iso(),
    }
    await db.audit_events.insert_one(audit_doc)
    await enqueue_job("process_audit_event", audit_doc)


async def hydrate_invite_codes(invite_codes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not invite_codes:
        return []

    user_ids = set()
    bot_ids = set()
    for code in invite_codes:
        if code.get("created_by_user_id"):
            user_ids.add(code["created_by_user_id"])
        if code.get("revoked_by_user_id"):
            user_ids.add(code["revoked_by_user_id"])
        if code.get("purchased_by_user_id"):
            user_ids.add(code["purchased_by_user_id"])
        if code.get("claimed_by_user_id"):
            user_ids.add(code["claimed_by_user_id"])
        if code.get("claimed_bot_id"):
            bot_ids.add(code["claimed_bot_id"])
        for claim in code.get("claimed_by", []):
            if claim.get("user_id"):
                user_ids.add(claim["user_id"])

    user_lookup: Dict[str, Dict[str, Any]] = {}
    if user_ids:
        users = await db.users.find(
            {"id": {"$in": [user_id for user_id in user_ids if user_id]}},
            {"_id": 0, "id": 1, "email": 1, "handle": 1},
        ).to_list(len(user_ids))
        user_lookup = {
            user["id"]: sanitize_doc(user)
            for user in users
            if user.get("id")
        }

    bot_lookup: Dict[str, Dict[str, Any]] = {}
    if bot_ids:
        bots = await db.bots.find(
            {"id": {"$in": [bot_id for bot_id in bot_ids if bot_id]}},
            {"_id": 0, "id": 1, "handle": 1, "name": 1, "status": 1, "bot_type": 1},
        ).to_list(len(bot_ids))
        bot_lookup = {
            bot["id"]: sanitize_bot(bot)
            for bot in bots
            if bot.get("id")
        }

    items: List[Dict[str, Any]] = []
    for code in invite_codes:
        code_doc = sanitize_doc(dict(code))
        claims = []
        for claim in code_doc.get("claimed_by", []) or []:
            user_id = claim.get("user_id")
            claims.append(
                {
                    "user_id": user_id,
                    "claimed_at": claim.get("claimed_at"),
                    "user": user_lookup.get(user_id),
                }
            )
        claims.sort(key=lambda claim: claim.get("claimed_at") or "", reverse=True)
        code_doc["invite_type"] = normalize_invite_type(code_doc.get("invite_type"))
        code_doc["created_by"] = user_lookup.get(code_doc.get("created_by_user_id"))
        code_doc["revoked_by"] = user_lookup.get(code_doc.get("revoked_by_user_id"))
        code_doc["purchased_by"] = user_lookup.get(code_doc.get("purchased_by_user_id"))
        code_doc["claimed_by"] = claims
        code_doc["claimed_by_user"] = user_lookup.get(code_doc.get("claimed_by_user_id"))
        code_doc["claimed_bot"] = bot_lookup.get(code_doc.get("claimed_bot_id"))
        code_doc["remaining_uses"] = max(code_doc.get("max_uses", 1) - code_doc.get("uses", 0), 0)
        items.append(code_doc)
    return items


def normalize_bot_invite_text(value: Optional[str], *, max_length: int) -> Optional[str]:
    cleaned = " ".join((value or "").split()).strip()
    if not cleaned:
        return None
    if len(cleaned) > max_length:
        raise HTTPException(status_code=400, detail="Bot invite field is too long")
    return cleaned


async def moderate_bot_identity_fields(
    *,
    actor_type: str,
    actor_id: str,
    bot_name: Optional[str],
    description: Optional[str],
    operator_handle: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    combined = "\n".join(
        value
        for value in [bot_name or "", description or "", operator_handle or ""]
        if value and value.strip()
    ).strip()
    if not combined:
        return
    moderation_error = moderate_text(combined)
    if not moderation_error:
        return
    await log_moderation_event(
        actor_type,
        actor_id,
        "bot_identity",
        combined,
        moderation_error,
        metadata=metadata,
    )
    if await should_alert_on_moderation(actor_type, actor_id):
        await log_alert_event("moderation.spike", {"actor_type": actor_type, "actor_id": actor_id})
    raise HTTPException(status_code=400, detail=moderation_error)


def summarize_bot_invite_scope(invite_doc: Dict[str, Any]) -> str:
    room_count = len(normalize_scope_ids(invite_doc.get("allowed_room_ids")))
    channel_count = len(normalize_scope_ids(invite_doc.get("allowed_channel_ids")))
    if not room_count and not channel_count:
        return "This invite creates a bot identity and defaults entry into the main Lobby."
    parts: List[str] = ["This invite creates a bot identity"]
    if room_count:
        parts.append(f"grants {room_count} room{'s' if room_count != 1 else ''}")
    if channel_count:
        connector = "and" if room_count else "grants"
        parts.append(f"{connector} {channel_count} channel{'s' if channel_count != 1 else ''}")
    return " ".join(parts) + "."


def resolve_bot_invite_source_label(invite_doc: Dict[str, Any]) -> str:
    source = (invite_doc.get("created_source") or "admin").strip().lower()
    if source == "purchase":
        return "Purchased invite"
    if source == "admin":
        return "Admin-issued invite"
    return source.replace("_", " ").title() or "Invite"


def resolve_bot_invited_by_label(invite_doc: Dict[str, Any]) -> Optional[str]:
    for key in ("purchased_by", "created_by"):
        actor = invite_doc.get(key) or {}
        label = actor.get("handle") or actor.get("email")
        if label:
            return label
    return None


def build_bot_invite_preview_payload(invite_doc: Dict[str, Any]) -> Dict[str, Any]:
    hydrated = sanitize_doc(dict(invite_doc))
    bot_name = normalize_bot_invite_text(hydrated.get("bot_name"), max_length=80)
    bot_type = normalize_bot_type(hydrated.get("bot_type"))
    bot_description = normalize_bot_invite_text(hydrated.get("bot_description"), max_length=280)
    owner_note = normalize_bot_invite_text(hydrated.get("owner_note"), max_length=280)
    return {
        "id": hydrated.get("id"),
        "code": hydrated.get("code"),
        "invite_type": "bot",
        "expires_at": hydrated.get("expires_at"),
        "created_source": hydrated.get("created_source") or "admin",
        "source_label": resolve_bot_invite_source_label(hydrated),
        "invited_by_label": resolve_bot_invited_by_label(hydrated),
        "bot_name": bot_name,
        "bot_type": bot_type,
        "bot_description": bot_description,
        "owner_note": owner_note,
        "allowed_room_ids": normalize_scope_ids(hydrated.get("allowed_room_ids")),
        "allowed_channel_ids": normalize_scope_ids(hydrated.get("allowed_channel_ids")),
        "requires_identity_completion": not bool(bot_name),
        "access_summary": summarize_bot_invite_scope(hydrated),
    }


async def get_claimable_bot_invite_by_code(code: str) -> Dict[str, Any]:
    code_doc = await db.invite_codes.find_one({"code": code}, {"_id": 0})
    if not code_doc:
        raise HTTPException(status_code=404, detail="Invite code not found")
    code_doc = sanitize_doc(code_doc)
    if normalize_invite_type(code_doc.get("invite_type")) != "bot":
        raise HTTPException(status_code=400, detail="This code is not a bot invite")
    if code_doc.get("revoked_at"):
        raise HTTPException(status_code=400, detail="Invite code revoked")
    if code_doc.get("claimed_bot_id") or code_doc.get("uses", 0) >= code_doc.get("max_uses", 1):
        raise HTTPException(status_code=400, detail="Invite code already claimed")
    if is_invite_expired(code_doc.get("expires_at")):
        raise HTTPException(status_code=400, detail="Invite code expired")
    return code_doc


async def create_bot_invite_session_user(*, invite_doc: Dict[str, Any], bot_name: str) -> Dict[str, Any]:
    now = now_iso()
    handle = await build_unique_user_handle(bot_name)
    user_doc = {
        "id": new_id(),
        "email": f"bot-invite-{invite_doc['id']}@agents.thesparkpit.local",
        "handle": handle,
        "password_hash": hash_password(secrets.token_urlsafe(32)),
        "role": "member",
        "membership_status": "pending",
        "membership_plan": None,
        "membership_expires_at": None,
        "joined_at": None,
        "membership_activated_at": None,
        "stripe_customer_id": None,
        "stripe_session_id": None,
        "stripe_session_status": None,
        "reputation": {
            "bounties_claimed": 0,
            "bounties_submitted": 0,
            "bounties_approved": 0,
            "completion_rate": 0.0,
        },
        "account_source": "bot_invite_claim",
        "principal_type": "bot_operator_session",
        "active_bot_id": None,
        "origin_invite_code_id": invite_doc["id"],
        "created_at": now,
        "updated_at": now,
    }
    await db.users.insert_one(user_doc)
    created = sanitize_doc(user_doc)
    created.pop("password_hash", None)
    return created


async def create_public_bot_entry_session_user(*, bot_name: str, operator_handle: Optional[str] = None) -> Dict[str, Any]:
    now = now_iso()
    normalized_operator_handle = normalize_bot_invite_text(operator_handle, max_length=80)
    handle = await build_unique_user_handle(normalized_operator_handle or bot_name)
    user_doc = {
        "id": new_id(),
        "email": f"bot-entry-{uuid.uuid4().hex[:16]}@agents.thesparkpit.local",
        "handle": handle,
        "password_hash": hash_password(secrets.token_urlsafe(32)),
        "role": "member",
        "membership_status": "pending",
        "membership_plan": None,
        "membership_expires_at": None,
        "joined_at": None,
        "membership_activated_at": None,
        "stripe_customer_id": None,
        "stripe_session_id": None,
        "stripe_session_status": None,
        "reputation": {
            "bounties_claimed": 0,
            "bounties_submitted": 0,
            "bounties_approved": 0,
            "completion_rate": 0.0,
        },
        "account_source": "bot_public_entry",
        "principal_type": "bot_operator_session",
        "active_bot_id": None,
        "operator_handle": normalized_operator_handle,
        "created_at": now,
        "updated_at": now,
    }
    await db.users.insert_one(user_doc)
    created = sanitize_doc(user_doc)
    created.pop("password_hash", None)
    return created


async def create_bot_invite_code_doc(
    *,
    created_by_user_id: Optional[str],
    purchased_by_user_id: Optional[str] = None,
    created_source: str,
    expires_at: Optional[str] = None,
    label: Optional[str] = None,
    note: Optional[str] = None,
    payment_transaction_id: Optional[str] = None,
    allowed_room_ids: Optional[List[str]] = None,
    allowed_channel_ids: Optional[List[str]] = None,
    bot_name: Optional[str] = None,
    bot_type: Optional[str] = None,
    bot_description: Optional[str] = None,
    owner_note: Optional[str] = None,
) -> Dict[str, Any]:
    now = now_iso()
    invite_doc = {
        "id": new_id(),
        "code": await generate_unique_invite_code("bot"),
        "invite_type": "bot",
        "max_uses": 1,
        "uses": 0,
        "created_by_user_id": created_by_user_id,
        "purchased_by_user_id": purchased_by_user_id,
        "created_source": created_source,
        "payment_transaction_id": payment_transaction_id,
        "allowed_room_ids": normalize_scope_ids(allowed_room_ids),
        "allowed_channel_ids": normalize_scope_ids(allowed_channel_ids),
        "expires_at": normalize_invite_expiration_date(expires_at) or get_default_bot_invite_expiration_date(),
        "label": label.strip() if label else None,
        "note": note.strip() if note else None,
        "bot_name": normalize_bot_invite_text(bot_name, max_length=80),
        "bot_type": normalize_bot_type(bot_type),
        "bot_description": normalize_bot_invite_text(bot_description, max_length=280),
        "owner_note": normalize_bot_invite_text(owner_note, max_length=280),
        "claimed_by": [],
        "claimed_by_user_id": None,
        "claimed_bot_id": None,
        "claimed_at": None,
        "revoked_at": None,
        "revoked_by_user_id": None,
        "created_at": now,
        "updated_at": now,
    }
    await db.invite_codes.insert_one(invite_doc)
    return sanitize_doc(invite_doc)


async def ensure_bot_invite_for_transaction(transaction: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not transaction:
        return None
    transaction = sanitize_doc(dict(transaction))
    metadata = transaction.get("metadata") or {}
    if metadata.get("purpose") != "bot_invite":
        return None

    existing_invite_id = metadata.get("generated_invite_id") or transaction.get("generated_invite_id")
    if existing_invite_id:
        existing_invite = await db.invite_codes.find_one({"id": existing_invite_id}, {"_id": 0})
        if existing_invite:
            return sanitize_doc(existing_invite)

    invite_doc = await create_bot_invite_code_doc(
        created_by_user_id=transaction.get("user_id"),
        purchased_by_user_id=transaction.get("user_id"),
        created_source="purchase",
        payment_transaction_id=transaction.get("id"),
        label="Purchased bot invite",
        note="Generated from Stripe bot invite purchase",
    )
    await db.payment_transactions.update_one(
        {"id": transaction["id"]},
        {
            "$set": {
                "generated_invite_id": invite_doc["id"],
                "updated_at": now_iso(),
                "metadata.generated_invite_id": invite_doc["id"],
            }
        },
    )
    return invite_doc


def get_request_ip(request: Request) -> Optional[str]:
    # Prefer X-Real-IP set by nginx to $remote_addr — cannot be spoofed by clients.
    # X-Forwarded-For uses $proxy_add_x_forwarded_for (appends real IP to any
    # client-supplied header), making the first element spoofable for rate limiting.
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host
    return None


def get_request_meta(request: Request) -> Dict[str, Any]:
    return {
        "ip": get_request_ip(request),
        "user_agent": request.headers.get("user-agent"),
        "ts": now_iso(),
    }


def normalize_csp_reports(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return []

    items: List[Dict[str, Any]] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        report = entry.get("body") if isinstance(entry.get("body"), dict) else entry.get("csp-report")
        if not isinstance(report, dict):
            report = entry
        normalized = {
            "document_uri": report.get("document-uri"),
            "referrer": report.get("referrer"),
            "violated_directive": report.get("violated-directive"),
            "effective_directive": report.get("effective-directive"),
            "original_policy": report.get("original-policy"),
            "disposition": report.get("disposition"),
            "blocked_uri": report.get("blocked-uri"),
            "status_code": report.get("status-code"),
            "source_file": report.get("source-file"),
            "line_number": report.get("line-number"),
            "column_number": report.get("column-number"),
            "script_sample": report.get("script-sample"),
            "report_type": entry.get("type"),
        }
        if any(value is not None for value in normalized.values()):
            items.append(normalized)
    return items


def mask_secret_value(value: Optional[str], reveal_prefix: int = 7, reveal_suffix: int = 4) -> Optional[str]:
    if not value:
        return None
    if len(value) <= reveal_prefix + reveal_suffix:
        return "*" * len(value)
    return f"{value[:reveal_prefix]}***{value[-reveal_suffix:]}"


async def get_stripe_config_doc() -> Optional[Dict[str, Any]]:
    config_doc = await db.payment_settings.find_one({"id": "stripe"}, {"_id": 0})
    return sanitize_doc(config_doc) if config_doc else None


def decrypt_optional_secret(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        return decrypt_secret(value)
    except Exception:
        logger.warning("Failed to decrypt stored Stripe secret")
        return None


async def get_runtime_stripe_config() -> Dict[str, Any]:
    config_doc = await get_stripe_config_doc()
    publishable_key = ((config_doc or {}).get("publishable_key") or ENV_STRIPE_PUBLISHABLE_KEY or "").strip()
    secret_key = (
        decrypt_optional_secret((config_doc or {}).get("secret_key_encrypted"))
        or ENV_STRIPE_SECRET_KEY
        or ""
    ).strip()
    webhook_secret = (
        decrypt_optional_secret((config_doc or {}).get("webhook_secret_encrypted"))
        or ENV_STRIPE_WEBHOOK_SECRET
        or ""
    ).strip()
    membership_monthly_price_id = (
        (config_doc or {}).get("membership_monthly_price_id")
        or ENV_STRIPE_MEMBERSHIP_MONTHLY_PRICE_ID
        or ""
    ).strip()
    membership_yearly_price_id = (
        (config_doc or {}).get("membership_yearly_price_id")
        or ENV_STRIPE_MEMBERSHIP_YEARLY_PRICE_ID
        or ""
    ).strip()
    bot_invite_price_id = (
        (config_doc or {}).get("bot_invite_price_id")
        or ENV_STRIPE_BOT_INVITE_PRICE_ID
        or ""
    ).strip()
    return {
        "publishable_key": publishable_key,
        "secret_key": secret_key,
        "webhook_secret": webhook_secret,
        "membership_monthly_price_id": membership_monthly_price_id,
        "membership_yearly_price_id": membership_yearly_price_id,
        "bot_invite_price_id": bot_invite_price_id,
        "credentials_configured": bool(publishable_key and secret_key and webhook_secret),
        "config_doc": config_doc,
    }


async def get_stripe_config_status_payload() -> Dict[str, Any]:
    runtime_config = await get_runtime_stripe_config()
    config_doc = runtime_config.get("config_doc") or {}
    updated_by = None
    updated_by_user_id = config_doc.get("updated_by_user_id")
    if updated_by_user_id:
        user_doc = await db.users.find_one(
            {"id": updated_by_user_id},
            {"_id": 0, "id": 1, "email": 1, "handle": 1},
        )
        updated_by = sanitize_doc(user_doc) if user_doc else {"id": updated_by_user_id}
    last_tested_by = None
    last_tested_by_user_id = config_doc.get("last_tested_by_user_id")
    if last_tested_by_user_id:
        user_doc = await db.users.find_one(
            {"id": last_tested_by_user_id},
            {"_id": 0, "id": 1, "email": 1, "handle": 1},
        )
        last_tested_by = sanitize_doc(user_doc) if user_doc else {"id": last_tested_by_user_id}
    webhook_state = await db.ops_state.find_one({"id": "stripe_webhook"}, {"_id": 0, "last_received_at": 1})
    webhook_state = sanitize_doc(webhook_state) if webhook_state else None
    return {
        "publishable_key": runtime_config["publishable_key"] or None,
        "secret_key_masked": mask_secret_value(runtime_config["secret_key"]),
        "webhook_secret_masked": mask_secret_value(runtime_config["webhook_secret"]),
        "membership_monthly_price_id": runtime_config["membership_monthly_price_id"] or None,
        "membership_yearly_price_id": runtime_config["membership_yearly_price_id"] or None,
        "bot_invite_price_id": runtime_config["bot_invite_price_id"] or None,
        "credentials_configured": runtime_config["credentials_configured"],
        "membership_monthly_price_configured": bool(runtime_config["membership_monthly_price_id"]),
        "membership_yearly_price_configured": bool(runtime_config["membership_yearly_price_id"]),
        "membership_price_configured": bool(
            runtime_config["membership_monthly_price_id"] and runtime_config["membership_yearly_price_id"]
        ),
        "bot_invite_price_configured": bool(runtime_config["bot_invite_price_id"]),
        "updated_at": config_doc.get("updated_at"),
        "updated_by": updated_by,
        "last_tested_at": config_doc.get("last_tested_at"),
        "last_test_ok": config_doc.get("last_test_ok"),
        "last_test_message": config_doc.get("last_test_message"),
        "last_test_account_id": config_doc.get("last_test_account_id"),
        "last_test_livemode": config_doc.get("last_test_livemode"),
        "last_test_membership_monthly_price_ok": config_doc.get("last_test_membership_monthly_price_ok"),
        "last_test_membership_yearly_price_ok": config_doc.get("last_test_membership_yearly_price_ok"),
        "last_test_bot_invite_price_ok": config_doc.get("last_test_bot_invite_price_ok"),
        "last_tested_by": last_tested_by,
        "stripe_webhook_last_received": (webhook_state or {}).get("last_received_at"),
        "source": {
            "publishable_key": "database" if config_doc.get("publishable_key") else ("env" if ENV_STRIPE_PUBLISHABLE_KEY else "unset"),
            "secret_key": "database" if config_doc.get("secret_key_encrypted") else ("env" if ENV_STRIPE_SECRET_KEY else "unset"),
            "webhook_secret": "database" if config_doc.get("webhook_secret_encrypted") else ("env" if ENV_STRIPE_WEBHOOK_SECRET else "unset"),
            "membership_monthly_price_id": "database" if config_doc.get("membership_monthly_price_id") else ("env" if ENV_STRIPE_MEMBERSHIP_MONTHLY_PRICE_ID else "unset"),
            "membership_yearly_price_id": "database" if config_doc.get("membership_yearly_price_id") else ("env" if ENV_STRIPE_MEMBERSHIP_YEARLY_PRICE_ID else "unset"),
            "bot_invite_price_id": "database" if config_doc.get("bot_invite_price_id") else ("env" if ENV_STRIPE_BOT_INVITE_PRICE_ID else "unset"),
        },
    }


async def can_access_room(user: Dict[str, Any], room_id: str) -> bool:
    if user.get("role") == "admin":
        return True
    room = await db.rooms.find_one({"id": room_id}, {"_id": 0, "is_public": 1})
    if room and room.get("is_public"):
        return True
    user_membership, bot_membership = await get_room_membership_state(user, room_id)
    return bool(user_membership or bot_membership)


async def can_manage_room(user: Dict[str, Any], room_id: str) -> bool:
    if user.get("role") == "admin":
        return True
    membership = await db.room_memberships.find_one(
        {"room_id": room_id, "member_type": "user", "member_id": user["id"]}
    )
    membership = sanitize_doc(membership) if membership else None
    return bool(membership and membership.get("role") in ["owner", "moderator"])


def lobby_post_view(user_doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not user_doc:
        return None
    return {
        "id": user_doc.get("id"),
        "handle": user_doc.get("handle"),
        "role": user_doc.get("role"),
        "membership_status": user_doc.get("membership_status"),
        "actor_type": "human",
    }


def lobby_bot_view(bot_doc: Optional[Dict[str, Any]], operator_doc: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    if not bot_doc:
        return None
    return {
        "id": bot_doc.get("id"),
        "handle": bot_doc.get("handle") or bot_doc.get("name"),
        "name": bot_doc.get("name"),
        "role": "bot",
        "bot_type": bot_doc.get("bot_type"),
        "membership_status": None,
        "actor_type": "bot",
        "operator": lobby_post_view(operator_doc) if operator_doc else None,
    }


def normalize_lobby_post_type(value: str) -> str:
    normalized = (value or "post").strip().lower()
    if normalized not in {"post", "question", "summary"}:
        raise HTTPException(status_code=400, detail="Invalid lobby post type")
    return normalized


def normalize_lobby_tags(tags: Optional[List[str]]) -> List[str]:
    cleaned = []
    for tag in tags or []:
        normalized = re.sub(r"[^a-z0-9 -]", "", (tag or "").strip().lower()).replace(" ", "-")
        normalized = normalized.strip("-")
        if normalized and normalized not in cleaned:
            cleaned.append(normalized[:24])
    return cleaned[:5]


def build_room_slug_from_text(text: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower())
    normalized = normalized.strip("-")
    return normalized[:48] or f"room-{new_id()[:8]}"


def build_room_title_from_post(body: str) -> str:
    words = [(word or "").strip() for word in (body or "").split() if word.strip()]
    title = " ".join(words[:8]).strip()
    return title[:80] or "Lobby thread"


def normalize_research_status(value: Optional[str]) -> str:
    normalized = (value or "active").strip().lower()
    if normalized not in {"active", "paused", "concluded"}:
        raise HTTPException(status_code=400, detail="Invalid research status")
    return normalized


def normalize_research_cadence(value: Optional[str]) -> str:
    try:
        return normalize_participation_cadence(value)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Invalid research participation cadence") from error


def normalize_research_items(items: Optional[List[str]], field_name: str, limit: int = 12) -> List[str]:
    cleaned = []
    for raw in items or []:
        value = (raw or "").strip()
        if not value:
            continue
        if moderate_text(value):
            raise HTTPException(status_code=400, detail=f"Invalid research {field_name}")
        if value not in cleaned:
            cleaned.append(value[:280])
    return cleaned[:limit]


def normalize_research_text(value: Optional[str], field_name: str, limit: int = 4000) -> str:
    cleaned = (value or "").strip()
    moderation_error = moderate_text(cleaned) if cleaned else None
    if moderation_error:
        raise HTTPException(status_code=400, detail=f"Invalid research {field_name}")
    return cleaned[:limit]


def normalize_bot_profile_text(value: Optional[str], field_name: str, limit: int = 1200) -> str:
    cleaned = (value or "").strip()
    moderation_error = moderate_text(cleaned) if cleaned else None
    if moderation_error:
        raise HTTPException(status_code=400, detail=f"Invalid bot {field_name}")
    return cleaned[:limit]


def normalize_research_outputs(items: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    cleaned: List[Dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        resource_id = (item.get("resource_id") or "").strip()
        output_type = (item.get("type") or "").strip().lower()
        title = (item.get("title") or "").strip()
        source_text = (item.get("source_text") or "").strip()
        if not resource_id or output_type not in {"task", "bounty"} or not title:
            continue
        cleaned.append(
            {
                "id": item.get("id") or new_id(),
                "type": output_type,
                "resource_id": resource_id,
                "title": title[:160],
                "status": (item.get("status") or "").strip()[:40],
                "source_text": source_text[:280],
                "created_at": item.get("created_at") or now_iso(),
                "created_by_user_id": (item.get("created_by_user_id") or "").strip(),
                "created_by_actor_type": (item.get("created_by_actor_type") or "").strip()[:16],
                "created_by_actor_id": (item.get("created_by_actor_id") or "").strip()[:64],
                "operator_user_id": (item.get("operator_user_id") or "").strip(),
            }
        )
    return cleaned[:24]


def build_research_handoff_title(source_text: str, fallback_prefix: str) -> str:
    normalized = re.sub(r"\s+", " ", (source_text or "").strip())
    if not normalized:
        return fallback_prefix
    return normalized[:120]


async def get_research_workspace_or_404(slug: str, user: Dict[str, Any]) -> Dict[str, Any]:
    room = await db.rooms.find_one({"slug": slug})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    room = sanitize_doc(room)
    if not await can_access_room(user, room["id"]):
        raise HTTPException(status_code=403, detail="Join the room first")
    if (room.get("source") or {}).get("kind") != "research_project":
        raise HTTPException(status_code=400, detail="Room is not a research workspace")
    return room


def lobby_post_is_archived(post: Dict[str, Any], archived_before_iso: str) -> bool:
    return bool(
        post.get("created_at", "") < archived_before_iso
        and not post.get("reply_count")
        and not len(post.get("saved_by_user_ids") or [])
        and not post.get("promoted_room_id")
        and not post.get("pinned")
    )


async def get_lobby_post_or_404(post_id: str) -> Dict[str, Any]:
    post = await db.lobby_posts.find_one({"id": post_id})
    if not post:
        raise HTTPException(status_code=404, detail="Lobby post not found")
    return sanitize_doc(post)


async def enrich_lobby_posts(
    posts: List[Dict[str, Any]],
    current_user_id: str,
    include_replies: bool = True,
) -> List[Dict[str, Any]]:
    if not posts:
        return []

    user_ids = {
        user_id
        for post in posts
        for user_id in [post.get("author_user_id"), post.get("operator_user_id")]
        if user_id
    }
    bot_ids = {
        bot_id
        for post in posts
        for bot_id in [post.get("author_bot_id"), post.get("actor_id") if post.get("actor_type") == "bot" else None]
        if bot_id
    }
    room_ids = {post.get("linked_room_id") for post in posts if post.get("linked_room_id")}
    room_ids.update({post.get("promoted_room_id") for post in posts if post.get("promoted_room_id")})
    bounty_ids = {post.get("linked_bounty_id") for post in posts if post.get("linked_bounty_id")}
    post_ids = [post["id"] for post in posts]

    replies_by_post: Dict[str, List[Dict[str, Any]]] = {}
    if include_replies:
        replies = await db.lobby_post_replies.find(
            {"post_id": {"$in": post_ids}},
            {"_id": 0},
        ).sort("created_at", 1).to_list(500)
        for reply in replies:
            replies_by_post.setdefault(reply["post_id"], []).append(reply)
            if reply.get("author_user_id"):
                user_ids.add(reply["author_user_id"])
            if reply.get("operator_user_id"):
                user_ids.add(reply["operator_user_id"])
            if reply.get("author_bot_id"):
                bot_ids.add(reply["author_bot_id"])
            if reply.get("actor_type") == "bot" and reply.get("actor_id"):
                bot_ids.add(reply["actor_id"])

    users = {
        user_doc["id"]: sanitize_doc(user_doc)
        for user_doc in await db.users.find({"id": {"$in": list(user_ids)}}).to_list(500)
    }
    bots = {
        bot_doc["id"]: sanitize_bot(bot_doc)
        for bot_doc in await db.bots.find({"id": {"$in": list(bot_ids)}}).to_list(500)
    }
    rooms = {
        room_doc["id"]: sanitize_doc(room_doc)
        for room_doc in await db.rooms.find({"id": {"$in": list(room_ids)}}).to_list(500)
    }
    bounties = {
        bounty_doc["id"]: sanitize_doc(bounty_doc)
        for bounty_doc in await db.bounties.find({"id": {"$in": list(bounty_ids)}}).to_list(500)
    }

    enriched_items = []
    for post in posts:
        saved_by_user_ids = post.get("saved_by_user_ids") or []
        author = (
            lobby_bot_view(
                bots.get(post.get("author_bot_id") or post.get("actor_id")),
                users.get(post.get("operator_user_id")),
            )
            if post.get("actor_type") == "bot" or post.get("author_bot_id")
            else lobby_post_view(users.get(post.get("author_user_id") or post.get("actor_id")))
        )
        item = {
            **post,
            "author": author,
            "linked_room": rooms.get(post.get("linked_room_id")) if post.get("linked_room_id") else None,
            "linked_bounty": bounties.get(post.get("linked_bounty_id")) if post.get("linked_bounty_id") else None,
            "promoted_room": rooms.get(post.get("promoted_room_id")) if post.get("promoted_room_id") else None,
            "promoted": bool(post.get("promoted_room_id")),
            "saved_by_me": current_user_id in saved_by_user_ids,
            "save_count": len(saved_by_user_ids),
        }
        item.pop("saved_by_user_ids", None)
        item["replies"] = [
            {
                **reply,
                "author": (
                    lobby_bot_view(
                        bots.get(reply.get("author_bot_id") or reply.get("actor_id")),
                        users.get(reply.get("operator_user_id")),
                    )
                    if reply.get("actor_type") == "bot" or reply.get("author_bot_id")
                    else lobby_post_view(users.get(reply.get("author_user_id") or reply.get("actor_id")))
                ),
            }
            for reply in replies_by_post.get(post["id"], [])
        ]
        enriched_items.append(item)
    return enriched_items


async def log_task_event(
    task_id: str,
    room_id: str,
    event_type: str,
    actor_user_id: str,
    payload: Optional[Dict[str, Any]] = None,
    actor_type: str = "human",
    actor_id: Optional[str] = None,
    operator_user_id: Optional[str] = None,
):
    event_doc = {
        "id": new_id(),
        "task_id": task_id,
        "room_id": room_id,
        "event_type": event_type,
        "actor_user_id": actor_user_id,
        "actor_type": actor_type,
        "actor_id": actor_id or actor_user_id,
        "operator_user_id": operator_user_id,
        "payload": payload or {},
        "created_at": now_iso(),
    }
    await db.task_events.insert_one(event_doc)
    return sanitize_doc(event_doc)


async def log_room_event(
    room_id: str,
    event_type: str,
    actor_user_id: str,
    payload: Optional[Dict[str, Any]] = None,
    actor_type: str = "human",
    actor_id: Optional[str] = None,
    operator_user_id: Optional[str] = None,
):
    event_doc = {
        "id": new_id(),
        "room_id": room_id,
        "event_type": event_type,
        "actor_user_id": actor_user_id,
        "actor_type": actor_type,
        "actor_id": actor_id or actor_user_id,
        "operator_user_id": operator_user_id,
        "payload": payload or {},
        "created_at": now_iso(),
    }
    await db.room_events.insert_one(event_doc)
    return sanitize_doc(event_doc)


async def update_reputation(user_id: str, field: str):
    user = await db.users.find_one({"id": user_id})
    if not user:
        return
    rep = user.get("reputation", {
        "bounties_claimed": 0,
        "bounties_submitted": 0,
        "bounties_approved": 0,
        "completion_rate": 0.0,
    })
    rep[field] = rep.get(field, 0) + 1
    claimed = rep.get("bounties_claimed", 0)
    approved = rep.get("bounties_approved", 0)
    rep["completion_rate"] = round((approved / claimed) if claimed else 0.0, 3)
    await db.users.update_one({"id": user_id}, {"$set": {"reputation": rep, "updated_at": now_iso()}})


async def activate_membership(
    user_id: str,
    session_id: str,
    customer_id: Optional[str] = None,
    membership_plan: str = "monthly",
):
    existing = await db.users.find_one({"id": user_id}, {"_id": 0, "membership_expires_at": 1})
    current_expiration = parse_iso_datetime((existing or {}).get("membership_expires_at")) if existing else None
    base_time = current_expiration if current_expiration and current_expiration > datetime.now(timezone.utc) else datetime.now(timezone.utc)
    membership_plan = normalize_membership_plan(membership_plan)
    updates = {
        "membership_status": "active",
        "membership_plan": membership_plan,
        "membership_expires_at": compute_membership_expiration(base_time, membership_plan),
        "joined_at": now_iso(),
        "membership_activated_at": now_iso(),
        "stripe_session_id": session_id,
        "stripe_session_status": "paid",
        "updated_at": now_iso(),
    }
    if customer_id:
        updates["stripe_customer_id"] = customer_id
    await db.users.update_one({"id": user_id}, {"$set": updates})


class AuthResponse(BaseModel):
    token: Optional[str] = None
    user: Dict[str, Any]


class UserCreate(BaseModel):
    email: str
    handle: str
    password: str


class UserLogin(BaseModel):
    email: str
    password: str


def normalize_registration_email(value: str) -> str:
    return (value or "").strip().lower()


def normalize_registration_handle(value: str) -> str:
    return (value or "").strip()


def validate_registration_password(password: str) -> str:
    normalized = password or ""
    if len(normalized) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    return normalized


class UserUpdate(BaseModel):
    handle: Optional[str] = None


class InviteClaim(BaseModel):
    code: str


class InviteCodeCreate(BaseModel):
    code: Optional[str] = None
    max_uses: int = 1
    expires_at: Optional[str] = None
    invite_type: str = "membership"
    label: Optional[str] = None
    note: Optional[str] = None
    allowed_room_ids: List[str] = []
    allowed_channel_ids: List[str] = []
    bot_name: Optional[str] = None
    bot_type: Optional[str] = None
    bot_description: Optional[str] = None
    owner_note: Optional[str] = None


class BotInviteClaim(BaseModel):
    code: str
    bot_name: Optional[str] = None
    bot_type: Optional[str] = None
    description: Optional[str] = None


class PublicBotEntryCreate(BaseModel):
    bot_name: str
    description: str
    bot_type: Optional[str] = None
    operator_handle: Optional[str] = None


class BotEntryRecoveryCreate(BaseModel):
    bot_handle: str
    recovery_code: str


class BotInviteUpdate(BaseModel):
    bot_name: Optional[str] = None
    bot_type: Optional[str] = None
    bot_description: Optional[str] = None
    owner_note: Optional[str] = None
    expires_at: Optional[str] = None


class RoomSource(BaseModel):
    kind: str
    post_id: Optional[str] = None
    launched_from: Optional[str] = None


class RoomResearchSeed(BaseModel):
    question: Optional[str] = ""
    summary: Optional[str] = ""
    final_summary: Optional[str] = ""
    key_sources: List[str] = []
    findings: List[str] = []
    open_questions: List[str] = []
    next_actions: List[str] = []
    status: str = "active"
    template: Optional[str] = None
    visibility: Optional[str] = None
    next_step: Optional[str] = ""
    recommended_next_step: Optional[str] = ""
    note: Optional[str] = ""
    bot_directive: Optional[str] = ""
    bot_return_policy: Optional[str] = ""
    participation_cadence: Optional[str] = "daily"
    outputs: List[Dict[str, Any]] = []


class RoomResearchUpdate(BaseModel):
    question: Optional[str] = None
    summary: Optional[str] = None
    final_summary: Optional[str] = None
    key_sources: Optional[List[str]] = None
    findings: Optional[List[str]] = None
    open_questions: Optional[List[str]] = None
    next_actions: Optional[List[str]] = None
    status: Optional[str] = None
    recommended_next_step: Optional[str] = None
    note: Optional[str] = None
    bot_directive: Optional[str] = None
    bot_return_policy: Optional[str] = None
    participation_cadence: Optional[str] = None


class RoomResearchListItemCreate(BaseModel):
    field: str
    value: str


class ResearchPromoteTaskCreate(BaseModel):
    source_text: str
    title: Optional[str] = None
    description: Optional[str] = None


class ResearchPromoteBountyCreate(BaseModel):
    source_text: str
    title: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = []


class LobbyPostCreate(BaseModel):
    type: str = "post"
    body: str
    tags: List[str] = []
    linked_room_id: Optional[str] = None
    linked_bounty_id: Optional[str] = None


class LobbyPostReplyCreate(BaseModel):
    body: str


class RoomCreate(BaseModel):
    slug: str
    title: str
    is_public: bool = True
    description: Optional[str] = ""
    source: Optional[RoomSource] = None
    research: Optional[RoomResearchSeed] = None


class ChannelCreate(BaseModel):
    slug: str
    title: str
    type: str = "chat"


class MessageCreate(BaseModel):
    content: str


class ActiveBotSelection(BaseModel):
    bot_id: Optional[str] = None


class BotCreate(BaseModel):
    name: str
    handle: Optional[str] = None
    bio: str
    bot_type: Optional[str] = None
    skills: List[str] = []
    model_stack: Optional[List[str]] = []
    connect_url: Optional[str] = ""
    status: str = "offline"
    operating_directive: Optional[str] = ""
    return_policy: Optional[str] = ""


class BotUpdate(BaseModel):
    name: Optional[str] = None
    bio: Optional[str] = None
    bot_type: Optional[str] = None
    skills: Optional[List[str]] = None
    model_stack: Optional[List[str]] = None
    connect_url: Optional[str] = None
    status: Optional[str] = None
    operating_directive: Optional[str] = None
    return_policy: Optional[str] = None


class BotWebhookCreate(BaseModel):
    url: str
    events: List[str] = []
    enabled: bool = True
    label: Optional[str] = None


class BotWebhookUpdate(BaseModel):
    url: Optional[str] = None
    events: Optional[List[str]] = None
    enabled: Optional[bool] = None
    label: Optional[str] = None


class BountyCreate(BaseModel):
    title: str
    description: str
    tags: List[str] = []
    reward_amount: Optional[float] = None
    reward_currency: Optional[str] = None
    room_id: Optional[str] = None
    due_at: Optional[str] = None


class BountyUpdateCreate(BaseModel):
    type: str = "comment"
    content: str


class BountyStatusUpdate(BaseModel):
    status: str


class TaskCreate(BaseModel):
    room_id: str
    title: str
    description: Optional[str] = ""
    priority: str = "normal"
    tags: List[str] = []


class TaskAssign(BaseModel):
    assignee_user_id: str


class TaskStateUpdate(BaseModel):
    state: str
    note: Optional[str] = None


class TaskArtifactCreate(BaseModel):
    kind: str = "note"
    title: str
    url: Optional[str] = None
    body: Optional[str] = None
    metadata: Dict[str, Any] = {}


class ProposalResource(BaseModel):
    title: str
    url: str


class TaskProposalCreate(BaseModel):
    title: str
    summary: str
    steps: List[str] = []
    risks: List[str] = []
    resources: List[ProposalResource] = []


class TaskVoteCreate(BaseModel):
    proposal_id: str
    vote: str


class RoomMemorySummarizeRequest(BaseModel):
    note: Optional[str] = None


class CheckoutSessionCreate(BaseModel):
    origin_url: str
    purpose: str = "membership"
    membership_plan: Optional[str] = "monthly"


class AdminStripeConfigUpdate(BaseModel):
    publishable_key: Optional[str] = None
    secret_key: Optional[str] = None
    webhook_secret: Optional[str] = None
    membership_monthly_price_id: Optional[str] = None
    membership_yearly_price_id: Optional[str] = None
    bot_invite_price_id: Optional[str] = None


class BotHandshakeVerify(BaseModel):
    challenge: str
    signature: str
    capabilities: Optional[Dict[str, Any]] = None
    allowed_room_ids: List[str] = []
    allowed_channel_ids: List[str] = []

class BotTokenRefresh(BaseModel):
    refresh_token: str


class ModerationResolve(BaseModel):
    status: str
    notes: Optional[str] = None


async def issue_bot_tokens(bot_id: str, scopes: Dict[str, List[str]]) -> Dict[str, Any]:
    bot_token = create_bot_token(bot_id, scopes)
    refresh_token = new_refresh_token()
    expires_at = now_epoch() + (BOT_REFRESH_TOKEN_DAYS * 24 * 60 * 60)
    refresh_doc = {
        "id": new_id(),
        "bot_id": bot_id,
        "token_hash": hash_refresh_token(refresh_token),
        "expires_at": expires_at,
        "created_at": now_iso(),
        "last_used_at": None,
    }
    await db.bot_refresh_tokens.insert_one(refresh_doc)
    return {"bot_token": bot_token, "refresh_token": refresh_token, "expires_in_days": BOT_TOKEN_EXPIRE_DAYS}


class BotMessageCreate(BaseModel):
    channel_id: str
    content: str


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Dict[str, Any]:
    token = extract_bearer_token(credentials) or extract_cookie_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") == "bot":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bot token not allowed")
        user_id = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if user.get("is_banned"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account suspended")
    user = await refresh_user_membership_state(user)
    return await hydrate_authenticated_user(user)


async def get_optional_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[Dict[str, Any]]:
    token = extract_bearer_token(credentials) or extract_cookie_token(request)
    if not token:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") == "bot":
            return None
        user_id = payload.get("sub")
    except JWTError:
        return None
    user = await db.users.find_one({"id": user_id})
    if not user or user.get("is_banned"):
        return None
    user = await refresh_user_membership_state(user)
    return await hydrate_authenticated_user(user)


async def require_active_member(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if user.get("membership_status") != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Membership not active")
    return user


async def require_conversation_participant(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if not can_user_post_conversations(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conversation access is unavailable for this session",
        )
    if is_bot_session_user(user) and not user.get("active_bot"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bot identity unavailable for this session")
    return user


async def require_registered_user(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return user


async def require_admin(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


async def get_current_bot(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Dict[str, Any]:
    token = extract_bearer_token(credentials) or extract_cookie_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bot token")
    if payload.get("type") != "bot":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bot token required")
    bot_id = payload.get("sub")
    bot = await db.bots.find_one({"id": bot_id})
    if not bot:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bot not found")
    if bot.get("is_banned"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bot suspended")
    revoked_at = bot.get("bot_token_revoked_at")
    token_iat = payload.get("iat")
    if revoked_at and token_iat and int(token_iat) <= int(revoked_at):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bot token revoked")
    bot = sanitize_doc(bot)
    bot["scopes"] = payload.get("scopes", {})
    return bot


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, channel_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.setdefault(channel_id, []).append(websocket)

    def disconnect(self, channel_id: str, websocket: WebSocket):
        if channel_id in self.active_connections:
            self.active_connections[channel_id] = [
                conn for conn in self.active_connections[channel_id] if conn != websocket
            ]

    async def broadcast(self, channel_id: str, message: Dict[str, Any]):
        for connection in self.active_connections.get(channel_id, []):
            await connection.send_json(message)


manager = ConnectionManager()


@api_router.get("/")
async def root():
    return {"message": "Spark Pit API online"}


@api_router.get("/auth/csrf")
async def get_csrf():
    token = get_csrf_token_value()
    response = JSONResponse(content={"csrf_token": token})
    csrf_settings = {**get_cookie_settings(), "httponly": False}
    response.set_cookie("spark_csrf", token, **csrf_settings)
    return response


@api_router.post("/auth/register", response_model=AuthResponse)
async def register(user: UserCreate, request: Request, response: Response):
    request_ip = get_request_ip(request) or "unknown"
    await enforce_rate_limit(
        request,
        key=f"rl:auth:register:ip:{request_ip}",
        limit=get_rate_limit("RATE_LIMIT_AUTH_REGISTER_PER_HOUR", 10),
        window_seconds=60 * 60,
        actor_type="anonymous",
        actor_id=request_ip,
        endpoint="/auth/register",
        detail="registration rate limit exceeded",
        error_detail="Too many registration attempts",
    )
    email = normalize_registration_email(user.email)
    handle = normalize_registration_handle(user.handle)
    password = validate_registration_password(user.password)
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    if not handle:
        raise HTTPException(status_code=400, detail="Handle is required")

    email_exists = await db.users.find_one({"email": email}, {"_id": 0, "id": 1})
    handle_exists = await db.users.find_one({"handle": handle}, {"_id": 0, "id": 1})
    if email_exists and handle_exists:
        raise HTTPException(status_code=400, detail="Email is already registered and handle is already in use")
    if email_exists:
        raise HTTPException(status_code=400, detail="Email is already registered")
    if handle_exists:
        raise HTTPException(status_code=400, detail="Handle is already in use")

    admin_count = await db.users.count_documents({"role": "admin"})
    if admin_count == 0:
        bootstrap_token = os.environ.get("ADMIN_BOOTSTRAP_TOKEN")
        allow_open_bootstrap = os.environ.get("ALLOW_BOOTSTRAP_ADMIN", "").lower() == "true"
        if bootstrap_token:
            provided_token = request.headers.get("X-Admin-Bootstrap")
            if not provided_token or not hmac.compare_digest(bootstrap_token, provided_token):
                raise HTTPException(status_code=403, detail="Admin bootstrap token required")
        elif not allow_open_bootstrap:
            raise HTTPException(status_code=403, detail="Admin bootstrap disabled")
    role = "admin" if admin_count == 0 else "member"
    membership_status = "active" if role == "admin" else "pending"
    now = now_iso()
    user_doc = {
        "id": new_id(),
        "email": email,
        "handle": handle,
        "password_hash": hash_password(password),
        "role": role,
        "membership_status": membership_status,
        "membership_plan": "admin" if membership_status == "active" else None,
        "membership_expires_at": None,
        "joined_at": now if membership_status == "active" else None,
        "membership_activated_at": now if membership_status == "active" else None,
        "stripe_customer_id": None,
        "stripe_session_id": None,
        "stripe_session_status": None,
        "reputation": {
            "bounties_claimed": 0,
            "bounties_submitted": 0,
            "bounties_approved": 0,
            "completion_rate": 0.0,
        },
        "created_at": now,
        "updated_at": now,
    }
    await db.users.insert_one(user_doc)
    user_doc = sanitize_doc(user_doc)
    token = create_token(user_doc)
    user_doc.pop("password_hash", None)
    csrf_token = get_csrf_token_value()
    set_auth_cookies(response, token, csrf_token)
    await log_audit(
        "auth.register",
        "user",
        user_doc["id"],
        payload={
            **get_request_meta(request),
            "success": True,
            "email": user_doc.get("email"),
            "membership_status": user_doc.get("membership_status"),
        },
    )
    return {"token": None, "user": user_doc}


@api_router.post("/auth/login", response_model=AuthResponse)
async def login(user: UserLogin, request: Request, response: Response):
    request_ip = get_request_ip(request) or "unknown"
    await enforce_rate_limit(
        request,
        key=f"rl:auth:login:ip:{request_ip}",
        limit=get_rate_limit("RATE_LIMIT_AUTH_LOGIN_PER_15_MIN", 25),
        window_seconds=15 * 60,
        actor_type="anonymous",
        actor_id=request_ip,
        endpoint="/auth/login",
        detail="login rate limit exceeded",
        error_detail="Too many login attempts",
    )
    # Per-email lockout: block after 10 consecutive failures regardless of source IP.
    # Key resets on successful login; expires automatically after 15 minutes.
    email_key = f"rl:auth:login:email:{user.email}"
    if redis_pool:
        try:
            failure_count = await redis_pool.get(email_key)
            if failure_count and int(failure_count) >= get_rate_limit("RATE_LIMIT_AUTH_LOCKOUT_THRESHOLD", 10):
                raise HTTPException(status_code=429, detail="Too many login attempts")
        except HTTPException:
            raise
        except Exception as error:
            logger.warning("Account lockout check error: %s", error)
    existing = await db.users.find_one({"email": user.email})
    if not existing or not verify_password(user.password, existing.get("password_hash", "")):
        request_meta = get_request_meta(request)
        failure_actor_id = existing.get("id") if existing else "unknown"
        failure_payload = {
            **request_meta,
            "success": False,
            "reason": "invalid_credentials",
            "email": user.email,
        }
        # Increment per-email failure counter.
        if redis_pool:
            try:
                count = await redis_pool.incr(email_key)
                if count == 1:
                    await redis_pool.expire(email_key, 15 * 60)
            except Exception as error:
                logger.warning("Account lockout increment error: %s", error)
        await log_security_event(
            "auth.login.failure",
            severity="medium",
            actor_type="anonymous",
            actor_id=failure_actor_id,
            route="/auth/login",
            payload=failure_payload,
        )
        await log_audit(
            "auth.login.failure",
            "anonymous",
            failure_actor_id,
            payload=failure_payload,
        )
        raise HTTPException(status_code=400, detail="Invalid credentials")
    existing = sanitize_doc(existing)
    # Clear per-email failure counter on successful login.
    if redis_pool:
        try:
            await redis_pool.delete(email_key)
        except Exception as error:
            logger.warning("Account lockout reset error: %s", error)
    token = create_token(existing)
    existing.pop("password_hash", None)
    csrf_token = get_csrf_token_value()
    set_auth_cookies(response, token, csrf_token)
    await log_audit(
        "auth.login.success",
        "user",
        existing["id"],
        payload={
            **get_request_meta(request),
            "success": True,
            "email": existing.get("email"),
        },
    )
    return {"token": None, "user": existing}


@api_router.post("/auth/logout")
async def logout(request: Request, response: Response):
    token = extract_cookie_token(request)
    auth_header = request.headers.get("Authorization", "")
    if not token and auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
    actor_type = "anonymous"
    actor_id = "unknown"
    if token:
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            if payload.get("type") != "bot":
                actor_type = "user"
                actor_id = payload.get("sub") or "unknown"
        except JWTError:
            actor_type = "anonymous"
            actor_id = "unknown"
    await log_audit(
        "auth.logout",
        actor_type,
        actor_id,
        payload={
            **get_request_meta(request),
            "success": True,
            "token_present": bool(token),
        },
    )
    clear_auth_cookies(response)
    return {"status": "ok"}


@api_router.post("/auth/invite/claim")
async def claim_invite(payload: InviteClaim, request: Request, user: Dict[str, Any] = Depends(get_current_user)):
    await enforce_rate_limit(
        request,
        key=f"rl:invite-claim:user:{user['id']}",
        limit=get_rate_limit("RATE_LIMIT_INVITE_CLAIMS_PER_HOUR", 10),
        window_seconds=60 * 60,
        actor_type="user",
        actor_id=user["id"],
        endpoint="/auth/invite/claim",
        detail="invite claim rate limit exceeded",
        error_detail="Too many invite claim attempts",
    )
    code_doc = await db.invite_codes.find_one({"code": payload.code})
    if not code_doc:
        await log_security_event(
            "invite.claim.failure",
            severity="medium",
            actor_type="user",
            actor_id=user["id"],
            route="/auth/invite/claim",
            payload={
                **get_request_meta(request),
                "reason": "invite_not_found",
                "code_preview": format_invite_code_preview(payload.code),
            },
        )
        raise HTTPException(status_code=404, detail="Invite code not found")
    code_doc = sanitize_doc(code_doc)
    normalized_expiration = normalize_invite_expiration_date(code_doc.get("expires_at"))
    if code_doc.get("expires_at") and not normalized_expiration:
        await log_security_event(
            "invite.claim.failure",
            severity="medium",
            actor_type="user",
            actor_id=user["id"],
            route="/auth/invite/claim",
            payload={
                **get_request_meta(request),
                "reason": "invite_expiration_invalid",
                "code_id": code_doc.get("id"),
                "code_preview": format_invite_code_preview(payload.code),
            },
        )
        raise HTTPException(status_code=400, detail="Invite expiration is invalid")
    if is_invite_expired(code_doc.get("expires_at")):
        await log_security_event(
            "invite.claim.failure",
            severity="medium",
            actor_type="user",
            actor_id=user["id"],
            route="/auth/invite/claim",
            payload={
                **get_request_meta(request),
                "reason": "invite_expired",
                "code_id": code_doc.get("id"),
                "code_preview": format_invite_code_preview(payload.code),
            },
        )
        raise HTTPException(status_code=400, detail="Invite code expired")
    if code_doc.get("uses", 0) >= code_doc.get("max_uses", 1):
        await log_security_event(
            "invite.claim.failure",
            severity="medium",
            actor_type="user",
            actor_id=user["id"],
            route="/auth/invite/claim",
            payload={
                **get_request_meta(request),
                "reason": "invite_exhausted",
                "code_id": code_doc.get("id"),
                "code_preview": format_invite_code_preview(payload.code),
            },
        )
        raise HTTPException(status_code=400, detail="Invite code exhausted")
    if normalize_invite_type(code_doc.get("invite_type")) != "membership":
        await log_security_event(
            "invite.claim.failure",
            severity="low",
            actor_type="user",
            actor_id=user["id"],
            route="/auth/invite/claim",
            payload={
                **get_request_meta(request),
                "reason": "invite_wrong_type",
                "code_id": code_doc.get("id"),
                "code_preview": format_invite_code_preview(payload.code),
            },
        )
        raise HTTPException(status_code=400, detail="This code must be redeemed from the bot invite entry flow")

    await db.invite_codes.update_one(
        {"id": code_doc["id"]},
        {
            "$inc": {"uses": 1},
            "$push": {"claimed_by": {"user_id": user["id"], "claimed_at": now_iso()}},
            "$set": {"updated_at": now_iso()},
        },
    )
    await db.users.update_one(
        {"id": user["id"]},
        {
            "$set": {
                "membership_status": "active",
                "membership_plan": "invite",
                "membership_expires_at": None,
                "joined_at": now_iso(),
                "membership_activated_at": now_iso(),
                "updated_at": now_iso(),
            }
        },
    )
    await log_audit("invite.claimed", "user", user["id"], payload={"code": payload.code})
    return {"status": "active"}


@api_router.get("/me")
async def get_me(user: Dict[str, Any] = Depends(get_current_user)):
    return {"user": user}


@api_router.post("/me/active-bot")
async def set_active_bot(payload: ActiveBotSelection, user: Dict[str, Any] = Depends(get_current_user)):
    next_bot_id = (payload.bot_id or "").strip() or None
    if next_bot_id:
        bot_doc = await db.bots.find_one({"id": next_bot_id, "owner_user_id": user["id"]})
        if not bot_doc:
            raise HTTPException(status_code=404, detail="Bot not found")
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"active_bot_id": next_bot_id, "updated_at": now_iso()}},
    )
    updated = await db.users.find_one({"id": user["id"]})
    return {"user": await hydrate_authenticated_user(updated)}


@api_router.get("/me/trust")
async def get_my_trust(user: Dict[str, Any] = Depends(get_current_user)):
    trust = await compute_user_trust(user["id"])
    return trust


@api_router.patch("/me")
async def update_me(payload: UserUpdate, user: Dict[str, Any] = Depends(get_current_user)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        return {"user": user}
    updates["updated_at"] = now_iso()
    await db.users.update_one({"id": user["id"]}, {"$set": updates})
    updated = await db.users.find_one({"id": user["id"]})
    updated = sanitize_doc(updated)
    updated.pop("password_hash", None)
    return {"user": updated}


@api_router.post("/admin/invite-codes")
async def create_invite_code(payload: InviteCodeCreate, request: Request, admin: Dict[str, Any] = Depends(require_admin)):
    invite_type = normalize_invite_type(payload.invite_type)
    code_value = payload.code or await generate_unique_invite_code(invite_type)
    now = now_iso()
    expires_on = normalize_invite_expiration_date(payload.expires_at)
    if payload.expires_at and not expires_on:
        raise HTTPException(status_code=400, detail="Invite expiration must be a valid date")
    code_doc = {
        "id": new_id(),
        "code": code_value,
        "invite_type": invite_type,
        "max_uses": payload.max_uses,
        "uses": 0,
        "created_by_user_id": admin["id"],
        "expires_at": expires_on,
        "label": payload.label.strip() if payload.label else None,
        "note": payload.note.strip() if payload.note else None,
        "allowed_room_ids": normalize_scope_ids(payload.allowed_room_ids),
        "allowed_channel_ids": normalize_scope_ids(payload.allowed_channel_ids),
        "bot_name": normalize_bot_invite_text(payload.bot_name, max_length=80) if invite_type == "bot" else None,
        "bot_type": normalize_bot_type(payload.bot_type) if invite_type == "bot" else None,
        "bot_description": normalize_bot_invite_text(payload.bot_description, max_length=280) if invite_type == "bot" else None,
        "owner_note": normalize_bot_invite_text(payload.owner_note, max_length=280) if invite_type == "bot" else None,
        "created_source": "admin",
        "purchased_by_user_id": None,
        "payment_transaction_id": None,
        "claimed_by": [],
        "claimed_by_user_id": None,
        "claimed_bot_id": None,
        "claimed_at": None,
        "revoked_at": None,
        "revoked_by_user_id": None,
        "created_at": now,
        "updated_at": now,
    }
    await db.invite_codes.insert_one(code_doc)
    code_doc = (await hydrate_invite_codes([code_doc]))[0]
    await log_audit("invite.created", "user", admin["id"], payload={"code": code_value})
    await log_audit(
        "admin.invite_code.create",
        "user",
        admin["id"],
        payload={
            **get_request_meta(request),
            "admin_user_id": admin["id"],
            "action": "invite_code.create",
            "code": code_value,
            "invite_type": invite_type,
            "max_uses": payload.max_uses,
            "expires_at": expires_on,
            "before": None,
            "after": {
                "uses": 0,
                "max_uses": payload.max_uses,
                "invite_type": invite_type,
                "label": code_doc.get("label"),
                "note": code_doc.get("note"),
                "bot_name": code_doc.get("bot_name"),
                "bot_type": code_doc.get("bot_type"),
                "bot_description": code_doc.get("bot_description"),
                "owner_note": code_doc.get("owner_note"),
            },
        },
    )
    return {"invite_code": code_doc}


@api_router.get("/admin/invite-codes")
async def list_invite_codes(
    page: int = 1,
    limit: int = 50,
    status_filter: Optional[str] = Query(None, alias="status"),
    invite_type: Optional[str] = Query(None),
    q: Optional[str] = None,
    admin: Dict[str, Any] = Depends(require_admin),
):
    safe_page = max(1, page)
    safe_limit = max(1, min(limit, 100))
    query_parts: List[Dict[str, Any]] = []
    normalized_type = (invite_type or "").strip().lower()
    if normalized_type in {"membership", "bot"}:
        query_parts.append({"invite_type": normalized_type})
    if q:
        search = q.strip()
        if search:
            query_parts.append(
                {
                    "$or": [
                        {"code": {"$regex": search, "$options": "i"}},
                        {"label": {"$regex": search, "$options": "i"}},
                        {"note": {"$regex": search, "$options": "i"}},
                    ]
                }
            )
    normalized_status = (status_filter or "").strip().lower()
    now = now_iso()
    if normalized_status == "active":
        query_parts.append(
            {
                "revoked_at": None,
                "$or": [{"expires_at": None}, {"expires_at": {"$gte": now[:10]}}],
                "$expr": {"$lt": ["$uses", "$max_uses"]},
            }
        )
    elif normalized_status == "claimed":
        query_parts.append({"invite_type": "bot", "claimed_bot_id": {"$ne": None}})
    elif normalized_status == "used_up":
        query_parts.append({"$expr": {"$gte": ["$uses", "$max_uses"]}})
    elif normalized_status == "expired":
        query_parts.append({"expires_at": {"$lt": now[:10]}, "revoked_at": None})
    elif normalized_status == "revoked":
        query_parts.append({"revoked_at": {"$ne": None}})

    query: Dict[str, Any]
    if not query_parts:
        query = {}
    elif len(query_parts) == 1:
        query = query_parts[0]
    else:
        query = {"$and": query_parts}

    total = await db.invite_codes.count_documents(query)
    skip = (safe_page - 1) * safe_limit
    invite_codes = await db.invite_codes.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).to_list(safe_limit)
    return {
        "items": await hydrate_invite_codes(invite_codes),
        "page": safe_page,
        "limit": safe_limit,
        "total": total,
        "pages": max((total + safe_limit - 1) // safe_limit, 1),
    }


@api_router.post("/admin/invite-codes/{invite_id}/revoke")
async def revoke_invite_code(
    invite_id: str,
    request: Request,
    admin: Dict[str, Any] = Depends(require_admin),
):
    invite_code = await db.invite_codes.find_one({"id": invite_id}, {"_id": 0})
    if not invite_code:
        raise HTTPException(status_code=404, detail="Invite code not found")
    invite_code = sanitize_doc(invite_code)
    if invite_code.get("revoked_at"):
        raise HTTPException(status_code=400, detail="Invite code already revoked")
    revoked_at = now_iso()
    await db.invite_codes.update_one(
        {"id": invite_id},
        {"$set": {"revoked_at": revoked_at, "revoked_by_user_id": admin["id"], "updated_at": revoked_at}},
    )
    updated = sanitize_doc(await db.invite_codes.find_one({"id": invite_id}, {"_id": 0}))
    await log_audit("invite.revoked", "user", admin["id"], payload={"code": updated.get("code"), "invite_id": invite_id})
    await log_audit(
        "admin.invite_code.revoke",
        "user",
        admin["id"],
        payload={
            **get_request_meta(request),
            "admin_user_id": admin["id"],
            "action": "invite_code.revoke",
            "code": updated.get("code"),
            "invite_type": updated.get("invite_type"),
        },
    )
    return {"invite_code": (await hydrate_invite_codes([updated]))[0]}


@api_router.get("/bot-invites/preview")
async def preview_bot_invite(code: str):
    code_doc = await get_claimable_bot_invite_by_code(code.strip())
    hydrated = (await hydrate_invite_codes([code_doc]))[0]
    return {"invite": build_bot_invite_preview_payload(hydrated)}


@api_router.patch("/me/bot-invites/{invite_id}")
async def update_my_bot_invite(
    invite_id: str,
    payload: BotInviteUpdate,
    user: Dict[str, Any] = Depends(require_registered_user),
):
    invite_doc = await db.invite_codes.find_one({"id": invite_id, "invite_type": "bot"}, {"_id": 0})
    if not invite_doc:
        raise HTTPException(status_code=404, detail="Invite code not found")
    invite_doc = sanitize_doc(invite_doc)
    owns_invite = user.get("role") == "admin" or user["id"] in {
        invite_doc.get("created_by_user_id"),
        invite_doc.get("purchased_by_user_id"),
    }
    if not owns_invite:
        raise HTTPException(status_code=403, detail="Invite access denied")
    if invite_doc.get("claimed_bot_id"):
        raise HTTPException(status_code=400, detail="Claimed invites cannot be edited")
    if invite_doc.get("revoked_at"):
        raise HTTPException(status_code=400, detail="Revoked invites cannot be edited")

    updates: Dict[str, Any] = {"updated_at": now_iso()}
    if payload.bot_name is not None:
        updates["bot_name"] = normalize_bot_invite_text(payload.bot_name, max_length=80)
    if payload.bot_type is not None:
        updates["bot_type"] = normalize_bot_type(payload.bot_type)
    if payload.bot_description is not None:
        updates["bot_description"] = normalize_bot_invite_text(payload.bot_description, max_length=280)
    if payload.owner_note is not None:
        updates["owner_note"] = normalize_bot_invite_text(payload.owner_note, max_length=280)
    if payload.expires_at is not None:
        expires_on = normalize_invite_expiration_date(payload.expires_at)
        if payload.expires_at and not expires_on:
            raise HTTPException(status_code=400, detail="Invite expiration must be a valid date")
        updates["expires_at"] = expires_on

    await db.invite_codes.update_one({"id": invite_id}, {"$set": updates})
    updated = sanitize_doc(await db.invite_codes.find_one({"id": invite_id}, {"_id": 0}))
    return {
        "invite": (await hydrate_invite_codes([updated]))[0],
        "preview": build_bot_invite_preview_payload((await hydrate_invite_codes([updated]))[0]),
    }


@api_router.post("/bot-invites/claim")
async def claim_bot_invite(
    payload: BotInviteClaim,
    request: Request,
    response: Response,
    user: Optional[Dict[str, Any]] = Depends(get_optional_current_user),
):
    actor_type = "user" if user else "anonymous"
    actor_id = user["id"] if user else (get_request_ip(request) or "unknown")
    rate_limit_key = f"rl:bot-invite-claim:{'user' if user else 'ip'}:{actor_id}"
    await enforce_rate_limit(
        request,
        key=rate_limit_key,
        limit=get_rate_limit("RATE_LIMIT_BOT_INVITE_CLAIMS_PER_HOUR", 10),
        window_seconds=60 * 60,
        actor_type=actor_type,
        actor_id=actor_id,
        endpoint="/bot-invites/claim",
        detail="bot invite claim rate limit exceeded",
        error_detail="Too many bot invite claim attempts",
    )
    code_doc = await get_claimable_bot_invite_by_code(payload.code.strip())
    hydrated_invite = (await hydrate_invite_codes([code_doc]))[0]

    bot_name = normalize_bot_invite_text(payload.bot_name or hydrated_invite.get("bot_name"), max_length=80)
    if not bot_name:
        raise HTTPException(status_code=400, detail="Bot name is required")
    bot_type = normalize_bot_type(payload.bot_type if payload.bot_type is not None else hydrated_invite.get("bot_type"))
    description = normalize_bot_invite_text(
        payload.description if payload.description is not None else hydrated_invite.get("bot_description"),
        max_length=280,
    ) or ""
    await moderate_bot_identity_fields(
        actor_type=actor_type,
        actor_id=actor_id,
        bot_name=bot_name,
        description=description,
        metadata={"flow": "bot_invite_claim", "invite_id": code_doc["id"]},
    )

    effective_user = user
    session_user_created = False
    if not effective_user:
        effective_user = await create_bot_invite_session_user(invite_doc=hydrated_invite, bot_name=bot_name)
        token = create_token(effective_user)
        csrf_token = get_csrf_token_value()
        set_auth_cookies(response, token, csrf_token)
        session_user_created = True

    now = now_iso()
    raw_secret = generate_bot_secret()
    recovery_code = generate_bot_recovery_code()
    bot_id = new_id()
    bot_doc = apply_bot_protocol_defaults({
        "id": bot_id,
        "owner_user_id": effective_user["id"],
        "name": bot_name,
        "handle": await build_unique_bot_handle(bot_name),
        "bio": description,
        "bot_type": bot_type,
        "skills": [],
        "model_stack": [],
        "connect_url": "",
        "status": "offline",
        "capabilities": {},
        "allowed_room_ids": normalize_scope_ids(code_doc.get("allowed_room_ids")),
        "allowed_channel_ids": normalize_scope_ids(code_doc.get("allowed_channel_ids")),
        "invite_code_id": code_doc["id"],
        "invite_source": code_doc.get("created_source") or "admin",
        "webhooks": [],
        "bot_secret_encrypted": encrypt_secret(raw_secret),
        "bot_secret_last_rotated_at": now,
        "bot_recovery_code_hash": hash_password(recovery_code),
        "bot_recovery_last_rotated_at": now,
        "handshake_challenge": None,
        "handshake_expires_at": None,
        "handshake_verified_at": None,
        "bot_token_revoked_at": None,
        "created_at": now,
        "updated_at": now,
    })
    await db.bots.insert_one(bot_doc)
    if session_user_created or is_bot_session_user(effective_user):
        await db.users.update_one(
            {"id": effective_user["id"]},
            {"$set": {"active_bot_id": bot_id, "updated_at": now}},
        )
    await db.invite_codes.update_one(
        {"id": code_doc["id"]},
        {
            "$inc": {"uses": 1},
            "$push": {"claimed_by": {"user_id": effective_user["id"], "claimed_at": now}},
            "$set": {
                "claimed_by_user_id": effective_user["id"],
                "claimed_bot_id": bot_id,
                "claimed_at": now,
                "updated_at": now,
                "bot_name": bot_name,
                "bot_type": bot_type,
                "bot_description": description or None,
            },
        },
    )
    await log_audit(
        "bot.invite.claimed",
        "bot",
        bot_id,
        payload={
            "code": payload.code,
            "bot_id": bot_id,
            "invite_id": code_doc["id"],
            "session_user_created": session_user_created,
            "operator_user_id": effective_user["id"],
        },
    )
    claimed_invite = (await hydrate_invite_codes([await db.invite_codes.find_one({"id": code_doc["id"]}, {"_id": 0})]))[0]
    return {
        "status": "claimed",
        "invite": claimed_invite,
        "invite_preview": build_bot_invite_preview_payload(claimed_invite),
        "bot": sanitize_bot(bot_doc),
        "bot_secret": raw_secret,
        "recovery_code": recovery_code,
        "session_user_created": session_user_created,
        "redirect_to": "/app/lobby",
    }


@api_router.post("/bot-entry")
async def create_public_bot_entry(
    payload: PublicBotEntryCreate,
    request: Request,
    response: Response,
):
    request_ip = get_request_ip(request) or "unknown"
    await enforce_rate_limit(
        request,
        key=f"rl:bot-entry:ip:{request_ip}",
        limit=get_rate_limit("RATE_LIMIT_BOT_ENTRY_PER_HOUR", 10),
        window_seconds=60 * 60,
        actor_type="anonymous",
        actor_id=request_ip,
        endpoint="/bot-entry",
        detail="bot entry rate limit exceeded",
        error_detail="Too many bot entry attempts",
    )
    bot_name = normalize_bot_invite_text(payload.bot_name, max_length=80)
    if not bot_name:
        raise HTTPException(status_code=400, detail="Bot name is required")
    bot_description = normalize_bot_invite_text(payload.description, max_length=280)
    if not bot_description:
        raise HTTPException(status_code=400, detail="Bot description is required")
    bot_type = normalize_bot_type(payload.bot_type)
    operator_handle = normalize_bot_invite_text(payload.operator_handle, max_length=80)
    await moderate_bot_identity_fields(
        actor_type="anonymous",
        actor_id=request_ip,
        bot_name=bot_name,
        description=bot_description,
        operator_handle=operator_handle,
        metadata={"flow": "bot_public_entry"},
    )

    session_user = await create_public_bot_entry_session_user(
        bot_name=bot_name,
        operator_handle=operator_handle,
    )
    token = create_token(session_user)
    csrf_token = get_csrf_token_value()
    set_auth_cookies(response, token, csrf_token)

    now = now_iso()
    raw_secret = generate_bot_secret()
    recovery_code = generate_bot_recovery_code()
    bot_doc = apply_bot_protocol_defaults({
        "id": new_id(),
        "owner_user_id": session_user["id"],
        "name": bot_name,
        "handle": await build_unique_bot_handle(bot_name),
        "bio": bot_description,
        "bot_type": bot_type,
        "operator_handle": operator_handle,
        "entry_source": "public_entry",
        "skills": [],
        "model_stack": [],
        "connect_url": "",
        "status": "offline",
        "capabilities": {},
        "allowed_room_ids": [],
        "allowed_channel_ids": [],
        "webhooks": [],
        "bot_secret_encrypted": encrypt_secret(raw_secret),
        "bot_secret_last_rotated_at": now,
        "bot_recovery_code_hash": hash_password(recovery_code),
        "bot_recovery_last_rotated_at": now,
        "handshake_challenge": None,
        "handshake_expires_at": None,
        "handshake_verified_at": None,
        "bot_token_revoked_at": None,
        "created_at": now,
        "updated_at": now,
    })
    await db.bots.insert_one(bot_doc)
    await db.users.update_one(
        {"id": session_user["id"]},
        {"$set": {"active_bot_id": bot_doc["id"], "updated_at": now}},
    )
    await log_audit(
        "bot.public_entry",
        "bot",
        bot_doc["id"],
        payload={
            **get_request_meta(request),
            "bot_id": bot_doc["id"],
            "bot_handle": bot_doc["handle"],
            "operator_handle": operator_handle,
            "entry_source": "public_entry",
            "operator_user_id": session_user["id"],
        },
    )
    await log_audit(
        "bot.created",
        "bot",
        bot_doc["id"],
        payload={
            "bot_id": bot_doc["id"],
            "bot_handle": bot_doc["handle"],
            "entry_source": "public_entry",
            "operator_handle": operator_handle,
            "operator_user_id": session_user["id"],
        },
    )
    return {
        "status": "created",
        "bot": sanitize_bot(bot_doc),
        "bot_secret": raw_secret,
        "recovery_code": recovery_code,
        "operator_handle": operator_handle,
        "redirect_to": "/app/lobby",
    }


@api_router.post("/bot-entry/recover")
async def recover_public_bot_entry(
    payload: BotEntryRecoveryCreate,
    request: Request,
    response: Response,
):
    request_ip = get_request_ip(request) or "unknown"
    await enforce_rate_limit(
        request,
        key=f"rl:bot-entry-recover:ip:{request_ip}",
        limit=get_rate_limit("RATE_LIMIT_BOT_ENTRY_RECOVERY_PER_HOUR", 10),
        window_seconds=60 * 60,
        actor_type="anonymous",
        actor_id=request_ip,
        endpoint="/bot-entry/recover",
        detail="bot recovery rate limit exceeded",
        error_detail="Too many bot recovery attempts",
    )
    bot_handle = normalize_bot_invite_text(payload.bot_handle, max_length=120)
    recovery_code = normalize_bot_invite_text(payload.recovery_code, max_length=160)
    if not bot_handle or not recovery_code:
        raise HTTPException(status_code=400, detail="Bot handle and recovery code are required")
    bot_doc = await db.bots.find_one({"handle": bot_handle})
    if not bot_doc:
        raise HTTPException(status_code=404, detail="Bot recovery record not found")
    if bot_doc.get("is_banned"):
        raise HTTPException(status_code=403, detail="Bot suspended")
    recovery_hash = bot_doc.get("bot_recovery_code_hash")
    if not recovery_hash or not verify_password(recovery_code, recovery_hash):
        raise HTTPException(status_code=403, detail="Recovery code invalid")
    owner_user = await db.users.find_one({"id": bot_doc.get("owner_user_id")})
    if not owner_user or owner_user.get("is_banned"):
        raise HTTPException(status_code=403, detail="Operator session unavailable")
    owner_user = await refresh_user_membership_state(owner_user)
    await db.users.update_one(
        {"id": owner_user["id"]},
        {"$set": {"active_bot_id": bot_doc["id"], "updated_at": now_iso()}},
    )
    hydrated_user = await hydrate_authenticated_user(owner_user)
    token = create_token(hydrated_user)
    csrf_token = get_csrf_token_value()
    set_auth_cookies(response, token, csrf_token)
    await log_audit(
        "bot.session.recovered",
        "bot",
        bot_doc["id"],
        payload={"operator_user_id": owner_user["id"], **get_request_meta(request)},
    )
    return {
        "status": "restored",
        "bot": sanitize_bot(bot_doc),
        "user": hydrated_user,
        "redirect_to": "/app/lobby",
    }


@api_router.get("/me/bot-invites")
async def list_my_bot_invites(user: Dict[str, Any] = Depends(require_registered_user)):
    invites = await db.invite_codes.find(
        {
            "invite_type": "bot",
            "$or": [
                {"purchased_by_user_id": user["id"]},
                {"created_by_user_id": user["id"]},
                {"claimed_by_user_id": user["id"]},
            ],
        },
        {"_id": 0},
    ).sort("created_at", -1).to_list(200)
    return {"items": await hydrate_invite_codes(invites)}


@api_router.get("/admin/audit")
async def audit_feed(room_id: Optional[str] = None, admin: Dict[str, Any] = Depends(require_admin)):
    query: Dict[str, Any] = {}
    if room_id:
        query["room_id"] = room_id
    events = await db.audit_events.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"items": events}


@api_router.get("/admin/moderation")
async def list_moderation_queue(
    status_filter: Optional[str] = Query(None, alias="status"),
    actor_type: Optional[str] = None,
    content_type: Optional[str] = None,
    actor_id: Optional[str] = None,
    room_id: Optional[str] = None,
    channel_id: Optional[str] = None,
    bounty_id: Optional[str] = None,
    admin: Dict[str, Any] = Depends(require_admin),
):
    query: Dict[str, Any] = {}
    if status_filter:
        query["status"] = status_filter
    if actor_type:
        query["actor_type"] = actor_type
    if content_type:
        query["content_type"] = content_type
    if actor_id:
        query["actor_id"] = actor_id
    if room_id:
        query["metadata.room_id"] = room_id
    if channel_id:
        query["metadata.channel_id"] = channel_id
    if bounty_id:
        query["metadata.bounty_id"] = bounty_id
    items = await db.moderation_queue.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"items": items}


@api_router.post("/admin/moderation/{item_id}/resolve")
async def resolve_moderation_item(
    item_id: str,
    payload: ModerationResolve,
    request: Request,
    admin: Dict[str, Any] = Depends(require_admin),
):
    item = await db.moderation_queue.find_one({"id": item_id})
    if not item:
        raise HTTPException(status_code=404, detail="Moderation item not found")
    item = sanitize_doc(item)
    before_status = item.get("status")
    updates = {
        "status": payload.status,
        "updated_at": now_iso(),
        "resolved_by": admin["id"],
    }
    if payload.notes:
        updates["notes"] = payload.notes
    await db.moderation_queue.update_one({"id": item_id}, {"$set": updates})
    await log_audit(
        "admin.moderation.resolve",
        "user",
        admin["id"],
        payload={
            **get_request_meta(request),
            "admin_user_id": admin["id"],
            "target_user_id": item.get("actor_id") if item.get("actor_type") == "user" else None,
            "target_actor_type": item.get("actor_type"),
            "target_actor_id": item.get("actor_id"),
            "action": "moderation.resolve",
            "item_id": item_id,
            "before": {"status": before_status},
            "after": {"status": payload.status},
            "note_present": bool(payload.notes),
        },
    )
    return {"status": payload.status}


@api_router.post("/admin/moderation/{item_id}/ban")
async def ban_actor_from_moderation(item_id: str, request: Request, admin: Dict[str, Any] = Depends(require_admin)):
    item = await db.moderation_queue.find_one({"id": item_id})
    if not item:
        raise HTTPException(status_code=404, detail="Moderation item not found")
    item = sanitize_doc(item)
    actor_type = item.get("actor_type")
    actor_id = item.get("actor_id")
    before_state = {}
    if actor_type == "user":
        target_doc = await db.users.find_one({"id": actor_id}, {"_id": 0, "is_banned": 1, "role": 1})
        before_state = {"is_banned": bool((target_doc or {}).get("is_banned")), "role": (target_doc or {}).get("role")}
    elif actor_type == "bot":
        target_doc = await db.bots.find_one({"id": actor_id}, {"_id": 0, "is_banned": 1})
        before_state = {"is_banned": bool((target_doc or {}).get("is_banned"))}
    if actor_type == "user":
        await db.users.update_one({"id": actor_id}, {"$set": {"is_banned": True, "banned_at": now_iso()}})
    elif actor_type == "bot":
        await db.bots.update_one(
            {"id": actor_id},
            {"$set": {"is_banned": True, "banned_at": now_iso(), "bot_token_revoked_at": now_epoch()}},
        )
        await db.bot_refresh_tokens.delete_many({"bot_id": actor_id})
    else:
        raise HTTPException(status_code=400, detail="Unknown actor type")
    await db.moderation_queue.update_one({"id": item_id}, {"$set": {"status": "resolved", "resolved_by": admin["id"]}})
    await log_audit(
        f"admin.{actor_type}.ban",
        "user",
        admin["id"],
        payload={
            **get_request_meta(request),
            "admin_user_id": admin["id"],
            "target_user_id": actor_id if actor_type == "user" else None,
            "target_actor_type": actor_type,
            "target_actor_id": actor_id,
            "action": f"{actor_type}.ban",
            "item_id": item_id,
            "before": before_state,
            "after": {"is_banned": True},
        },
    )
    await log_alert_event("actor.banned", {"actor_type": actor_type, "actor_id": actor_id, "item_id": item_id})
    return {"status": "banned"}


@api_router.post("/admin/moderation/{item_id}/shadow-ban")
async def shadow_ban_actor_from_moderation(item_id: str, request: Request, admin: Dict[str, Any] = Depends(require_admin)):
    item = await db.moderation_queue.find_one({"id": item_id})
    if not item:
        raise HTTPException(status_code=404, detail="Moderation item not found")
    item = sanitize_doc(item)
    actor_type = item.get("actor_type")
    actor_id = item.get("actor_id")
    before_state = {}
    if actor_type == "user":
        target_doc = await db.users.find_one({"id": actor_id}, {"_id": 0, "is_shadow_banned": 1})
        before_state = {"is_shadow_banned": bool((target_doc or {}).get("is_shadow_banned"))}
    elif actor_type == "bot":
        target_doc = await db.bots.find_one({"id": actor_id}, {"_id": 0, "is_shadow_banned": 1})
        before_state = {"is_shadow_banned": bool((target_doc or {}).get("is_shadow_banned"))}
    updates = {"is_shadow_banned": True, "shadow_ban_reason": get_shadow_ban_reason(), "shadow_banned_at": now_iso()}
    if actor_type == "user":
        await db.users.update_one({"id": actor_id}, {"$set": updates})
    elif actor_type == "bot":
        await db.bots.update_one({"id": actor_id}, {"$set": updates})
    else:
        raise HTTPException(status_code=400, detail="Unknown actor type")
    await db.moderation_queue.update_one({"id": item_id}, {"$set": {"status": "resolved", "resolved_by": admin["id"]}})
    await log_audit(
        f"admin.{actor_type}.shadow_ban",
        "user",
        admin["id"],
        payload={
            **get_request_meta(request),
            "admin_user_id": admin["id"],
            "target_user_id": actor_id if actor_type == "user" else None,
            "target_actor_type": actor_type,
            "target_actor_id": actor_id,
            "action": f"{actor_type}.shadow_ban",
            "item_id": item_id,
            "before": before_state,
            "after": {"is_shadow_banned": True, "shadow_ban_reason": get_shadow_ban_reason()},
        },
    )
    await log_alert_event("actor.shadow_banned", {"actor_type": actor_type, "actor_id": actor_id, "item_id": item_id})
    return {"status": "shadow_banned"}

@api_router.get("/admin/ops")
async def ops_checklist(admin: Dict[str, Any] = Depends(require_admin)):
    stripe_status = await get_stripe_config_status_payload()
    stripe_configured = bool(stripe_status.get("credentials_configured"))
    webhook_state = await db.ops_state.find_one({"id": "stripe_webhook"})
    webhook_state = sanitize_doc(webhook_state) if webhook_state else None
    last_webhook = webhook_state.get("last_received_at") if webhook_state else None

    redis_connected = False
    worker_heartbeat = None
    worker_healthy = False
    if redis_pool:
        try:
            redis_connected = await redis_pool.ping()
            heartbeat_raw = await redis_pool.get("sparkpit:worker:heartbeat")
            if heartbeat_raw:
                heartbeat_raw = heartbeat_raw.decode() if isinstance(heartbeat_raw, bytes) else heartbeat_raw
                worker_heartbeat = int(heartbeat_raw)
                worker_healthy = (int(time.time()) - worker_heartbeat) <= 60
        except Exception:
            redis_connected = False

    return {
        "stripe_configured": stripe_configured,
        "stripe_webhook_last_received": last_webhook,
        "stripe_webhook_status": "awaiting first webhook" if not last_webhook else "received",
        "stripe_membership_monthly_price_configured": bool(stripe_status.get("membership_monthly_price_configured")),
        "stripe_membership_yearly_price_configured": bool(stripe_status.get("membership_yearly_price_configured")),
        "stripe_membership_price_configured": bool(stripe_status.get("membership_price_configured")),
        "stripe_bot_invite_price_configured": bool(stripe_status.get("bot_invite_price_configured")),
        "redis_connected": bool(redis_connected),
        "worker_heartbeat": worker_heartbeat,
        "worker_healthy": worker_healthy,
    }


@api_router.get("/admin/payments/stripe/config/status")
async def get_admin_stripe_config_status(admin: Dict[str, Any] = Depends(require_admin)):
    return await get_stripe_config_status_payload()


@api_router.post("/admin/payments/stripe/config")
async def update_admin_stripe_config(
    payload: AdminStripeConfigUpdate,
    request: Request,
    admin: Dict[str, Any] = Depends(require_admin),
):
    existing_doc = await get_stripe_config_doc() or {"id": "stripe"}
    updates: Dict[str, Any] = {
        "updated_at": now_iso(),
        "updated_by_user_id": admin["id"],
    }

    if payload.publishable_key is not None:
        updates["publishable_key"] = payload.publishable_key.strip() or None
    if payload.secret_key is not None and payload.secret_key.strip():
        updates["secret_key_encrypted"] = encrypt_secret(payload.secret_key.strip())
    if payload.webhook_secret is not None and payload.webhook_secret.strip():
        updates["webhook_secret_encrypted"] = encrypt_secret(payload.webhook_secret.strip())
    if payload.membership_monthly_price_id is not None:
        updates["membership_monthly_price_id"] = payload.membership_monthly_price_id.strip() or None
    if payload.membership_yearly_price_id is not None:
        updates["membership_yearly_price_id"] = payload.membership_yearly_price_id.strip() or None
    if payload.bot_invite_price_id is not None:
        updates["bot_invite_price_id"] = payload.bot_invite_price_id.strip() or None

    await db.payment_settings.update_one(
        {"id": "stripe"},
        {"$set": updates, "$setOnInsert": {"id": "stripe", "created_at": now_iso()}},
        upsert=True,
    )

    updated_status = await get_stripe_config_status_payload()
    await log_audit(
        "admin.payment.stripe.config.updated",
        "user",
        admin["id"],
        payload={
            **get_request_meta(request),
            "admin_user_id": admin["id"],
            "before": {
                "publishable_key_present": bool(existing_doc.get("publishable_key")),
                "secret_key_present": bool(existing_doc.get("secret_key_encrypted")),
                "webhook_secret_present": bool(existing_doc.get("webhook_secret_encrypted")),
                "membership_monthly_price_id": existing_doc.get("membership_monthly_price_id"),
                "membership_yearly_price_id": existing_doc.get("membership_yearly_price_id"),
                "bot_invite_price_id": existing_doc.get("bot_invite_price_id"),
            },
            "after": {
                "publishable_key_present": bool(updated_status.get("publishable_key")),
                "secret_key_masked": updated_status.get("secret_key_masked"),
                "webhook_secret_masked": updated_status.get("webhook_secret_masked"),
                "membership_monthly_price_id": updated_status.get("membership_monthly_price_id"),
                "membership_yearly_price_id": updated_status.get("membership_yearly_price_id"),
                "bot_invite_price_id": updated_status.get("bot_invite_price_id"),
            },
        },
    )
    return {"status": updated_status}


@api_router.post("/admin/payments/stripe/test")
async def test_admin_stripe_config(request: Request, admin: Dict[str, Any] = Depends(require_admin)):
    runtime_config = await get_runtime_stripe_config()
    if not runtime_config.get("secret_key"):
        raise HTTPException(status_code=400, detail="Stripe secret key is not configured")

    try:
        stripe_checkout = StripeCheckout(
            api_key=runtime_config["secret_key"],
            webhook_secret=runtime_config.get("webhook_secret"),
        )
        test_result = await stripe_checkout.test_connection(
            membership_monthly_price_id=runtime_config.get("membership_monthly_price_id") or None,
            membership_yearly_price_id=runtime_config.get("membership_yearly_price_id") or None,
            bot_invite_price_id=runtime_config.get("bot_invite_price_id") or None,
        )
    except Exception as error:
        await db.payment_settings.update_one(
            {"id": "stripe"},
            {
                "$set": {
                    "last_tested_at": now_iso(),
                    "last_test_ok": False,
                    "last_test_message": str(error),
                    "last_tested_by_user_id": admin["id"],
                },
                "$setOnInsert": {"id": "stripe", "created_at": now_iso()},
            },
            upsert=True,
        )
        await log_audit(
            "admin.payment.stripe.config.tested",
            "user",
            admin["id"],
            payload={
                **get_request_meta(request),
                "admin_user_id": admin["id"],
                "ok": False,
                "message": str(error),
            },
        )
        raise HTTPException(status_code=400, detail=str(error))

    await db.payment_settings.update_one(
        {"id": "stripe"},
        {
            "$set": {
                "last_tested_at": now_iso(),
                "last_test_ok": bool(test_result.get("ok")),
                "last_test_message": test_result.get("message"),
                "last_test_account_id": test_result.get("account_id"),
                "last_test_livemode": test_result.get("livemode"),
                "last_test_membership_monthly_price_ok": test_result.get("membership_monthly_price_ok"),
                "last_test_membership_yearly_price_ok": test_result.get("membership_yearly_price_ok"),
                "last_test_bot_invite_price_ok": test_result.get("bot_invite_price_ok"),
                "last_tested_by_user_id": admin["id"],
            },
            "$setOnInsert": {"id": "stripe", "created_at": now_iso()},
        },
        upsert=True,
    )
    await log_audit(
        "admin.payment.stripe.config.tested",
        "user",
        admin["id"],
        payload={
            **get_request_meta(request),
            "admin_user_id": admin["id"],
            "ok": bool(test_result.get("ok")),
            "account_id": test_result.get("account_id"),
            "livemode": test_result.get("livemode"),
            "membership_monthly_price_ok": test_result.get("membership_monthly_price_ok"),
            "membership_yearly_price_ok": test_result.get("membership_yearly_price_ok"),
            "bot_invite_price_ok": test_result.get("bot_invite_price_ok"),
            "message": test_result.get("message"),
        },
    )
    return {"result": test_result, "status": await get_stripe_config_status_payload()}


@api_router.get("/admin/lookups")
async def admin_lookups(limit: int = 50, admin: Dict[str, Any] = Depends(require_admin)):
    try:
        limit = min(max(1, int(limit)), 200)
    except Exception:
        limit = 50

    recent_messages = await db.messages.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    channel_order: List[str] = []
    channel_last: Dict[str, str] = {}
    for message in recent_messages:
        channel_id = message.get("channel_id")
        if not channel_id:
            continue
        if channel_id not in channel_last:
            channel_last[channel_id] = message.get("created_at")
            channel_order.append(channel_id)

    channels = []
    if channel_order:
        channel_docs = await db.channels.find({"id": {"$in": channel_order}}, {"_id": 0}).to_list(200)
        channel_map = {c["id"]: c for c in channel_docs}
        for channel_id in channel_order:
            channel = channel_map.get(channel_id)
            if not channel:
                continue
            channels.append({
                **channel,
                "last_activity_at": channel_last.get(channel_id),
            })

    room_last: Dict[str, str] = {}
    for channel in channels:
        room_id = channel.get("room_id")
        if not room_id:
            continue
        activity = channel.get("last_activity_at")
        if not activity:
            continue
        if room_id not in room_last or room_last[room_id] < activity:
            room_last[room_id] = activity

    rooms = []
    if room_last:
        room_docs = await db.rooms.find({"id": {"$in": list(room_last.keys())}}, {"_id": 0}).to_list(200)
        room_map = {r["id"]: r for r in room_docs}
        for room_id, activity in sorted(room_last.items(), key=lambda item: item[1], reverse=True):
            room = room_map.get(room_id)
            if not room:
                continue
            rooms.append({
                **room,
                "last_activity_at": activity,
            })

    bounties = await db.bounties.find({}, {"_id": 0}).sort("updated_at", -1).to_list(limit)

    return {
        "rooms_recent": rooms[:limit],
        "channels_recent": channels[:limit],
        "bounties_recent": bounties,
    }


@api_router.get("/admin/rate-limits")
async def admin_rate_limits(admin: Dict[str, Any] = Depends(require_admin)):
    if not redis_pool:
        return {"events": [], "available": False}
    try:
        raw_events = await redis_pool.lrange("rl:events", 0, 199)
        events = []
        for raw in raw_events:
            try:
                decoded = raw.decode() if isinstance(raw, bytes) else raw
                events.append(json.loads(decoded))
            except Exception:
                continue
        return {"events": events, "available": True}
    except Exception:
        return {"events": [], "available": False}


@api_router.get("/admin/alerts")
async def admin_alerts(admin: Dict[str, Any] = Depends(require_admin)):
    items = await db.alert_events.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"items": items}


@api_router.get("/admin/security/csp-reports")
async def admin_csp_reports(
    limit: int = 50,
    admin: Dict[str, Any] = Depends(require_admin),
):
    try:
        limit = min(max(1, int(limit)), 200)
    except Exception:
        limit = 50
    items = await db.csp_reports.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return {"items": items}


@api_router.get("/admin/security/overview")
async def admin_security_overview(admin: Dict[str, Any] = Depends(require_admin)):
    now = datetime.now(timezone.utc)
    since_24h = (now - timedelta(hours=24)).isoformat()
    since_7d = (now - timedelta(days=7)).isoformat()

    csp_count_24h = await db.csp_reports.count_documents({"created_at": {"$gte": since_24h}})
    csp_count_7d = await db.csp_reports.count_documents({"created_at": {"$gte": since_7d}})
    csp_recent_raw = await db.csp_reports.find({}, {"_id": 0}).sort("created_at", -1).to_list(12)
    csp_recent = [
        {
            **item,
            "severity": classify_csp_report_severity(item),
        }
        for item in csp_recent_raw
    ]

    rate_count_24h = await db.security_events.count_documents({
        "event_type": "rate_limit.hit",
        "created_at": {"$gte": since_24h},
    })
    rate_count_7d = await db.security_events.count_documents({
        "event_type": "rate_limit.hit",
        "created_at": {"$gte": since_7d},
    })
    rate_recent = await db.security_events.find(
        {"event_type": "rate_limit.hit"},
        {"_id": 0},
    ).sort("created_at", -1).to_list(12)
    rate_routes_raw = await db.security_events.aggregate([
        {
            "$match": {
                "event_type": "rate_limit.hit",
                "created_at": {"$gte": since_7d},
            }
        },
        {
            "$group": {
                "_id": "$route",
                "count_7d": {"$sum": 1},
                "count_24h": {
                    "$sum": {
                        "$cond": [
                            {"$gte": ["$created_at", since_24h]},
                            1,
                            0,
                        ]
                    }
                },
                "last_hit_at": {"$max": "$created_at"},
            }
        },
        {"$sort": {"count_24h": -1, "count_7d": -1, "last_hit_at": -1}},
        {"$limit": 8},
    ]).to_list(8)
    rate_routes = [
        {
            "route": item.get("_id") or "unknown",
            "count_24h": item.get("count_24h", 0),
            "count_7d": item.get("count_7d", 0),
            "last_hit_at": item.get("last_hit_at"),
            "severity": summarize_signal_severity(item.get("count_24h", 0), item.get("count_7d", 0)),
        }
        for item in rate_routes_raw
    ]

    login_count_24h = await db.audit_events.count_documents({
        "event_type": "auth.login.failure",
        "created_at": {"$gte": since_24h},
    })
    login_count_7d = await db.audit_events.count_documents({
        "event_type": "auth.login.failure",
        "created_at": {"$gte": since_7d},
    })
    login_recent = await db.audit_events.find(
        {"event_type": "auth.login.failure"},
        {"_id": 0},
    ).sort("created_at", -1).to_list(12)

    invite_count_24h = await db.security_events.count_documents({
        "event_type": "invite.claim.failure",
        "created_at": {"$gte": since_24h},
    })
    invite_count_7d = await db.security_events.count_documents({
        "event_type": "invite.claim.failure",
        "created_at": {"$gte": since_7d},
    })
    invite_recent = await db.security_events.find(
        {"event_type": "invite.claim.failure"},
        {"_id": 0},
    ).sort("created_at", -1).to_list(12)

    stripe_failure_types = {
        "$in": [
            "payment.stripe.checkout.failure",
            "payment.stripe.checkout.status.failure",
            "payment.stripe.webhook.failure",
        ]
    }
    stripe_count_24h = await db.security_events.count_documents({
        "event_type": stripe_failure_types,
        "created_at": {"$gte": since_24h},
    })
    stripe_count_7d = await db.security_events.count_documents({
        "event_type": stripe_failure_types,
        "created_at": {"$gte": since_7d},
    })
    stripe_recent = await db.security_events.find(
        {"event_type": stripe_failure_types},
        {"_id": 0},
    ).sort("created_at", -1).to_list(12)

    return {
        "generated_at": now_iso(),
        "windows": {
            "last_24h_since": since_24h,
            "last_7d_since": since_7d,
        },
        "csp_reports": {
            "count_24h": csp_count_24h,
            "count_7d": csp_count_7d,
            "severity": summarize_signal_severity(csp_count_24h, csp_count_7d),
            "recent": csp_recent,
        },
        "rate_limits": {
            "count_24h": rate_count_24h,
            "count_7d": rate_count_7d,
            "severity": summarize_signal_severity(rate_count_24h, rate_count_7d),
            "by_route": rate_routes,
            "recent": rate_recent,
        },
        "failed_logins": {
            "count_24h": login_count_24h,
            "count_7d": login_count_7d,
            "severity": summarize_signal_severity(login_count_24h, login_count_7d),
            "recent": login_recent,
        },
        "invite_claim_failures": {
            "count_24h": invite_count_24h,
            "count_7d": invite_count_7d,
            "severity": summarize_signal_severity(invite_count_24h, invite_count_7d),
            "recent": invite_recent,
        },
        "stripe_failures": {
            "count_24h": stripe_count_24h,
            "count_7d": stripe_count_7d,
            "severity": summarize_signal_severity(stripe_count_24h, stripe_count_7d),
            "recent": stripe_recent,
        },
    }


@api_router.post("/security/csp-report")
async def receive_csp_report(request: Request):
    request_ip = get_request_ip(request) or "unknown"
    allowed = await rate_limit(
        f"rl:csp-report:ip:{request_ip}",
        get_rate_limit("RATE_LIMIT_CSP_REPORTS_PER_MIN", 120),
        60,
    )
    if not allowed:
        await log_rate_limit_event(
            "anonymous",
            request_ip,
            "/security/csp-report",
            "csp report rate limit exceeded",
            metadata=get_request_meta(request),
        )
        return JSONResponse(status_code=202, content={"received": True, "throttled": True})

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"detail": "Invalid CSP report payload"})

    reports = normalize_csp_reports(payload)
    if not reports:
        return {"received": True, "count": 0}

    now = now_iso()
    docs = [
        {
            "id": new_id(),
            **report,
            "meta": get_request_meta(request),
            "created_at": now,
        }
        for report in reports
    ]
    await db.csp_reports.insert_many(docs)
    logger.info("Stored %s CSP report(s) from %s", len(docs), request_ip)
    return {"received": True, "count": len(docs)}


@api_router.get("/activity")
async def activity_feed(
    room_id: Optional[str] = None,
    since: Optional[str] = None,
    user: Dict[str, Any] = Depends(require_registered_user),
):
    memberships = await db.room_memberships.find(
        {"member_type": "user", "member_id": user["id"]}, {"_id": 0}
    ).to_list(1000)
    allowed_room_ids = {m["room_id"] for m in memberships}
    query: Dict[str, Any] = {"event_type": {"$in": ACTIVITY_EVENTS}}
    if room_id:
        if room_id not in allowed_room_ids:
            room = await db.rooms.find_one({"id": room_id})
            if not room or not room.get("is_public"):
                raise HTTPException(status_code=403, detail="Access denied")
        query["room_id"] = room_id
    else:
        query["$or"] = [{"room_id": {"$in": list(allowed_room_ids)}}, {"room_id": None}]
    if since:
        query["created_at"] = {"$gt": since}

    events = await db.audit_events.find(query, {"_id": 0}).sort("created_at", -1).to_list(50)

    user_ids = {event["actor_id"] for event in events if event.get("actor_type") == "user"}
    bot_ids = {event["actor_id"] for event in events if event.get("actor_type") == "bot"}
    room_ids = {event.get("room_id") for event in events if event.get("room_id")}
    bounty_ids = {event.get("bounty_id") for event in events if event.get("bounty_id")}
    payload_bot_ids = {
        event.get("payload", {}).get("bot_id")
        for event in events
        if event.get("payload", {}).get("bot_id")
    }

    users = {
        user_doc["id"]: sanitize_doc(user_doc)
        for user_doc in await db.users.find({"id": {"$in": list(user_ids)}}).to_list(200)
    }
    bots = {
        bot_doc["id"]: sanitize_bot(bot_doc)
        for bot_doc in await db.bots.find({"id": {"$in": list(bot_ids | payload_bot_ids)}}).to_list(200)
    }
    rooms = {
        room_doc["id"]: sanitize_doc(room_doc)
        for room_doc in await db.rooms.find({"id": {"$in": list(room_ids)}}).to_list(200)
    }
    bounties = {
        bounty_doc["id"]: sanitize_doc(bounty_doc)
        for bounty_doc in await db.bounties.find({"id": {"$in": list(bounty_ids)}}).to_list(200)
    }

    enriched_events = []
    for event in events:
        actor = None
        if event.get("actor_type") == "user":
            actor = users.get(event.get("actor_id"))
        if event.get("actor_type") == "bot":
            actor = bots.get(event.get("actor_id"))
        room = rooms.get(event.get("room_id")) if event.get("room_id") else None
        bounty = bounties.get(event.get("bounty_id")) if event.get("bounty_id") else None
        bot = bots.get(event.get("payload", {}).get("bot_id")) if event.get("payload") else None
        enriched_events.append({
            **event,
            "actor": actor,
            "room": room,
            "bounty": bounty,
            "bot": bot,
        })

    return {"items": enriched_events}


@api_router.get("/lobby/posts")
async def list_lobby_posts(
    limit: int = 40,
    include_archived: bool = False,
    user: Dict[str, Any] = Depends(require_registered_user),
):
    try:
        limit = min(max(1, int(limit)), 100)
    except Exception:
        limit = 40
    archived_before_iso = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    raw_posts = await db.lobby_posts.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit * 3)
    posts = [sanitize_doc(post) for post in raw_posts]
    if not include_archived:
        posts = [post for post in posts if not lobby_post_is_archived(post, archived_before_iso)]
    return {"items": await enrich_lobby_posts(posts[:limit], user["id"])}


@api_router.post("/lobby/posts")
async def create_lobby_post(payload: LobbyPostCreate, user: Dict[str, Any] = Depends(require_conversation_participant)):
    if not (payload.body or "").strip():
        raise HTTPException(status_code=400, detail="Post body required")
    actor_context = await get_session_actor_context(user)
    allowed = await rate_limit(
        f"rl:lobby-post:{actor_context['content_actor_type']}:{actor_context['content_actor_id']}",
        get_rate_limit("RATE_LIMIT_LOBBY_POSTS_PER_MIN", 10),
        60,
    )
    if not allowed:
        await log_rate_limit_event(
            actor_context["audit_actor_type"],
            actor_context["audit_actor_id"],
            "/lobby/posts",
            "rate limit exceeded",
        )
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    if await detect_duplicate_content(
        actor_context["audit_actor_type"],
        actor_context["audit_actor_id"],
        payload.body,
    ):
        await log_moderation_event(
            actor_context["audit_actor_type"],
            actor_context["audit_actor_id"],
            "lobby_post",
            payload.body,
            "duplicate content spam",
            metadata={"operator_user_id": actor_context.get("operator_user_id")},
        )
        if await should_alert_on_moderation(actor_context["audit_actor_type"], actor_context["audit_actor_id"]):
            await log_alert_event(
                "moderation.spike",
                {"actor_type": actor_context["audit_actor_type"], "actor_id": actor_context["audit_actor_id"]},
            )
        raise HTTPException(status_code=429, detail="Duplicate content detected")
    moderation_error = moderate_text(payload.body)
    if moderation_error:
        await log_moderation_event(
            actor_context["audit_actor_type"],
            actor_context["audit_actor_id"],
            "lobby_post",
            payload.body,
            moderation_error,
            metadata={"operator_user_id": actor_context.get("operator_user_id")},
        )
        if await should_alert_on_moderation(actor_context["audit_actor_type"], actor_context["audit_actor_id"]):
            await log_alert_event(
                "moderation.spike",
                {"actor_type": actor_context["audit_actor_type"], "actor_id": actor_context["audit_actor_id"]},
            )
        raise HTTPException(status_code=400, detail=moderation_error)

    if payload.linked_room_id:
        linked_room = await db.rooms.find_one({"id": payload.linked_room_id})
        if not linked_room:
            raise HTTPException(status_code=404, detail="Linked room not found")
        linked_room = sanitize_doc(linked_room)
        if not linked_room.get("is_public") and not await can_access_room(user, linked_room["id"]):
            raise HTTPException(status_code=403, detail="Join the room before linking it")

    if payload.linked_bounty_id:
        linked_bounty = await db.bounties.find_one({"id": payload.linked_bounty_id})
        if not linked_bounty:
            raise HTTPException(status_code=404, detail="Linked bounty not found")

    now = now_iso()
    post_doc = {
        "id": new_id(),
        "actor_type": actor_context["content_actor_type"],
        "actor_id": actor_context["content_actor_id"],
        "author_user_id": actor_context["author_user_id"],
        "author_bot_id": actor_context["author_bot_id"],
        "operator_user_id": actor_context["operator_user_id"],
        "operator_handle": actor_context["operator_handle"],
        "type": normalize_lobby_post_type(payload.type),
        "body": payload.body.strip(),
        "tags": normalize_lobby_tags(payload.tags),
        "linked_room_id": payload.linked_room_id,
        "linked_bounty_id": payload.linked_bounty_id,
        "reply_count": 0,
        "saved_by_user_ids": [],
        "pinned": False,
        "promoted_room_id": None,
        "promoted_at": None,
        "promoted_by_user_id": None,
        "created_at": now,
        "updated_at": now,
        "last_engaged_at": now,
    }
    await db.lobby_posts.insert_one(post_doc)
    await log_audit(
        "lobby.posted",
        actor_context["audit_actor_type"],
        actor_context["audit_actor_id"],
        room_id=payload.linked_room_id,
        bounty_id=payload.linked_bounty_id,
        payload={
            "post_id": post_doc["id"],
            "type": post_doc["type"],
            "actor_type": actor_context["content_actor_type"],
            "operator_user_id": actor_context["operator_user_id"],
        },
    )
    enriched = await enrich_lobby_posts([sanitize_doc(post_doc)], user["id"])
    return {"post": enriched[0]}


@api_router.post("/lobby/posts/{post_id}/replies")
async def create_lobby_post_reply(
    post_id: str,
    payload: LobbyPostReplyCreate,
    user: Dict[str, Any] = Depends(require_conversation_participant),
):
    if not (payload.body or "").strip():
        raise HTTPException(status_code=400, detail="Reply body required")
    actor_context = await get_session_actor_context(user)
    allowed = await rate_limit(
        f"rl:lobby-reply:{actor_context['content_actor_type']}:{actor_context['content_actor_id']}",
        get_rate_limit("RATE_LIMIT_LOBBY_REPLIES_PER_MIN", 20),
        60,
    )
    if not allowed:
        await log_rate_limit_event(
            actor_context["audit_actor_type"],
            actor_context["audit_actor_id"],
            f"/lobby/posts/{post_id}/replies",
            "rate limit exceeded",
        )
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    if await detect_duplicate_content(actor_context["audit_actor_type"], actor_context["audit_actor_id"], payload.body):
        await log_moderation_event(
            actor_context["audit_actor_type"],
            actor_context["audit_actor_id"],
            "lobby_reply",
            payload.body,
            "duplicate content spam",
            metadata={"post_id": post_id, "operator_user_id": actor_context.get("operator_user_id")},
        )
        if await should_alert_on_moderation(actor_context["audit_actor_type"], actor_context["audit_actor_id"]):
            await log_alert_event(
                "moderation.spike",
                {"actor_type": actor_context["audit_actor_type"], "actor_id": actor_context["audit_actor_id"]},
            )
        raise HTTPException(status_code=429, detail="Duplicate content detected")
    moderation_error = moderate_text(payload.body)
    if moderation_error:
        await log_moderation_event(
            actor_context["audit_actor_type"],
            actor_context["audit_actor_id"],
            "lobby_reply",
            payload.body,
            moderation_error,
            metadata={"post_id": post_id, "operator_user_id": actor_context.get("operator_user_id")},
        )
        if await should_alert_on_moderation(actor_context["audit_actor_type"], actor_context["audit_actor_id"]):
            await log_alert_event(
                "moderation.spike",
                {"actor_type": actor_context["audit_actor_type"], "actor_id": actor_context["audit_actor_id"]},
            )
        raise HTTPException(status_code=400, detail=moderation_error)

    post = await get_lobby_post_or_404(post_id)
    now = now_iso()
    reply_doc = {
        "id": new_id(),
        "post_id": post_id,
        "actor_type": actor_context["content_actor_type"],
        "actor_id": actor_context["content_actor_id"],
        "author_user_id": actor_context["author_user_id"],
        "author_bot_id": actor_context["author_bot_id"],
        "operator_user_id": actor_context["operator_user_id"],
        "operator_handle": actor_context["operator_handle"],
        "body": payload.body.strip(),
        "created_at": now,
        "updated_at": now,
    }
    await db.lobby_post_replies.insert_one(reply_doc)
    await db.lobby_posts.update_one(
        {"id": post_id},
        {"$inc": {"reply_count": 1}, "$set": {"updated_at": now, "last_engaged_at": now}},
    )
    await log_audit(
        "lobby.replied",
        actor_context["audit_actor_type"],
        actor_context["audit_actor_id"],
        room_id=post.get("linked_room_id"),
        bounty_id=post.get("linked_bounty_id"),
        payload={
            "post_id": post_id,
            "reply_id": reply_doc["id"],
            "actor_type": actor_context["content_actor_type"],
            "operator_user_id": actor_context["operator_user_id"],
        },
    )
    enriched = await enrich_lobby_posts([await get_lobby_post_or_404(post_id)], user["id"])
    return {"post": enriched[0]}


@api_router.post("/lobby/posts/{post_id}/save")
async def save_lobby_post(post_id: str, user: Dict[str, Any] = Depends(require_conversation_participant)):
    await get_lobby_post_or_404(post_id)
    now = now_iso()
    await db.lobby_posts.update_one(
        {"id": post_id},
        {"$addToSet": {"saved_by_user_ids": user["id"]}, "$set": {"updated_at": now, "last_engaged_at": now}},
    )
    await log_audit("lobby.saved", "user", user["id"], payload={"post_id": post_id})
    enriched = await enrich_lobby_posts([await get_lobby_post_or_404(post_id)], user["id"])
    return {"post": enriched[0]}


@api_router.delete("/lobby/posts/{post_id}/save")
async def unsave_lobby_post(post_id: str, user: Dict[str, Any] = Depends(require_conversation_participant)):
    await get_lobby_post_or_404(post_id)
    await db.lobby_posts.update_one(
        {"id": post_id},
        {"$pull": {"saved_by_user_ids": user["id"]}, "$set": {"updated_at": now_iso()}},
    )
    enriched = await enrich_lobby_posts([await get_lobby_post_or_404(post_id)], user["id"])
    return {"post": enriched[0]}


@api_router.post("/lobby/posts/{post_id}/convert-room")
async def convert_lobby_post_to_room(post_id: str, user: Dict[str, Any] = Depends(require_conversation_participant)):
    post = await get_lobby_post_or_404(post_id)
    if post.get("promoted_room_id"):
        enriched = await enrich_lobby_posts([post], user["id"])
        return {"post": enriched[0], "room": None}
    is_operator_author = post.get("operator_user_id") == user["id"]
    is_human_author = post.get("author_user_id") == user["id"]
    if not (is_operator_author or is_human_author or user.get("role") == "admin"):
        raise HTTPException(status_code=403, detail="Only the author or an admin can convert this post")

    base_title = build_room_title_from_post(post.get("body", ""))
    base_slug = build_room_slug_from_text(base_title)
    slug = base_slug
    counter = 2
    while await db.rooms.find_one({"slug": slug}):
        suffix = f"-{counter}"
        slug = f"{base_slug[: max(1, 48 - len(suffix))]}{suffix}"
        counter += 1

    now = now_iso()
    room_doc = {
        "id": new_id(),
        "slug": slug,
        "title": base_title,
        "is_public": True,
        "created_by_user_id": user["id"],
        "source": {"kind": "lobby_post", "post_id": post_id},
        "created_at": now,
        "updated_at": now,
    }
    await db.rooms.insert_one(room_doc)
    await db.room_memberships.insert_one(
        {
            "id": new_id(),
            "room_id": room_doc["id"],
            "member_type": "user",
            "member_id": user["id"],
            "role": "owner",
            "created_at": now,
        }
    )
    await db.channels.insert_one(
        {
            "id": new_id(),
            "room_id": room_doc["id"],
            "slug": "general",
            "title": "General",
            "type": "chat",
            "created_at": now,
        }
    )
    await db.lobby_posts.update_one(
        {"id": post_id},
        {
            "$set": {
                "promoted_room_id": room_doc["id"],
                "promoted_at": now,
                "promoted_by_user_id": user["id"],
                "updated_at": now,
                "last_engaged_at": now,
            }
        },
    )
    await log_audit("room.created", "user", user["id"], room_id=room_doc["id"], payload={"slug": slug, "source": "lobby_post"})
    await log_audit("room.joined", "user", user["id"], room_id=room_doc["id"], payload={"role": "owner", "source": "lobby_post"})
    await log_audit("lobby.promoted", "user", user["id"], room_id=room_doc["id"], payload={"post_id": post_id})
    enriched = await enrich_lobby_posts([await get_lobby_post_or_404(post_id)], user["id"])
    return {"post": enriched[0], "room": sanitize_doc(room_doc)}


@api_router.post("/payments/stripe/checkout")
async def create_checkout_session(
    payload: CheckoutSessionCreate,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
):
    await enforce_rate_limit(
        request,
        key=f"rl:payments:checkout:user:{user['id']}",
        limit=get_rate_limit("RATE_LIMIT_STRIPE_CHECKOUT_PER_HOUR", 10),
        window_seconds=60 * 60,
        actor_type="user",
        actor_id=user["id"],
        endpoint="/payments/stripe/checkout",
        detail="stripe checkout rate limit exceeded",
        error_detail="Too many checkout attempts",
    )
    runtime_config = await get_runtime_stripe_config()
    if not runtime_config.get("secret_key"):
        await log_security_event(
            "payment.stripe.checkout.failure",
            severity="high",
            actor_type="user",
            actor_id=user["id"],
            route="/payments/stripe/checkout",
            payload={**get_request_meta(request), "reason": "stripe_not_configured"},
        )
        return JSONResponse(status_code=400, content={"detail": "Stripe not configured"})
    purpose = (payload.purpose or "membership").strip().lower()
    if purpose not in {"membership", "bot_invite"}:
        raise HTTPException(status_code=400, detail="Checkout purpose must be membership or bot_invite")
    membership_plan = normalize_membership_plan(payload.membership_plan, default="monthly") if purpose == "membership" else None
    if purpose == "membership" and user.get("membership_status") == "active":
        raise HTTPException(status_code=400, detail="Membership already active")
    if purpose == "bot_invite" and not runtime_config.get("bot_invite_price_id"):
        raise HTTPException(status_code=400, detail="Bot invite checkout is not configured")
    if purpose == "membership":
        selected_membership_price_id = (
            runtime_config.get("membership_monthly_price_id")
            if membership_plan == "monthly"
            else runtime_config.get("membership_yearly_price_id")
        )
        if not selected_membership_price_id:
            raise HTTPException(
                status_code=400,
                detail=f"{membership_plan.title()} membership checkout is not configured",
            )
    if not payload.origin_url:
        await log_security_event(
            "payment.stripe.checkout.failure",
            severity="medium",
            actor_type="user",
            actor_id=user["id"],
            route="/payments/stripe/checkout",
            payload={**get_request_meta(request), "reason": "origin_missing"},
        )
        raise HTTPException(status_code=400, detail="Origin URL required")
    allowed_origins = os.environ.get("ALLOWED_ORIGINS", "").split(",")
    allowed_origins = [origin.strip().rstrip("/") for origin in allowed_origins if origin.strip()]
    parsed_origin = urlparse(payload.origin_url)
    if not parsed_origin.scheme or not parsed_origin.netloc:
        await log_security_event(
            "payment.stripe.checkout.failure",
            severity="medium",
            actor_type="user",
            actor_id=user["id"],
            route="/payments/stripe/checkout",
            payload={**get_request_meta(request), "reason": "origin_invalid", "origin_url": payload.origin_url},
        )
        raise HTTPException(status_code=400, detail="Origin URL invalid")
    origin_root = f"{parsed_origin.scheme}://{parsed_origin.netloc}".rstrip("/")
    if allowed_origins and origin_root not in allowed_origins:
        await log_security_event(
            "payment.stripe.checkout.failure",
            severity="medium",
            actor_type="user",
            actor_id=user["id"],
            route="/payments/stripe/checkout",
            payload={**get_request_meta(request), "reason": "origin_not_allowed", "origin_root": origin_root},
        )
        raise HTTPException(status_code=400, detail="Origin URL not allowed")

    host_url = str(request.base_url).rstrip("/")
    webhook_url = f"{host_url}/api/webhook/stripe"
    stripe_checkout = StripeCheckout(
        api_key=runtime_config["secret_key"],
        webhook_secret=runtime_config.get("webhook_secret"),
        webhook_url=webhook_url,
    )
    success_url = (
        f"{origin_root}/join?session_id={{CHECKOUT_SESSION_ID}}"
        if purpose == "membership"
        else f"{origin_root}/app/bots?bot_invite_session={{CHECKOUT_SESSION_ID}}"
    )
    cancel_url = (
        f"{origin_root}/join?canceled=true"
        if purpose == "membership"
        else f"{origin_root}/app/bots?bot_invite_canceled=true"
    )
    metadata = {"user_id": user["id"], "email": user["email"], "purpose": purpose}
    if membership_plan:
        metadata["membership_plan"] = membership_plan
    checkout_price_id = (
        selected_membership_price_id
        if purpose == "membership"
        else runtime_config.get("bot_invite_price_id")
    )

    checkout_request = CheckoutSessionRequest(
        amount=None,
        currency=None,
        price_id=checkout_price_id or None,
        product_name=(
            f"TheSparkPit {membership_plan.title()} Chat Posting Membership"
            if purpose == "membership"
            else "TheSparkPit Bot Invite"
        ),
        success_url=success_url,
        cancel_url=cancel_url,
        metadata=metadata,
        customer_email=user.get("email"),
    )
    try:
        session = await stripe_checkout.create_checkout_session(checkout_request)
    except Exception as error:
        logger.warning("Stripe checkout session creation failed: %s", error)
        await log_security_event(
            "payment.stripe.checkout.failure",
            severity="high",
            actor_type="user",
            actor_id=user["id"],
            route="/payments/stripe/checkout",
            payload={
                **get_request_meta(request),
                "reason": "create_session_failed",
                "message": str(error),
            },
        )
        raise HTTPException(status_code=400, detail="Unable to create Stripe checkout session")

    payment_doc = {
        "id": new_id(),
        "user_id": user["id"],
        "session_id": session.session_id,
        "purpose": purpose,
        "amount": None,
        "currency": None,
        "status": "initiated",
        "payment_status": "unpaid",
        "metadata": {
            **metadata,
            "price_id": checkout_price_id or None,
        },
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.payment_transactions.insert_one(payment_doc)
    if purpose == "membership":
        await db.users.update_one(
            {"id": user["id"]},
            {"$set": {"stripe_session_id": session.session_id, "stripe_session_status": "initiated"}},
        )

    return {"url": session.url, "session_id": session.session_id, "purpose": purpose}


@api_router.get("/payments/stripe/checkout/status/{session_id}")
async def checkout_status(session_id: str, request: Request, user: Dict[str, Any] = Depends(get_current_user)):
    await enforce_rate_limit(
        request,
        key=f"rl:payments:checkout-status:user:{user['id']}",
        limit=get_rate_limit("RATE_LIMIT_STRIPE_STATUS_PER_15_MIN", 60),
        window_seconds=15 * 60,
        actor_type="user",
        actor_id=user["id"],
        endpoint="/payments/stripe/checkout/status",
        detail="stripe checkout status rate limit exceeded",
        error_detail="Too many payment status checks",
    )
    runtime_config = await get_runtime_stripe_config()
    if not runtime_config.get("secret_key"):
        await log_security_event(
            "payment.stripe.checkout.status.failure",
            severity="high",
            actor_type="user",
            actor_id=user["id"],
            route="/payments/stripe/checkout/status",
            payload={**get_request_meta(request), "reason": "stripe_not_configured", "session_id": session_id},
        )
        return JSONResponse(status_code=400, content={"detail": "Stripe not configured"})
    stripe_checkout = StripeCheckout(
        api_key=runtime_config["secret_key"],
        webhook_secret=runtime_config.get("webhook_secret"),
    )
    try:
        status_response = await stripe_checkout.get_checkout_status(session_id)
    except Exception as error:
        logger.warning("Stripe checkout status lookup failed for %s: %s", session_id, error)
        await log_security_event(
            "payment.stripe.checkout.status.failure",
            severity="high",
            actor_type="user",
            actor_id=user["id"],
            route="/payments/stripe/checkout/status",
            payload={
                **get_request_meta(request),
                "reason": "status_lookup_failed",
                "session_id": session_id,
                "message": str(error),
            },
        )
        raise HTTPException(status_code=400, detail="Unable to verify Stripe checkout session")

    transaction = await db.payment_transactions.find_one({"session_id": session_id})
    transaction = sanitize_doc(transaction) if transaction else None
    if not transaction:
        await log_security_event(
            "payment.stripe.checkout.status.failure",
            severity="medium",
            actor_type="user",
            actor_id=user["id"],
            route="/payments/stripe/checkout/status",
            payload={**get_request_meta(request), "reason": "unknown_session", "session_id": session_id},
        )
        raise HTTPException(status_code=404, detail="Unknown checkout session")
    if transaction.get("user_id") != user["id"]:
        await log_security_event(
            "payment.stripe.checkout.status.failure",
            severity="medium",
            actor_type="user",
            actor_id=user["id"],
            route="/payments/stripe/checkout/status",
            payload={**get_request_meta(request), "reason": "session_user_mismatch", "session_id": session_id},
        )
        raise HTTPException(status_code=403, detail="Session does not belong to user")
    new_status = status_response.status
    payment_status = status_response.payment_status
    invite_doc = None
    updates = {
        "status": new_status,
        "payment_status": payment_status,
        "updated_at": now_iso(),
    }
    if transaction:
        await db.payment_transactions.update_one({"session_id": session_id}, {"$set": updates})

    if payment_status == "paid":
        session_details = await fetch_stripe_session(session_id)
        customer_id = session_details.get("customer") if session_details else None
        if transaction.get("purpose") == "membership":
            await activate_membership(
                user["id"],
                session_id,
                customer_id,
                membership_plan=((transaction.get("metadata") or {}).get("membership_plan") or "monthly"),
            )
        elif transaction.get("purpose") == "bot_invite":
            invite_doc = await ensure_bot_invite_for_transaction(transaction)
            if invite_doc:
                updates["generated_invite_id"] = invite_doc["id"]
                await db.payment_transactions.update_one(
                    {"session_id": session_id},
                    {"$set": {"generated_invite_id": invite_doc["id"], "updated_at": now_iso()}},
                )
    elif new_status in ["expired", "canceled"]:
        if transaction.get("purpose") == "membership":
            await db.users.update_one(
                {"id": user["id"]},
                {"$set": {"stripe_session_status": new_status, "updated_at": now_iso()}},
            )

    return {
        "status": status_response.status,
        "payment_status": status_response.payment_status,
        "amount_total": status_response.amount_total,
        "currency": status_response.currency,
        "metadata": status_response.metadata,
        "purpose": transaction.get("purpose") if transaction else None,
        "invite": invite_doc if payment_status == "paid" and transaction.get("purpose") == "bot_invite" else None,
    }


@api_router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    runtime_config = await get_runtime_stripe_config()
    if not runtime_config.get("secret_key") or not runtime_config.get("webhook_secret"):
        await log_security_event(
            "payment.stripe.webhook.failure",
            severity="high",
            actor_type="anonymous",
            actor_id=get_request_ip(request) or "unknown",
            route="/webhook/stripe",
            payload={**get_request_meta(request), "reason": "webhook_not_configured"},
        )
        return JSONResponse(status_code=400, content={"detail": "Stripe webhook not configured"})
    payload = await request.body()
    signature = request.headers.get("Stripe-Signature")
    stripe_checkout = StripeCheckout(
        api_key=runtime_config["secret_key"],
        webhook_secret=runtime_config.get("webhook_secret"),
    )
    try:
        webhook_event = await stripe_checkout.handle_webhook(payload, signature)
    except Exception as error:
        logger.warning("Stripe webhook verification failed: %s", error)
        await log_security_event(
            "payment.stripe.webhook.failure",
            severity="high",
            actor_type="anonymous",
            actor_id=get_request_ip(request) or "unknown",
            route="/webhook/stripe",
            payload={
                **get_request_meta(request),
                "reason": "invalid_signature_or_payload",
                "message": str(error),
            },
        )
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook")

    session_id = webhook_event.session_id
    if not session_id:
        return {"received": True}

    transaction = await db.payment_transactions.find_one({"session_id": session_id})
    if transaction and transaction.get("status") == "paid":
        return {"received": True, "idempotent": True}

    new_status = webhook_event.event_type
    payment_status = webhook_event.payment_status or "unknown"
    session_details = await fetch_stripe_session(session_id)
    customer_id = session_details.get("customer") if session_details else None
    metadata = webhook_event.metadata or {}
    user_id = metadata.get("user_id") if metadata else None

    purpose = metadata.get("purpose") if metadata else None

    if webhook_event.event_type == "checkout.session.completed":
        if user_id and purpose == "membership":
            await activate_membership(
                user_id,
                session_id,
                customer_id,
                membership_plan=(metadata.get("membership_plan") or "monthly"),
            )
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "status": "paid",
                    "payment_status": payment_status,
                    "updated_at": now_iso(),
                    "stripe_customer_id": customer_id,
                    "purpose": purpose or "membership",
                },
                "$setOnInsert": {
                    "id": new_id(),
                    "user_id": user_id,
                    "amount": None,
                    "currency": None,
                    "metadata": metadata,
                    "purpose": purpose or "membership",
                    "created_at": now_iso(),
                },
            },
            upsert=True,
        )
        transaction = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
        if purpose == "bot_invite":
            await ensure_bot_invite_for_transaction(transaction or {})
    elif webhook_event.event_type in ["checkout.session.expired", "charge.refunded"]:
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "status": "expired" if webhook_event.event_type == "checkout.session.expired" else "refunded",
                    "payment_status": payment_status,
                    "updated_at": now_iso(),
                    "stripe_customer_id": customer_id,
                    "purpose": purpose or "membership",
                },
                "$setOnInsert": {
                    "id": new_id(),
                    "user_id": user_id,
                    "amount": None,
                    "currency": None,
                    "metadata": metadata,
                    "purpose": purpose or "membership",
                    "created_at": now_iso(),
                },
            },
            upsert=True,
        )
        if user_id and purpose == "membership":
            await db.users.update_one(
                {"id": user_id},
                {"$set": {"membership_status": "pending", "stripe_session_status": "expired", "updated_at": now_iso()}},
            )

    await db.ops_state.update_one(
        {"id": "stripe_webhook"},
        {
            "$set": {
                "id": "stripe_webhook",
                "last_received_at": now_iso(),
                "event_type": webhook_event.event_type,
            }
        },
        upsert=True,
    )
    return {"received": True}


@api_router.post("/rooms")
async def create_room(payload: RoomCreate, user: Dict[str, Any] = Depends(require_registered_user)):
    existing = await db.rooms.find_one({"slug": payload.slug})
    if existing:
        raise HTTPException(status_code=400, detail="Room slug already exists")
    title_error = moderate_text(payload.title)
    if title_error:
        raise HTTPException(status_code=400, detail=title_error)
    description = normalize_research_text(payload.description, "room description", limit=500)
    research_payload = payload.research.dict() if payload.research else None
    if research_payload:
        if research_payload.get("status") is not None:
            research_payload["status"] = normalize_research_status(research_payload.get("status"))
        if research_payload.get("participation_cadence") is not None:
            research_payload["participation_cadence"] = normalize_research_cadence(
                research_payload.get("participation_cadence")
            )
        for field_name in ("key_sources", "findings", "open_questions", "next_actions"):
            if field_name in research_payload:
                research_payload[field_name] = normalize_research_items(
                    research_payload.get(field_name),
                    field_name.replace("_", " "),
                )
        for field_name, limit in (
            ("question", 500),
            ("summary", 4000),
            ("final_summary", 4000),
            ("note", 2000),
            ("next_step", 280),
            ("recommended_next_step", 280),
            ("bot_directive", 1200),
            ("bot_return_policy", 1200),
        ):
            if field_name in research_payload:
                research_payload[field_name] = normalize_research_text(
                    research_payload.get(field_name),
                    field_name.replace("_", " "),
                    limit=limit,
                )
        research_payload["outputs"] = normalize_research_outputs(research_payload.get("outputs"))
        research_payload = apply_research_protocol_defaults(research_payload)
    now = now_iso()
    actor_context = await get_session_actor_context(user)
    room_doc = {
        "id": new_id(),
        "slug": payload.slug,
        "title": payload.title,
        "is_public": payload.is_public,
        "description": description,
        "source": payload.source.dict() if payload.source else None,
        "research": research_payload,
        "created_by_user_id": user["id"],
        "created_by_actor_type": actor_context["content_actor_type"],
        "created_by_actor_id": actor_context["content_actor_id"],
        "operator_user_id": actor_context["operator_user_id"],
        "created_at": now,
        "updated_at": now,
    }
    if research_payload and actor_context["content_actor_type"] == "bot":
        room_doc["research"] = record_bot_research_activity(research_payload, now)
    await db.rooms.insert_one(room_doc)
    room_doc = sanitize_doc(room_doc)
    if room_doc.get("research"):
        room_doc["research"] = apply_research_protocol_defaults(room_doc.get("research"))
    membership_doc = {
        "id": new_id(),
        "room_id": room_doc["id"],
        "member_type": "user",
        "member_id": user["id"],
        "role": "owner",
        "created_at": now,
    }
    await db.room_memberships.insert_one(membership_doc)
    if actor_context.get("bot"):
        await ensure_bot_room_membership(room_doc["id"], actor_context["bot"], role="owner")
    default_channel = {
        "id": new_id(),
        "room_id": room_doc["id"],
        "slug": "general",
        "title": "General",
        "type": "chat",
        "created_at": now,
    }
    await db.channels.insert_one(default_channel)
    default_channel = sanitize_doc(default_channel)
    await log_audit(
        "room.created",
        actor_context["audit_actor_type"],
        actor_context["audit_actor_id"],
        room_id=room_doc["id"],
        payload={
            "slug": payload.slug,
            "actor_type": actor_context["content_actor_type"],
            "operator_user_id": actor_context["operator_user_id"],
        },
    )
    await log_audit(
        "room.joined",
        "user",
        user["id"],
        room_id=room_doc["id"],
        payload={"role": "owner"},
    )
    if actor_context.get("bot"):
        await log_audit(
            "bot.joined",
            "bot",
            actor_context["bot"]["id"],
            room_id=room_doc["id"],
            payload={"role": "owner", "operator_user_id": user["id"], "source": "room_create"},
        )
    room_doc["participants"] = await build_room_participants(room_doc["id"])
    return {"room": room_doc, "default_channel": default_channel}


@api_router.get("/rooms")
async def list_rooms(user: Dict[str, Any] = Depends(require_registered_user)):
    memberships = await db.room_memberships.find(
        {"member_type": "user", "member_id": user["id"]}, {"_id": 0}
    ).to_list(1000)
    joined_room_ids = {m["room_id"] for m in memberships}
    active_bot = user.get("active_bot") or await resolve_session_bot(user)
    bot_memberships = []
    joined_bot_room_ids = set()
    if active_bot:
        bot_memberships = await db.room_memberships.find(
            {"member_type": "bot", "member_id": active_bot["id"]}, {"_id": 0}
        ).to_list(1000)
        joined_bot_room_ids = {m["room_id"] for m in bot_memberships}
    visible_room_ids = list(joined_room_ids | joined_bot_room_ids)
    rooms = await db.rooms.find(
        {"$or": [{"is_public": True}, {"id": {"$in": visible_room_ids}}]}, {"_id": 0}
    ).to_list(1000)
    for room in rooms:
        if (room.get("source") or {}).get("kind") == "research_project":
            room["research"] = apply_research_protocol_defaults(room.get("research") or {})
        room["joined_as_user"] = room["id"] in joined_room_ids
        room["joined_as_bot"] = room["id"] in joined_bot_room_ids
        room["joined"] = room["joined_as_user"] or room["joined_as_bot"]
    return {"items": rooms}


@api_router.get("/rooms/{slug}")
async def get_room(slug: str, user: Dict[str, Any] = Depends(require_registered_user)):
    room = await db.rooms.find_one({"slug": slug})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    room = sanitize_doc(room)
    if (room.get("source") or {}).get("kind") == "research_project":
        room["research"] = apply_research_protocol_defaults(room.get("research") or {})
    membership, bot_membership = await get_room_membership_state(user, room["id"])
    if not room.get("is_public") and not membership and not bot_membership and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Room is private")
    channels = await db.channels.find({"room_id": room["id"]}, {"_id": 0}).to_list(200)
    room["participants"] = await build_room_participants(room["id"])
    return {"room": room, "channels": channels, "membership": membership, "bot_membership": bot_membership}


@api_router.patch("/rooms/{slug}/research")
async def update_room_research(
    slug: str,
    payload: RoomResearchUpdate,
    user: Dict[str, Any] = Depends(require_registered_user),
):
    room = await get_research_workspace_or_404(slug, user)
    actor_context = await get_session_actor_context(user)
    if actor_context.get("bot"):
        await ensure_bot_room_membership(room["id"], actor_context["bot"])

    updates: Dict[str, Any] = {}
    changed_fields: List[str] = []
    current_research = apply_research_protocol_defaults(room.get("research") or {})

    if payload.question is not None:
        updates["question"] = normalize_research_text(payload.question, "question", limit=500)
        changed_fields.append("question")
    if payload.summary is not None:
        updates["summary"] = normalize_research_text(payload.summary, "summary")
        changed_fields.append("summary")
    if payload.final_summary is not None:
        updates["final_summary"] = normalize_research_text(payload.final_summary, "final summary")
        changed_fields.append("final_summary")
    if payload.note is not None:
        updates["note"] = normalize_research_text(payload.note, "note", limit=2000)
        changed_fields.append("note")
    if payload.bot_directive is not None:
        updates["bot_directive"] = normalize_research_text(
            payload.bot_directive,
            "bot directive",
            limit=1200,
        )
        changed_fields.append("bot_directive")
    if payload.bot_return_policy is not None:
        updates["bot_return_policy"] = normalize_research_text(
            payload.bot_return_policy,
            "bot return policy",
            limit=1200,
        )
        changed_fields.append("bot_return_policy")
    if payload.status is not None:
        updates["status"] = normalize_research_status(payload.status)
        changed_fields.append("status")
    if payload.participation_cadence is not None:
        updates["participation_cadence"] = normalize_research_cadence(payload.participation_cadence)
        changed_fields.append("participation_cadence")
    if payload.recommended_next_step is not None:
        updates["recommended_next_step"] = normalize_research_text(
            payload.recommended_next_step,
            "recommended next step",
            limit=280,
        )
        changed_fields.append("recommended_next_step")
    if payload.key_sources is not None:
        updates["key_sources"] = normalize_research_items(payload.key_sources, "sources")
        changed_fields.append("key_sources")
    if payload.findings is not None:
        updates["findings"] = normalize_research_items(payload.findings, "findings")
        changed_fields.append("findings")
    if payload.open_questions is not None:
        updates["open_questions"] = normalize_research_items(payload.open_questions, "open questions")
        changed_fields.append("open_questions")
    if payload.next_actions is not None:
        updates["next_actions"] = normalize_research_items(payload.next_actions, "next actions")
        changed_fields.append("next_actions")

    if not updates:
        raise HTTPException(status_code=400, detail="No research updates provided")

    now = now_iso()
    merged_research = {
        **current_research,
        **updates,
        "updated_at": now,
        "updated_by_user_id": user["id"],
        "updated_by_actor_type": actor_context["content_actor_type"],
        "updated_by_actor_id": actor_context["content_actor_id"],
        "updated_by_operator_user_id": actor_context["operator_user_id"],
    }
    merged_research = apply_research_protocol_defaults(merged_research)
    if actor_context["content_actor_type"] == "bot":
        merged_research = record_bot_research_activity(merged_research, now)

    room_updates: Dict[str, Any] = {"research": merged_research, "updated_at": now}
    if "question" in updates:
        room_updates["description"] = updates["question"]

    await db.rooms.update_one({"id": room["id"]}, {"$set": room_updates})
    updated_room = sanitize_doc(await db.rooms.find_one({"id": room["id"]}, {"_id": 0}))
    if updated_room.get("research"):
        updated_room["research"] = apply_research_protocol_defaults(updated_room.get("research"))
    updated_room["participants"] = await build_room_participants(room["id"])

    await log_audit(
        "room.research.updated",
        actor_context["audit_actor_type"],
        actor_context["audit_actor_id"],
        room_id=room["id"],
        payload={
            "fields": changed_fields,
            "status": merged_research.get("status"),
            "actor_type": actor_context["content_actor_type"],
            "operator_user_id": actor_context["operator_user_id"],
        },
    )
    await log_room_event(
        room_id=room["id"],
        event_type="research.updated",
        actor_user_id=user["id"],
        actor_type=actor_context["content_actor_type"],
        actor_id=actor_context["content_actor_id"],
        operator_user_id=actor_context["operator_user_id"],
        payload={"fields": changed_fields, "status": merged_research.get("status")},
    )
    return {"room": updated_room}


@api_router.post("/rooms/{slug}/research/items")
async def append_room_research_item(
    slug: str,
    payload: RoomResearchListItemCreate,
    user: Dict[str, Any] = Depends(require_registered_user),
):
    room = await get_research_workspace_or_404(slug, user)
    actor_context = await get_session_actor_context(user)
    if actor_context.get("bot"):
        await ensure_bot_room_membership(room["id"], actor_context["bot"])

    field = (payload.field or "").strip()
    allowed_fields = {
        "key_sources": "sources",
        "findings": "findings",
        "open_questions": "open questions",
        "next_actions": "next actions",
    }
    if field not in allowed_fields:
        raise HTTPException(status_code=400, detail="Invalid research list field")
    value = normalize_research_text(payload.value, allowed_fields[field], limit=280)
    if not value:
        raise HTTPException(status_code=400, detail="Research item is required")

    current_research = apply_research_protocol_defaults(room.get("research") or {})
    next_items = normalize_research_items([*(current_research.get(field) or []), value], allowed_fields[field])
    now = now_iso()
    merged_research = {
        **current_research,
        field: next_items,
        "updated_at": now,
        "updated_by_user_id": user["id"],
        "updated_by_actor_type": actor_context["content_actor_type"],
        "updated_by_actor_id": actor_context["content_actor_id"],
        "updated_by_operator_user_id": actor_context["operator_user_id"],
    }
    if actor_context["content_actor_type"] == "bot":
        merged_research = record_bot_research_activity(merged_research, now)
    await db.rooms.update_one(
        {"id": room["id"]},
        {"$set": {"research": merged_research, "updated_at": now}},
    )
    updated_room = sanitize_doc(await db.rooms.find_one({"id": room["id"]}, {"_id": 0}))
    if updated_room.get("research"):
        updated_room["research"] = apply_research_protocol_defaults(updated_room.get("research"))
    updated_room["participants"] = await build_room_participants(room["id"])
    await log_audit(
        "room.research.updated",
        actor_context["audit_actor_type"],
        actor_context["audit_actor_id"],
        room_id=room["id"],
        payload={
            "fields": [field],
            "status": merged_research.get("status"),
            "actor_type": actor_context["content_actor_type"],
            "operator_user_id": actor_context["operator_user_id"],
        },
    )
    await log_room_event(
        room_id=room["id"],
        event_type="research.updated",
        actor_user_id=user["id"],
        actor_type=actor_context["content_actor_type"],
        actor_id=actor_context["content_actor_id"],
        operator_user_id=actor_context["operator_user_id"],
        payload={"fields": [field], "status": merged_research.get("status")},
    )
    return {"room": updated_room}


@api_router.post("/rooms/{slug}/research/promote-task")
async def promote_research_task(
    slug: str,
    payload: ResearchPromoteTaskCreate,
    user: Dict[str, Any] = Depends(require_registered_user),
):
    room = await get_research_workspace_or_404(slug, user)
    actor_context = await get_session_actor_context(user)
    if actor_context.get("bot"):
        await ensure_bot_room_membership(room["id"], actor_context["bot"])
    research = apply_research_protocol_defaults(room.get("research") or {})
    source_text = normalize_research_text(payload.source_text, "handoff item", limit=280)
    title = normalize_research_text(
        payload.title or build_research_handoff_title(source_text, "Research task"),
        "task title",
        limit=120,
    )
    summary = (research.get("summary") or "").strip()
    question = (research.get("question") or room.get("description") or "").strip()
    description = normalize_research_text(
        payload.description
        or "\n\n".join(
            part
            for part in [
                f"Promoted from research workspace: {room.get('title')}",
                f"Research question: {question}" if question else "",
                f"Next action: {source_text}",
                f"Current summary: {summary}" if summary else "",
                "This task was generated from a research handoff.",
            ]
            if part
        ),
        "task description",
    )
    now = now_iso()
    task_doc = {
        "id": new_id(),
        "room_id": room["id"],
        "title": title,
        "description": description,
        "priority": "normal",
        "tags": ["research", "handoff"],
        "state": "open",
        "created_by_user_id": user["id"],
        "created_by_actor_type": actor_context["content_actor_type"],
        "created_by_actor_id": actor_context["content_actor_id"],
        "operator_user_id": actor_context["operator_user_id"],
        "claimed_by_user_id": None,
        "assignee_user_id": None,
        "selected_proposal_id": None,
        "auto_select_enabled": False,
        "auto_select_min_votes": 5,
        "auto_select_margin": 0.2,
        "created_at": now,
        "updated_at": now,
    }
    await db.tasks.insert_one(task_doc)
    await log_task_event(
        task_doc["id"],
        task_doc["room_id"],
        "task.created_from_research",
        user["id"],
        {"title": task_doc["title"], "source_text": source_text},
        actor_type=actor_context["content_actor_type"],
        actor_id=actor_context["content_actor_id"],
        operator_user_id=actor_context["operator_user_id"],
    )

    outputs = normalize_research_outputs(research.get("outputs"))
    outputs.insert(
        0,
        {
            "id": new_id(),
            "type": "task",
            "resource_id": task_doc["id"],
            "title": task_doc["title"],
            "status": task_doc["state"],
            "source_text": source_text,
            "created_at": now,
            "created_by_user_id": user["id"],
            "created_by_actor_type": actor_context["content_actor_type"],
            "created_by_actor_id": actor_context["content_actor_id"],
            "operator_user_id": actor_context["operator_user_id"],
        },
    )
    merged_research = {
        **research,
        "outputs": outputs[:24],
        "updated_at": now,
        "updated_by_user_id": user["id"],
        "updated_by_actor_type": actor_context["content_actor_type"],
        "updated_by_actor_id": actor_context["content_actor_id"],
        "updated_by_operator_user_id": actor_context["operator_user_id"],
    }
    if actor_context["content_actor_type"] == "bot":
        merged_research = record_bot_research_activity(merged_research, now)
    await db.rooms.update_one(
        {"id": room["id"]},
        {"$set": {"research": merged_research, "updated_at": now}},
    )
    updated_room = sanitize_doc(await db.rooms.find_one({"id": room["id"]}, {"_id": 0}))
    if updated_room.get("research"):
        updated_room["research"] = apply_research_protocol_defaults(updated_room.get("research"))
    updated_room["participants"] = await build_room_participants(room["id"])
    await log_audit(
        "research.task_promoted",
        actor_context["audit_actor_type"],
        actor_context["audit_actor_id"],
        room_id=room["id"],
        payload={
            "task_id": task_doc["id"],
            "source_text": source_text,
            "actor_type": actor_context["content_actor_type"],
            "operator_user_id": actor_context["operator_user_id"],
        },
    )
    await log_room_event(
        room_id=room["id"],
        event_type="research.task_promoted",
        actor_user_id=user["id"],
        actor_type=actor_context["content_actor_type"],
        actor_id=actor_context["content_actor_id"],
        operator_user_id=actor_context["operator_user_id"],
        payload={"task_id": task_doc["id"], "title": task_doc["title"]},
    )
    return {"task": sanitize_doc(task_doc), "room": updated_room}


@api_router.post("/rooms/{slug}/research/promote-bounty")
async def promote_research_bounty(
    slug: str,
    payload: ResearchPromoteBountyCreate,
    user: Dict[str, Any] = Depends(require_registered_user),
):
    room = await get_research_workspace_or_404(slug, user)
    actor_context = await get_session_actor_context(user)
    if actor_context.get("bot"):
        await ensure_bot_room_membership(room["id"], actor_context["bot"])
    research = apply_research_protocol_defaults(room.get("research") or {})
    source_text = normalize_research_text(payload.source_text, "handoff item", limit=280)
    title = normalize_research_text(
        payload.title or build_research_handoff_title(source_text, "Research bounty"),
        "bounty title",
        limit=120,
    )
    summary = (research.get("summary") or "").strip()
    question = (research.get("question") or room.get("description") or "").strip()
    description = normalize_research_text(
        payload.description
        or "\n\n".join(
            part
            for part in [
                f"Promoted from research workspace: {room.get('title')}",
                f"Research question: {question}" if question else "",
                f"Unresolved problem: {source_text}",
                f"Current summary: {summary}" if summary else "",
                "This bounty was generated from a research handoff.",
            ]
            if part
        ),
        "bounty description",
    )
    normalized_tags = normalize_tags(["research", "handoff", *(payload.tags or [])])
    now = now_iso()
    bounty_doc = {
        "id": new_id(),
        "created_by_user_id": user["id"],
        "created_by_actor_type": actor_context["content_actor_type"],
        "created_by_actor_id": actor_context["content_actor_id"],
        "operator_user_id": actor_context["operator_user_id"],
        "room_id": room["id"],
        "title": title,
        "description": description,
        "tags": normalized_tags,
        "reward_amount": None,
        "reward_currency": None,
        "status": "open",
        "claimed_by_type": None,
        "claimed_by_id": None,
        "due_at": None,
        "created_at": now,
        "updated_at": now,
    }
    await db.bounties.insert_one(bounty_doc)
    await log_audit(
        "bounty.created",
        "user",
        user["id"],
        room_id=room["id"],
        payload={"bounty_id": bounty_doc["id"], "title": bounty_doc["title"]},
    )

    outputs = normalize_research_outputs(research.get("outputs"))
    outputs.insert(
        0,
        {
            "id": new_id(),
            "type": "bounty",
            "resource_id": bounty_doc["id"],
            "title": bounty_doc["title"],
            "status": bounty_doc["status"],
            "source_text": source_text,
            "created_at": now,
            "created_by_user_id": user["id"],
            "created_by_actor_type": actor_context["content_actor_type"],
            "created_by_actor_id": actor_context["content_actor_id"],
            "operator_user_id": actor_context["operator_user_id"],
        },
    )
    merged_research = {
        **research,
        "outputs": outputs[:24],
        "updated_at": now,
        "updated_by_user_id": user["id"],
        "updated_by_actor_type": actor_context["content_actor_type"],
        "updated_by_actor_id": actor_context["content_actor_id"],
        "updated_by_operator_user_id": actor_context["operator_user_id"],
    }
    if actor_context["content_actor_type"] == "bot":
        merged_research = record_bot_research_activity(merged_research, now)
    await db.rooms.update_one(
        {"id": room["id"]},
        {"$set": {"research": merged_research, "updated_at": now}},
    )
    updated_room = sanitize_doc(await db.rooms.find_one({"id": room["id"]}, {"_id": 0}))
    if updated_room.get("research"):
        updated_room["research"] = apply_research_protocol_defaults(updated_room.get("research"))
    updated_room["participants"] = await build_room_participants(room["id"])
    await log_audit(
        "research.bounty_promoted",
        actor_context["audit_actor_type"],
        actor_context["audit_actor_id"],
        room_id=room["id"],
        payload={
            "bounty_id": bounty_doc["id"],
            "source_text": source_text,
            "actor_type": actor_context["content_actor_type"],
            "operator_user_id": actor_context["operator_user_id"],
        },
    )
    await log_room_event(
        room_id=room["id"],
        event_type="research.bounty_promoted",
        actor_user_id=user["id"],
        actor_type=actor_context["content_actor_type"],
        actor_id=actor_context["content_actor_id"],
        operator_user_id=actor_context["operator_user_id"],
        payload={"bounty_id": bounty_doc["id"], "title": bounty_doc["title"]},
    )
    return {"bounty": sanitize_doc(bounty_doc), "room": updated_room}


@api_router.post("/rooms/{slug}/join")
async def join_room(slug: str, user: Dict[str, Any] = Depends(require_registered_user)):
    room = await db.rooms.find_one({"slug": slug})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    room = sanitize_doc(room)
    if not room.get("is_public"):
        raise HTTPException(status_code=403, detail="Room is private")
    existing = await db.room_memberships.find_one(
        {"room_id": room["id"], "member_type": "user", "member_id": user["id"]}
    )
    if not existing:
        membership_doc = {
            "id": new_id(),
            "room_id": room["id"],
            "member_type": "user",
            "member_id": user["id"],
            "role": "member",
            "created_at": now_iso(),
        }
        await db.room_memberships.insert_one(membership_doc)
        await log_audit("room.joined", "user", user["id"], room_id=room["id"], payload={"role": "member"})
        await emit_bot_webhook_event(
            event_type="room.joined",
            room_id=room["id"],
            event={
                "id": new_id(),
                "event_type": "room.joined",
                "occurred_at": membership_doc["created_at"],
                "room_id": room["id"],
                "room_slug": room.get("slug"),
                "user": {"id": user["id"], "handle": user.get("handle")},
                "role": "member",
            },
        )
    actor_context = await get_session_actor_context(user)
    if actor_context.get("bot"):
        bot_joined = await ensure_bot_room_membership(room["id"], actor_context["bot"])
        if bot_joined:
            await log_audit(
                "bot.joined",
                "bot",
                actor_context["bot"]["id"],
                room_id=room["id"],
                payload={"operator_user_id": user["id"], "source": "bot_operator_session"},
            )
            await emit_bot_webhook_event(
                event_type="bot.joined",
                room_id=room["id"],
                exclude_bot_ids=[actor_context["bot"]["id"]],
                event={
                    "id": new_id(),
                    "event_type": "bot.joined",
                    "occurred_at": now_iso(),
                    "room_id": room["id"],
                    "room_slug": room.get("slug"),
                    "bot": {"id": actor_context["bot"]["id"], "handle": actor_context["bot"].get("handle")},
                    "operator_user_id": user["id"],
                    "source": "bot_operator_session",
                },
            )
    return {"joined": True}


@api_router.post("/rooms/{slug}/join-bot")
async def join_bot_room(slug: str, bot_id: str = Query(...), user: Dict[str, Any] = Depends(require_registered_user)):
    room = await db.rooms.find_one({"slug": slug})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    room = sanitize_doc(room)
    if (room.get("source") or {}).get("kind") == "research_project":
        room["research"] = apply_research_protocol_defaults(room.get("research") or {})
    bot = await db.bots.find_one({"id": bot_id, "owner_user_id": user["id"]})
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    if not room.get("is_public") and user.get("role") != "admin" and not await can_manage_room(user, room["id"]):
        raise HTTPException(status_code=403, detail="Not allowed to add bots to this room")
    existing = await db.room_memberships.find_one(
        {"room_id": room["id"], "member_type": "bot", "member_id": bot_id}
    )
    if not existing:
        membership_doc = {
            "id": new_id(),
            "room_id": room["id"],
            "member_type": "bot",
            "member_id": bot_id,
            "role": "member",
            "created_at": now_iso(),
        }
        await db.room_memberships.insert_one(membership_doc)
        await log_audit("bot.joined", "user", user["id"], room_id=room["id"], payload={"bot_id": bot_id})
        await emit_bot_webhook_event(
            event_type="bot.joined",
            room_id=room["id"],
            exclude_bot_ids=[bot_id],
            event={
                "id": new_id(),
                "event_type": "bot.joined",
                "occurred_at": membership_doc["created_at"],
                "room_id": room["id"],
                "room_slug": room.get("slug"),
                "bot": {"id": bot_id, "handle": bot.get("handle")},
                "operator_user_id": user["id"],
                "source": "join_bot",
            },
        )
    allowed_room_ids = normalize_scope_ids([*(bot.get("allowed_room_ids") or []), room["id"]])
    await db.bots.update_one(
        {"id": bot_id},
        {"$set": {"allowed_room_ids": allowed_room_ids, "updated_at": now_iso()}},
    )
    room["participants"] = await build_room_participants(room["id"])
    return {"joined": True, "room": room}


@api_router.get("/rooms/{room_id}/memory")
async def get_room_memory(room_id: str, user: Dict[str, Any] = Depends(require_registered_user)):
    room = await db.rooms.find_one({"id": room_id})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if not await can_access_room(user, room_id):
        raise HTTPException(status_code=403, detail="Join the room first")
    artifacts = await db.artifacts.find(
        {"room_id": room_id, "kind": {"$in": ["memory_episdodic", "memory_semantic", "memory_episodic"]}},
        {"_id": 0},
    ).sort("created_at", -1).to_list(20)
    episodic = next((item for item in artifacts if item.get("kind") in ["memory_episdodic", "memory_episodic"]), None)
    semantic = next((item for item in artifacts if item.get("kind") == "memory_semantic"), None)
    await log_room_event(
        room_id=room_id,
        event_type="memory.viewed",
        actor_user_id=user["id"],
        payload={
            "has_episodic": bool(episodic),
            "has_semantic": bool(semantic),
        },
    )
    return {
        "room_id": room_id,
        "episodic": sanitize_doc(episodic) if episodic else None,
        "semantic": sanitize_doc(semantic) if semantic else None,
    }


@api_router.post("/rooms/{room_id}/memory/summarize")
async def summarize_room_memory(
    room_id: str,
    payload: RoomMemorySummarizeRequest,
    user: Dict[str, Any] = Depends(require_registered_user),
):
    room = await db.rooms.find_one({"id": room_id})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if not await can_access_room(user, room_id):
        raise HTTPException(status_code=403, detail="Join the room first")
    if os.environ.get("ROOM_SUMMARY_ENABLED", "0") != "1":
        raise HTTPException(status_code=403, detail="Room summarization is disabled")
    await enqueue_job(
        "summarize_room",
        {
            "room_id": room_id,
            "actor_user_id": user["id"],
            "note": (payload.note or "").strip(),
        },
    )
    await log_room_event(
        room_id=room_id,
        event_type="memory.summarize_requested",
        actor_user_id=user["id"],
        payload={"queued": True},
    )
    return {"status": "queued", "room_id": room_id}


@api_router.post("/rooms/{slug}/channels")
async def create_channel(slug: str, payload: ChannelCreate, user: Dict[str, Any] = Depends(require_registered_user)):
    room = await db.rooms.find_one({"slug": slug})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    room = sanitize_doc(room)
    membership = await db.room_memberships.find_one(
        {"room_id": room["id"], "member_type": "user", "member_id": user["id"]}
    )
    membership = sanitize_doc(membership) if membership else None
    if user.get("role") != "admin" and (not membership or membership.get("role") not in ["owner", "moderator"]):
        raise HTTPException(status_code=403, detail="Not allowed to create channels")
    existing = await db.channels.find_one({"room_id": room["id"], "slug": payload.slug})
    if existing:
        raise HTTPException(status_code=400, detail="Channel slug already exists")
    channel_doc = {
        "id": new_id(),
        "room_id": room["id"],
        "slug": payload.slug,
        "title": payload.title,
        "type": payload.type,
        "created_at": now_iso(),
    }
    await db.channels.insert_one(channel_doc)
    channel_doc = sanitize_doc(channel_doc)
    await log_audit("channel.created", "user", user["id"], room_id=room["id"], channel_id=channel_doc["id"], payload={"slug": payload.slug})
    return {"channel": channel_doc}


@api_router.get("/channels/{channel_id}/messages")
async def get_messages(
    channel_id: str,
    cursor: Optional[str] = None,
    limit: int = 50,
    user: Dict[str, Any] = Depends(require_registered_user),
):
    channel = await db.channels.find_one({"id": channel_id})
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    channel = sanitize_doc(channel)
    if not await can_access_room(user, channel["room_id"]):
        raise HTTPException(status_code=403, detail="Join the room first")
    query: Dict[str, Any] = {"channel_id": channel_id}
    if cursor:
        query["created_at"] = {"$lt": cursor}
    messages = await db.messages.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    messages.reverse()
    next_cursor = messages[0]["created_at"] if messages else None
    return {"items": messages, "next_cursor": next_cursor}


@api_router.post("/channels/{channel_id}/messages")
async def post_message(
    channel_id: str,
    payload: MessageCreate,
    user: Dict[str, Any] = Depends(require_conversation_participant),
):
    actor_context = await get_session_actor_context(user)
    allowed = await rate_limit(
        f"rl:msg:{actor_context['content_actor_type']}:{actor_context['content_actor_id']}",
        get_rate_limit("RATE_LIMIT_MESSAGES_PER_MIN", 30),
        60,
    )
    if not allowed:
        await log_rate_limit_event(
            actor_context["audit_actor_type"],
            actor_context["audit_actor_id"],
            "/channels/{channel_id}/messages",
            "rate limit exceeded",
        )
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    if await detect_duplicate_content(
        actor_context["audit_actor_type"],
        actor_context["audit_actor_id"],
        payload.content,
    ):
        await log_moderation_event(
            actor_context["audit_actor_type"],
            actor_context["audit_actor_id"],
            "message",
            payload.content,
            "duplicate content spam",
            metadata={"channel_id": channel_id, "operator_user_id": actor_context.get("operator_user_id")},
        )
        if await should_alert_on_moderation(actor_context["audit_actor_type"], actor_context["audit_actor_id"]):
            await log_alert_event(
                "moderation.spike",
                {"actor_type": actor_context["audit_actor_type"], "actor_id": actor_context["audit_actor_id"]},
            )
        raise HTTPException(status_code=429, detail="Duplicate content detected")
    moderation_error = moderate_text(payload.content)
    if moderation_error:
        await log_moderation_event(
            actor_context["audit_actor_type"],
            actor_context["audit_actor_id"],
            "message",
            payload.content,
            moderation_error,
            metadata={"channel_id": channel_id, "operator_user_id": actor_context.get("operator_user_id")},
        )
        if await should_alert_on_moderation(actor_context["audit_actor_type"], actor_context["audit_actor_id"]):
            await log_alert_event(
                "moderation.spike",
                {"actor_type": actor_context["audit_actor_type"], "actor_id": actor_context["audit_actor_id"]},
            )
        raise HTTPException(status_code=400, detail=moderation_error)
    channel = await db.channels.find_one({"id": channel_id})
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    channel = sanitize_doc(channel)
    user_membership, bot_membership = await get_room_membership_state(user, channel["room_id"])
    if not user_membership and not bot_membership:
        raise HTTPException(status_code=403, detail="Join the room first")
    if actor_context.get("bot") and not bot_membership:
        await ensure_bot_room_membership(channel["room_id"], actor_context["bot"])
    if user.get("is_shadow_banned") or (actor_context.get("bot") or {}).get("is_shadow_banned"):
        return {
            "message": {
                "id": new_id(),
                "channel_id": channel_id,
                "sender_type": "bot" if actor_context["content_actor_type"] == "bot" else "user",
                "sender_id": actor_context["content_actor_id"],
                "sender_handle": actor_context["display_handle"],
                "actor_type": actor_context["content_actor_type"],
                "actor_id": actor_context["content_actor_id"],
                "operator_user_id": actor_context["operator_user_id"],
                "operator_handle": actor_context["operator_handle"],
                "content": payload.content,
                "metadata": {"shadow_banned": True, "bot": actor_context["content_actor_type"] == "bot"},
                "created_at": now_iso(),
            }
        }
    message_doc = {
        "id": new_id(),
        "channel_id": channel_id,
        "sender_type": "bot" if actor_context["content_actor_type"] == "bot" else "user",
        "sender_id": actor_context["content_actor_id"],
        "sender_handle": actor_context["display_handle"],
        "actor_type": actor_context["content_actor_type"],
        "actor_id": actor_context["content_actor_id"],
        "operator_user_id": actor_context["operator_user_id"],
        "operator_handle": actor_context["operator_handle"],
        "content": payload.content,
        "metadata": {"bot": actor_context["content_actor_type"] == "bot"},
        "created_at": now_iso(),
    }
    await db.messages.insert_one(message_doc)
    if actor_context["content_actor_type"] == "bot":
        room_doc = await db.rooms.find_one({"id": channel["room_id"]}, {"_id": 0, "research": 1, "source": 1})
        if room_doc and (room_doc.get("source") or {}).get("kind") == "research_project":
            research = record_bot_research_activity(room_doc.get("research") or {}, message_doc["created_at"])
            await db.rooms.update_one(
                {"id": channel["room_id"]},
                {"$set": {"research": research, "updated_at": message_doc["created_at"]}},
            )
    message_doc = sanitize_doc(message_doc)
    await log_audit(
        "message.posted",
        actor_context["audit_actor_type"],
        actor_context["audit_actor_id"],
        room_id=channel["room_id"],
        channel_id=channel_id,
        payload={
            "actor_type": actor_context["content_actor_type"],
            "operator_user_id": actor_context["operator_user_id"],
        },
    )
    await manager.broadcast(channel_id, {"type": "message_created", "message": message_doc})
    await enqueue_job("index_message", message_doc)
    await emit_bot_webhook_event(
        event_type="message.created",
        room_id=channel["room_id"],
        exclude_bot_ids=[actor_context["content_actor_id"]] if actor_context["content_actor_type"] == "bot" else [],
        event={
            "id": new_id(),
            "event_type": "message.created",
            "occurred_at": message_doc["created_at"],
            "room_id": channel["room_id"],
            "channel_id": channel_id,
            "message": message_doc,
        },
    )
    if os.environ.get("BOT_AUTO_REPLY", "0") == "1":
        await enqueue_job(
            "generate_bot_reply",
            {
                "channel_id": channel_id,
                "user_message_id": message_doc["id"],
                "user_text": message_doc["content"],
            },
        )
    return {"message": message_doc}


@api_router.post("/bot/messages")
async def post_bot_message(payload: BotMessageCreate, bot: Dict[str, Any] = Depends(get_current_bot)):
    allowed = await rate_limit(
        f"rl:msg:bot:{bot['id']}",
        get_rate_limit("RATE_LIMIT_BOT_MESSAGES_PER_MIN", 60),
        60,
    )
    if not allowed:
        await log_rate_limit_event("bot", bot["id"], "/bot/messages", "rate limit exceeded")
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    if await detect_duplicate_content("bot", bot["id"], payload.content):
        await log_moderation_event(
            "bot",
            bot["id"],
            "message",
            payload.content,
            "duplicate content spam",
            metadata={"channel_id": payload.channel_id},
        )
        if await should_alert_on_moderation("bot", bot["id"]):
            await log_alert_event("moderation.spike", {"actor_type": "bot", "actor_id": bot["id"]})
        raise HTTPException(status_code=429, detail="Duplicate content detected")
    moderation_error = moderate_text(payload.content)
    if moderation_error:
        await log_moderation_event(
            "bot",
            bot["id"],
            "message",
            payload.content,
            moderation_error,
            metadata={"channel_id": payload.channel_id},
        )
        if await should_alert_on_moderation("bot", bot["id"]):
            await log_alert_event("moderation.spike", {"actor_type": "bot", "actor_id": bot["id"]})
        raise HTTPException(status_code=400, detail=moderation_error)
    channel = await db.channels.find_one({"id": payload.channel_id})
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    channel = sanitize_doc(channel)
    scopes = bot.get("scopes", {})
    allowed_channels = scopes.get("channels", [])
    allowed_rooms = scopes.get("rooms", [])
    if allowed_channels and payload.channel_id not in allowed_channels:
        raise HTTPException(status_code=403, detail="Bot not authorized for channel")
    if allowed_rooms and channel["room_id"] not in allowed_rooms:
        raise HTTPException(status_code=403, detail="Bot not authorized for room")

    membership = await db.room_memberships.find_one(
        {"room_id": channel["room_id"], "member_type": "bot", "member_id": bot["id"]}
    )
    if not membership:
        raise HTTPException(status_code=403, detail="Bot not in room")
    if bot.get("is_shadow_banned"):
        return {
            "message": {
                "id": new_id(),
                "channel_id": payload.channel_id,
                "sender_type": "bot",
                "sender_id": bot["id"],
                "sender_handle": bot.get("handle"),
                "actor_type": "bot",
                "actor_id": bot["id"],
                "operator_user_id": None,
                "operator_handle": None,
                "content": payload.content,
                "metadata": {"bot": True, "shadow_banned": True},
                "created_at": now_iso(),
            }
        }

    message_doc = {
        "id": new_id(),
        "channel_id": payload.channel_id,
        "sender_type": "bot",
        "sender_id": bot["id"],
        "sender_handle": bot.get("handle"),
        "actor_type": "bot",
        "actor_id": bot["id"],
        "operator_user_id": None,
        "operator_handle": None,
        "content": payload.content,
        "metadata": {"bot": True},
        "created_at": now_iso(),
    }
    await db.messages.insert_one(message_doc)
    room_doc = await db.rooms.find_one({"id": channel["room_id"]}, {"_id": 0, "research": 1, "source": 1})
    if room_doc and (room_doc.get("source") or {}).get("kind") == "research_project":
        research = record_bot_research_activity(room_doc.get("research") or {}, message_doc["created_at"])
        await db.rooms.update_one(
            {"id": channel["room_id"]},
            {"$set": {"research": research, "updated_at": message_doc["created_at"]}},
        )
    message_doc = sanitize_doc(message_doc)
    await log_audit("message.posted", "bot", bot["id"], room_id=channel["room_id"], channel_id=payload.channel_id)
    await manager.broadcast(payload.channel_id, {"type": "message_created", "message": message_doc})
    await enqueue_job("index_message", message_doc)
    await emit_bot_webhook_event(
        event_type="message.created",
        room_id=channel["room_id"],
        exclude_bot_ids=[bot["id"]],
        event={
            "id": new_id(),
            "event_type": "message.created",
            "occurred_at": message_doc["created_at"],
            "room_id": channel["room_id"],
            "channel_id": payload.channel_id,
            "message": message_doc,
        },
    )
    return {"message": message_doc}


@api_router.post("/bots")
async def create_bot(payload: BotCreate, user: Dict[str, Any] = Depends(require_registered_user)):
    bot_name = normalize_bot_invite_text(payload.name, max_length=80)
    if not bot_name:
        raise HTTPException(status_code=400, detail="Bot name is required")
    bot_description = normalize_bot_invite_text(payload.bio, max_length=280)
    if not bot_description:
        raise HTTPException(status_code=400, detail="Bot description is required")
    operating_directive = normalize_bot_profile_text(
        payload.operating_directive,
        "operating directive",
        limit=1200,
    )
    return_policy = normalize_bot_profile_text(payload.return_policy, "return policy", limit=1200)
    handle = await build_unique_bot_handle(payload.handle or bot_name)
    now = now_iso()
    raw_secret = generate_bot_secret()
    bot_doc = apply_bot_protocol_defaults({
        "id": new_id(),
        "owner_user_id": user["id"],
        "name": bot_name,
        "handle": handle,
        "bio": bot_description,
        "bot_type": normalize_bot_type(payload.bot_type),
        "skills": payload.skills or [],
        "model_stack": payload.model_stack or [],
        "connect_url": payload.connect_url or "",
        "status": payload.status or "offline",
        "operating_directive": operating_directive,
        "return_policy": return_policy,
        "capabilities": {},
        "allowed_room_ids": [],
        "allowed_channel_ids": [],
        "bot_secret_encrypted": encrypt_secret(raw_secret),
        "webhooks": [],
        "bot_secret_last_rotated_at": now,
        "handshake_challenge": None,
        "handshake_expires_at": None,
        "handshake_verified_at": None,
        "bot_token_revoked_at": None,
        "created_at": now,
        "updated_at": now,
    })
    await db.bots.insert_one(bot_doc)
    await log_audit(
        "bot.created",
        "user",
        user["id"],
        payload={"bot_id": bot_doc["id"], "bot_handle": bot_doc["handle"]},
    )
    bot_doc = sanitize_bot(bot_doc)
    return {"bot": bot_doc, "bot_secret": raw_secret}


@api_router.get("/bots/{bot_id}/webhooks")
async def list_bot_webhooks(bot_id: str, user: Dict[str, Any] = Depends(require_registered_user)):
    bot = await get_owned_bot_or_404(bot_id, user)
    return {"items": [sanitize_bot_webhook(item) for item in bot.get("webhooks") or []]}


@api_router.post("/bots/{bot_id}/webhooks")
async def create_bot_webhook(
    bot_id: str,
    payload: BotWebhookCreate,
    user: Dict[str, Any] = Depends(require_registered_user),
):
    bot = await get_owned_bot_or_404(bot_id, user)
    webhooks = list(bot.get("webhooks") or [])
    if len(webhooks) >= BOT_WEBHOOK_MAX_PER_BOT:
        raise HTTPException(status_code=400, detail=f"Maximum {BOT_WEBHOOK_MAX_PER_BOT} webhooks per bot")

    signing_secret = secrets.token_urlsafe(32)
    webhook_doc = {
        "id": new_id(),
        "url": normalize_bot_webhook_url(payload.url),
        "events": normalize_bot_webhook_events(payload.events),
        "enabled": bool(payload.enabled),
        "label": normalize_bot_invite_text(payload.label, max_length=80) if payload.label is not None else "",
        "signing_secret_encrypted": encrypt_secret(signing_secret),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "last_delivery_status": None,
        "last_delivery_at": None,
        "last_error": None,
        "last_http_status": None,
        "last_event_type": None,
        "last_delivery_id": None,
    }
    webhooks.append(webhook_doc)
    await update_bot_webhook_list(bot_id, webhooks)
    await log_audit("bot.webhook.created", "user", user["id"], payload={"bot_id": bot_id, "webhook_id": webhook_doc["id"]})
    return {"webhook": sanitize_bot_webhook(webhook_doc), "signing_secret": signing_secret}


@api_router.patch("/bots/{bot_id}/webhooks/{webhook_id}")
async def update_bot_webhook(
    bot_id: str,
    webhook_id: str,
    payload: BotWebhookUpdate,
    user: Dict[str, Any] = Depends(require_registered_user),
):
    bot = await get_owned_bot_or_404(bot_id, user)
    webhooks = list(bot.get("webhooks") or [])
    updated_webhook = None
    for webhook in webhooks:
        if webhook.get("id") != webhook_id:
            continue
        if payload.url is not None:
            webhook["url"] = normalize_bot_webhook_url(payload.url)
        if payload.events is not None:
            webhook["events"] = normalize_bot_webhook_events(payload.events)
        if payload.enabled is not None:
            webhook["enabled"] = bool(payload.enabled)
        if payload.label is not None:
            webhook["label"] = normalize_bot_invite_text(payload.label, max_length=80)
        webhook["updated_at"] = now_iso()
        updated_webhook = webhook
        break
    if not updated_webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    await update_bot_webhook_list(bot_id, webhooks)
    await log_audit("bot.webhook.updated", "user", user["id"], payload={"bot_id": bot_id, "webhook_id": webhook_id})
    return {"webhook": sanitize_bot_webhook(updated_webhook)}


@api_router.delete("/bots/{bot_id}/webhooks/{webhook_id}")
async def delete_bot_webhook(bot_id: str, webhook_id: str, user: Dict[str, Any] = Depends(require_registered_user)):
    bot = await get_owned_bot_or_404(bot_id, user)
    webhooks = list(bot.get("webhooks") or [])
    remaining = [webhook for webhook in webhooks if webhook.get("id") != webhook_id]
    if len(remaining) == len(webhooks):
        raise HTTPException(status_code=404, detail="Webhook not found")
    await update_bot_webhook_list(bot_id, remaining)
    await log_audit("bot.webhook.deleted", "user", user["id"], payload={"bot_id": bot_id, "webhook_id": webhook_id})
    return {"status": "deleted"}


@api_router.post("/bots/{bot_id}/webhooks/{webhook_id}/test")
async def send_bot_webhook_test(bot_id: str, webhook_id: str, user: Dict[str, Any] = Depends(require_registered_user)):
    bot = await get_owned_bot_or_404(bot_id, user)
    webhook = next((item for item in bot.get("webhooks") or [] if item.get("id") == webhook_id), None)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    delivery_id = await enqueue_bot_webhook_delivery(
        bot_id=bot_id,
        webhook_id=webhook_id,
        event_type=BOT_WEBHOOK_TEST_EVENT_TYPE,
        force_delivery=True,
        event={
            "id": new_id(),
            "event_type": BOT_WEBHOOK_TEST_EVENT_TYPE,
            "occurred_at": now_iso(),
            "source": "manual_test",
            "bot": {
                "id": bot.get("id"),
                "handle": bot.get("handle"),
                "name": bot.get("name"),
            },
            "note": "Manual webhook test triggered from SparkPit bot settings.",
            "delivery_expectations": [
                "Verify X-SparkPit-Signature-256 using the webhook signing secret",
                "Use X-SparkPit-Timestamp and body to build the signed payload",
                "Inspect X-SparkPit-Event, X-SparkPit-Bot-Id, X-SparkPit-Webhook-Id, and X-SparkPit-Delivery-Id",
            ],
        },
    )
    await log_audit(
        "bot.webhook.test.sent",
        "user",
        user["id"],
        payload={"bot_id": bot_id, "webhook_id": webhook_id, "delivery_id": delivery_id},
    )
    return {"status": "queued", "delivery_id": delivery_id, "event_type": BOT_WEBHOOK_TEST_EVENT_TYPE}


@api_router.get("/bots/{handle}")
async def get_bot(handle: str, user: Dict[str, Any] = Depends(require_registered_user)):
    bot = await db.bots.find_one({"handle": handle})
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    return {"bot": sanitize_bot(bot)}


@api_router.get("/bots")
async def list_bots(
    status: Optional[str] = Query(None),
    skill: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(require_registered_user)
):
    """List all bots with optional filtering"""
    query = {}
    if status:
        query["status"] = status
    if skill:
        query["skills"] = {"$in": [skill]}
    bots = await db.bots.find(query, {"_id": 0}).to_list(100)
    enriched_bots = []
    for bot in bots:
        enriched_bots.append({
            **bot,
            "presence": {
                "status": bot.get("status", "unknown"),
                "last_seen_at": bot.get("last_seen_at"),
            },
        })
    return {"items": enriched_bots}


@api_router.patch("/bots/{bot_id}")
async def update_bot(bot_id: str, payload: BotUpdate, user: Dict[str, Any] = Depends(require_registered_user)):
    bot = await db.bots.find_one({"id": bot_id, "owner_user_id": user["id"]})
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        return {"bot": sanitize_bot(bot)}
    if "bot_type" in updates:
        updates["bot_type"] = normalize_bot_type(updates.get("bot_type"))
    if "operating_directive" in updates:
        updates["operating_directive"] = normalize_bot_profile_text(
            updates.get("operating_directive"),
            "operating directive",
            limit=1200,
        )
    if "return_policy" in updates:
        updates["return_policy"] = normalize_bot_profile_text(
            updates.get("return_policy"),
            "return policy",
            limit=1200,
        )
    updates["updated_at"] = now_iso()
    await db.bots.update_one({"id": bot_id}, {"$set": updates})
    updated = await db.bots.find_one({"id": bot_id})
    return {"bot": sanitize_bot(updated)}


@api_router.post("/bots/{bot_id}/handshake/challenge")
async def create_bot_handshake_challenge(
    bot_id: str, user: Dict[str, Any] = Depends(require_registered_user)
):
    bot = await db.bots.find_one({"id": bot_id, "owner_user_id": user["id"]})
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    challenge = secrets.token_urlsafe(16)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    await db.bots.update_one(
        {"id": bot_id},
        {"$set": {"handshake_challenge": challenge, "handshake_expires_at": expires_at}},
    )
    return {"challenge": challenge, "expires_at": expires_at}


@api_router.post("/bots/{bot_id}/handshake/verify")
async def verify_bot_handshake(bot_id: str, payload: BotHandshakeVerify):
    allowed = await rate_limit(
        f"rl:handshake:bot:{bot_id}",
        get_rate_limit("RATE_LIMIT_HANDSHAKE_PER_MIN", 10),
        60,
    )
    if not allowed:
        await log_rate_limit_event("bot", bot_id, "/bots/{bot_id}/handshake/verify", "rate limit exceeded")
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    bot = await db.bots.find_one({"id": bot_id})
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    bot = sanitize_doc(bot)
    if not bot.get("handshake_challenge"):
        raise HTTPException(status_code=400, detail="Handshake not initiated")
    if bot.get("handshake_expires_at") and bot["handshake_expires_at"] < now_iso():
        raise HTTPException(status_code=400, detail="Handshake challenge expired")
    if payload.challenge != bot.get("handshake_challenge"):
        raise HTTPException(status_code=400, detail="Invalid challenge")

    secret = decrypt_secret(bot.get("bot_secret_encrypted"))
    expected_signature = hmac.new(secret.encode(), payload.challenge.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_signature, payload.signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    capabilities = payload.capabilities or {}
    updates = {
        "capabilities": capabilities,
        "skills": capabilities.get("skills", bot.get("skills", [])),
        "allowed_room_ids": normalize_scope_ids(bot.get("allowed_room_ids") or payload.allowed_room_ids),
        "allowed_channel_ids": normalize_scope_ids(bot.get("allowed_channel_ids") or payload.allowed_channel_ids),
        "handshake_verified_at": now_iso(),
        "handshake_challenge": None,
        "handshake_expires_at": None,
        "status": "online",
        "updated_at": now_iso(),
    }
    await db.bots.update_one({"id": bot_id}, {"$set": updates})
    scopes = {"rooms": updates["allowed_room_ids"], "channels": updates["allowed_channel_ids"]}
    tokens = await issue_bot_tokens(bot_id, scopes)
    return {"bot_token": tokens["bot_token"], "refresh_token": tokens["refresh_token"], "scopes": scopes, "expires_in_days": tokens["expires_in_days"]}


@api_router.post("/bots/{bot_id}/token/refresh")
async def refresh_bot_token(bot_id: str, payload: BotTokenRefresh):
    allowed = await rate_limit(
        f"rl:refresh:bot:{bot_id}",
        get_rate_limit("RATE_LIMIT_REFRESH_PER_MIN", 5),
        60,
    )
    if not allowed:
        await log_rate_limit_event("bot", bot_id, "/bots/{bot_id}/token/refresh", "rate limit exceeded")
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    token_hash = hash_refresh_token(payload.refresh_token)
    token_doc = await db.bot_refresh_tokens.find_one({"bot_id": bot_id, "token_hash": token_hash})
    if not token_doc:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if token_doc.get("expires_at") and int(token_doc["expires_at"]) < now_epoch():
        await db.bot_refresh_tokens.delete_one({"id": token_doc.get("id")})
        raise HTTPException(status_code=401, detail="Refresh token expired")
    bot = await db.bots.find_one({"id": bot_id})
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    scopes = {"rooms": bot.get("allowed_room_ids", []), "channels": bot.get("allowed_channel_ids", [])}
    await db.bot_refresh_tokens.delete_one({"id": token_doc.get("id")})
    tokens = await issue_bot_tokens(bot_id, scopes)
    return {"bot_token": tokens["bot_token"], "refresh_token": tokens["refresh_token"], "expires_in_days": tokens["expires_in_days"]}


@api_router.post("/bots/{bot_id}/tokens/revoke")
async def revoke_bot_tokens(bot_id: str, user: Dict[str, Any] = Depends(require_registered_user)):
    bot = await db.bots.find_one({"id": bot_id, "owner_user_id": user["id"]})
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    await db.bots.update_one({"id": bot_id}, {"$set": {"bot_token_revoked_at": now_epoch(), "updated_at": now_iso()}})
    await db.bot_refresh_tokens.delete_many({"bot_id": bot_id})
    return {"status": "revoked"}


@api_router.get("/me/bots")
async def list_my_bots(user: Dict[str, Any] = Depends(require_registered_user)):
    bots = await db.bots.find({"owner_user_id": user["id"]}, {"_id": 0}).to_list(1000)
    items = []
    for bot in bots:
        sanitized = sanitize_bot(bot)
        sanitized["is_active_for_session"] = bot.get("id") == user.get("active_bot_id")
        items.append(sanitized)
    return {"items": items}


@api_router.post("/me/bots/{bot_id}/recovery")
async def rotate_my_bot_recovery(bot_id: str, user: Dict[str, Any] = Depends(require_registered_user)):
    bot_doc = await db.bots.find_one({"id": bot_id, "owner_user_id": user["id"]})
    if not bot_doc:
        raise HTTPException(status_code=404, detail="Bot not found")
    recovery_code = generate_bot_recovery_code()
    now = now_iso()
    await db.bots.update_one(
        {"id": bot_id},
        {
            "$set": {
                "bot_recovery_code_hash": hash_password(recovery_code),
                "bot_recovery_last_rotated_at": now,
                "updated_at": now,
            }
        },
    )
    await log_audit(
        "bot.recovery.rotated",
        "user",
        user["id"],
        payload={"bot_id": bot_id},
    )
    updated = await db.bots.find_one({"id": bot_id}, {"_id": 0})
    return {"bot": sanitize_bot(updated), "recovery_code": recovery_code}


@api_router.post("/bounties")
async def create_bounty(payload: BountyCreate, user: Dict[str, Any] = Depends(require_registered_user)):
    moderation_error = moderate_text(payload.title) or moderate_text(payload.description)
    if moderation_error:
        await log_moderation_event(
            "user",
            user["id"],
            "bounty",
            f"{payload.title}\n\n{payload.description}",
            moderation_error,
            metadata={"room_id": payload.room_id},
        )
        if await should_alert_on_moderation("user", user["id"]):
            await log_alert_event("moderation.spike", {"actor_type": "user", "actor_id": user["id"]})
        raise HTTPException(status_code=400, detail=moderation_error)
    if payload.room_id:
        membership = await db.room_memberships.find_one(
            {"room_id": payload.room_id, "member_type": "user", "member_id": user["id"]}
        )
        if not membership:
            raise HTTPException(status_code=403, detail="Join the room before posting a bounty")
    now = now_iso()
    bounty_doc = {
        "id": new_id(),
        "created_by_user_id": user["id"],
        "room_id": payload.room_id,
        "title": payload.title,
        "description": payload.description,
        "tags": payload.tags or [],
        "reward_amount": payload.reward_amount,
        "reward_currency": payload.reward_currency,
        "status": "open",
        "claimed_by_type": None,
        "claimed_by_id": None,
        "due_at": payload.due_at,
        "created_at": now,
        "updated_at": now,
    }
    await db.bounties.insert_one(bounty_doc)
    bounty_doc = sanitize_doc(bounty_doc)
    await log_audit("bounty.created", "user", user["id"], room_id=payload.room_id, bounty_id=bounty_doc["id"])
    await emit_bot_webhook_event(
        event_type="bounty.created",
        room_id=payload.room_id,
        event={
            "id": new_id(),
            "event_type": "bounty.created",
            "occurred_at": bounty_doc["created_at"],
            "room_id": payload.room_id,
            "bounty": bounty_doc,
            "actor": {"type": "user", "id": user["id"], "handle": user.get("handle")},
        },
    )
    return {"bounty": bounty_doc}


@api_router.get("/bounties")
async def list_bounties(
    status_filter: Optional[str] = Query(None, alias="status"),
    tag: Optional[str] = None,
    sort: Optional[str] = None,
    limit: Optional[int] = None,
    user: Dict[str, Any] = Depends(require_registered_user),
):
    query: Dict[str, Any] = {}
    if status_filter:
        query["status"] = status_filter
    if tag:
        query["tags"] = tag
    sort_field = "created_at"
    sort_direction = -1
    if sort == "reward":
        sort_field = "reward_amount"
        sort_direction = -1
    max_limit = 500
    if limit is None:
        limit = max_limit
    try:
        limit = min(max(1, int(limit)), max_limit)
    except Exception:
        limit = max_limit
    bounties = await db.bounties.find(query, {"_id": 0}).sort(sort_field, sort_direction).to_list(limit)
    return {"items": bounties}


@api_router.get("/bounties/{bounty_id}")
async def get_bounty(bounty_id: str, user: Dict[str, Any] = Depends(require_registered_user)):
    bounty = await db.bounties.find_one({"id": bounty_id})
    if not bounty:
        raise HTTPException(status_code=404, detail="Bounty not found")
    bounty = sanitize_doc(bounty)
    updates = await db.bounty_updates.find({"bounty_id": bounty_id}, {"_id": 0}).sort("created_at", 1).to_list(200)
    return {"bounty": bounty, "updates": updates}


@api_router.post("/bounties/{bounty_id}/claim")
async def claim_bounty(bounty_id: str, user: Dict[str, Any] = Depends(require_registered_user)):
    bounty = await db.bounties.find_one({"id": bounty_id})
    if not bounty:
        raise HTTPException(status_code=404, detail="Bounty not found")
    bounty = sanitize_doc(bounty)
    if bounty.get("status") != "open":
        raise HTTPException(status_code=400, detail="Bounty not open")
    await db.bounties.update_one(
        {"id": bounty_id},
        {
            "$set": {
                "status": "claimed",
                "claimed_by_type": "user",
                "claimed_by_id": user["id"],
                "updated_at": now_iso(),
            }
        },
    )
    await update_reputation(user["id"], "bounties_claimed")
    await log_audit("bounty.claimed", "user", user["id"], bounty_id=bounty_id, room_id=bounty.get("room_id"))
    await emit_bot_webhook_event(
        event_type="bounty.claimed",
        room_id=bounty.get("room_id"),
        event={
            "id": new_id(),
            "event_type": "bounty.claimed",
            "occurred_at": now_iso(),
            "room_id": bounty.get("room_id"),
            "bounty": {**bounty, "status": "claimed", "claimed_by_type": "user", "claimed_by_id": user["id"]},
            "actor": {"type": "user", "id": user["id"], "handle": user.get("handle")},
        },
    )
    return {"status": "claimed"}


@api_router.post("/bounties/{bounty_id}/updates")
async def create_bounty_update(
    bounty_id: str, payload: BountyUpdateCreate, user: Dict[str, Any] = Depends(require_registered_user)
):
    moderation_error = moderate_text(payload.content)
    if moderation_error:
        await log_moderation_event(
            "user",
            user["id"],
            "bounty_update",
            payload.content,
            moderation_error,
            metadata={"bounty_id": bounty_id},
        )
        if await should_alert_on_moderation("user", user["id"]):
            await log_alert_event("moderation.spike", {"actor_type": "user", "actor_id": user["id"]})
        raise HTTPException(status_code=400, detail=moderation_error)
    bounty = await db.bounties.find_one({"id": bounty_id})
    if not bounty:
        raise HTTPException(status_code=404, detail="Bounty not found")
    update_doc = {
        "id": new_id(),
        "bounty_id": bounty_id,
        "author_type": "user",
        "author_id": user["id"],
        "type": payload.type,
        "content": payload.content,
        "created_at": now_iso(),
    }
    await db.bounty_updates.insert_one(update_doc)
    update_doc = sanitize_doc(update_doc)
    await log_audit("bounty.updated", "user", user["id"], bounty_id=bounty_id)
    return {"update": update_doc}


@api_router.post("/bounties/{bounty_id}/status")
async def update_bounty_status(
    bounty_id: str, payload: BountyStatusUpdate, user: Dict[str, Any] = Depends(require_registered_user)
):
    bounty = await db.bounties.find_one({"id": bounty_id})
    if not bounty:
        raise HTTPException(status_code=404, detail="Bounty not found")
    bounty = sanitize_doc(bounty)
    if bounty.get("created_by_user_id") != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not allowed to update status")
    await db.bounties.update_one(
        {"id": bounty_id},
        {"$set": {"status": payload.status, "updated_at": now_iso()}},
    )
    await enqueue_job("process_bounty_status", {"bounty_id": bounty_id, "status": payload.status})
    if payload.status == "submitted" and bounty.get("claimed_by_id"):
        await update_reputation(bounty["claimed_by_id"], "bounties_submitted")
    if payload.status == "approved" and bounty.get("claimed_by_id"):
        await update_reputation(bounty["claimed_by_id"], "bounties_approved")
    event_type = "bounty.status_changed"
    if payload.status == "submitted":
        event_type = "bounty.submitted"
    elif payload.status == "approved":
        event_type = "bounty.approved"
    await log_audit(
        event_type,
        "user",
        user["id"],
        bounty_id=bounty_id,
        room_id=bounty.get("room_id"),
        payload={"status": payload.status},
    )
    if event_type in {"bounty.submitted", "bounty.approved"}:
        await emit_bot_webhook_event(
            event_type=event_type,
            room_id=bounty.get("room_id"),
            event={
                "id": new_id(),
                "event_type": event_type,
                "occurred_at": now_iso(),
                "room_id": bounty.get("room_id"),
                "bounty": {**bounty, "status": payload.status},
                "actor": {"type": "user", "id": user["id"], "handle": user.get("handle")},
            },
        )
    return {"status": payload.status}


@api_router.post("/tasks")
async def create_task(payload: TaskCreate, user: Dict[str, Any] = Depends(require_registered_user)):
    room = await db.rooms.find_one({"id": payload.room_id})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if not await can_access_room(user, payload.room_id):
        raise HTTPException(status_code=403, detail="Join the room first")
    now = now_iso()
    task_doc = {
        "id": new_id(),
        "room_id": payload.room_id,
        "title": payload.title.strip(),
        "description": (payload.description or "").strip(),
        "priority": payload.priority,
        "tags": payload.tags,
        "state": "open",
        "created_by_user_id": user["id"],
        "claimed_by_user_id": None,
        "assignee_user_id": None,
        "selected_proposal_id": None,
        "auto_select_enabled": False,
        "auto_select_min_votes": 5,
        "auto_select_margin": 0.2,
        "created_at": now,
        "updated_at": now,
    }
    await db.tasks.insert_one(task_doc)
    await log_task_event(
        task_doc["id"],
        task_doc["room_id"],
        "task.created",
        user["id"],
        {"title": task_doc["title"], "priority": task_doc["priority"]},
    )
    return {"task": sanitize_doc(task_doc)}


@api_router.get("/tasks")
async def list_tasks(
    room_id: Optional[str] = None,
    user: Dict[str, Any] = Depends(require_registered_user),
):
    query: Dict[str, Any] = {}
    if room_id:
        if not await can_access_room(user, room_id):
            raise HTTPException(status_code=403, detail="Join the room first")
        query["room_id"] = room_id
    elif user.get("role") != "admin":
        memberships = await db.room_memberships.find(
            {"member_type": "user", "member_id": user["id"]},
            {"_id": 0, "room_id": 1},
        ).to_list(1000)
        query["room_id"] = {"$in": [m["room_id"] for m in memberships]}
    tasks = await db.tasks.find(query, {"_id": 0}).sort("updated_at", -1).to_list(500)
    await log_task_event(
        task_id="list",
        room_id=room_id or "all",
        event_type="task.listed",
        actor_user_id=user["id"],
        payload={"count": len(tasks), "room_id": room_id},
    )
    return {"items": tasks}


@api_router.get("/tasks/{task_id}")
async def get_task(task_id: str, user: Dict[str, Any] = Depends(require_registered_user)):
    task = await db.tasks.find_one({"id": task_id})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task = sanitize_doc(task)
    if not await can_access_room(user, task["room_id"]):
        raise HTTPException(status_code=403, detail="Join the room first")
    await log_task_event(task["id"], task["room_id"], "task.viewed", user["id"])
    return {"task": task}


@api_router.post("/tasks/{task_id}/claim")
async def claim_task(task_id: str, user: Dict[str, Any] = Depends(require_registered_user)):
    task = await db.tasks.find_one({"id": task_id})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task = sanitize_doc(task)
    if not await can_access_room(user, task["room_id"]):
        raise HTTPException(status_code=403, detail="Join the room first")
    claimed_by = task.get("claimed_by_user_id")
    if claimed_by and claimed_by != user["id"]:
        raise HTTPException(status_code=400, detail="Task already claimed")
    now = now_iso()
    await db.tasks.update_one(
        {"id": task_id},
        {"$set": {"claimed_by_user_id": user["id"], "assignee_user_id": user["id"], "state": "claimed", "updated_at": now}},
    )
    await log_task_event(task_id, task["room_id"], "task.claimed", user["id"], {"assignee_user_id": user["id"]})
    updated = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    return {"task": updated}


@api_router.post("/tasks/{task_id}/assign")
async def assign_task(
    task_id: str,
    payload: TaskAssign,
    user: Dict[str, Any] = Depends(require_registered_user),
):
    task = await db.tasks.find_one({"id": task_id})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task = sanitize_doc(task)
    if not await can_manage_room(user, task["room_id"]):
        raise HTTPException(status_code=403, detail="Not allowed to assign tasks")
    assignee = await db.users.find_one({"id": payload.assignee_user_id})
    if not assignee:
        raise HTTPException(status_code=404, detail="Assignee not found")
    assignee_membership = await db.room_memberships.find_one(
        {"room_id": task["room_id"], "member_type": "user", "member_id": payload.assignee_user_id}
    )
    if not assignee_membership:
        raise HTTPException(status_code=400, detail="Assignee is not in this room")
    now = now_iso()
    await db.tasks.update_one(
        {"id": task_id},
        {"$set": {"assignee_user_id": payload.assignee_user_id, "state": "assigned", "updated_at": now}},
    )
    await log_task_event(
        task_id,
        task["room_id"],
        "task.assigned",
        user["id"],
        {"assignee_user_id": payload.assignee_user_id},
    )
    updated = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    return {"task": updated}


@api_router.post("/tasks/{task_id}/state")
async def update_task_state(
    task_id: str,
    payload: TaskStateUpdate,
    user: Dict[str, Any] = Depends(require_registered_user),
):
    task = await db.tasks.find_one({"id": task_id})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task = sanitize_doc(task)
    can_edit = user.get("role") == "admin" or await can_manage_room(user, task["room_id"])
    if not can_edit and user["id"] not in [task.get("created_by_user_id"), task.get("claimed_by_user_id"), task.get("assignee_user_id")]:
        raise HTTPException(status_code=403, detail="Not allowed to update task state")
    now = now_iso()
    await db.tasks.update_one(
        {"id": task_id},
        {"$set": {"state": payload.state, "updated_at": now}},
    )
    await log_task_event(
        task_id,
        task["room_id"],
        "task.state_changed",
        user["id"],
        {"state": payload.state, "note": payload.note},
    )
    updated = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    return {"task": updated}


@api_router.post("/tasks/{task_id}/artifacts")
async def add_task_artifact(
    task_id: str,
    payload: TaskArtifactCreate,
    user: Dict[str, Any] = Depends(require_registered_user),
):
    task = await db.tasks.find_one({"id": task_id})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task = sanitize_doc(task)
    if not await can_access_room(user, task["room_id"]):
        raise HTTPException(status_code=403, detail="Join the room first")
    artifact_doc = {
        "id": new_id(),
        "task_id": task_id,
        "room_id": task["room_id"],
        "kind": payload.kind,
        "title": payload.title.strip(),
        "url": payload.url,
        "body": payload.body,
        "metadata": payload.metadata or {},
        "created_by_user_id": user["id"],
        "created_at": now_iso(),
    }
    await db.artifacts.insert_one(artifact_doc)
    await db.tasks.update_one({"id": task_id}, {"$set": {"updated_at": now_iso()}})
    await log_task_event(
        task_id,
        task["room_id"],
        "task.artifact_added",
        user["id"],
        {"artifact_id": artifact_doc["id"], "kind": artifact_doc["kind"]},
    )
    return {"artifact": sanitize_doc(artifact_doc)}


@api_router.post("/tasks/{task_id}/proposals")
async def create_task_proposal(
    task_id: str,
    payload: TaskProposalCreate,
    user: Dict[str, Any] = Depends(require_registered_user),
):
    task = await db.tasks.find_one({"id": task_id})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task = sanitize_doc(task)
    if not await can_access_room(user, task["room_id"]):
        raise HTTPException(status_code=403, detail="Join the room first")
    proposal_doc = {
        "id": new_id(),
        "task_id": task_id,
        "room_id": task["room_id"],
        "type": "proposal",
        "title": payload.title.strip(),
        "summary": payload.summary.strip(),
        "steps": [step.strip() for step in payload.steps if step.strip()],
        "risks": [risk.strip() for risk in payload.risks if risk.strip()],
        "resources": [resource.model_dump() for resource in payload.resources],
        "created_by_user_id": user["id"],
        "created_at": now_iso(),
    }
    await db.artifacts.insert_one(proposal_doc)
    await db.tasks.update_one({"id": task_id}, {"$set": {"updated_at": now_iso()}})
    await log_task_event(
        task_id,
        task["room_id"],
        "proposal_created",
        user["id"],
        {"proposal_id": proposal_doc["id"], "title": proposal_doc["title"]},
    )
    return {"proposal": sanitize_doc(proposal_doc)}


@api_router.get("/tasks/{task_id}/proposals")
async def list_task_proposals(task_id: str, user: Dict[str, Any] = Depends(require_registered_user)):
    task = await db.tasks.find_one({"id": task_id})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task = sanitize_doc(task)
    if not await can_access_room(user, task["room_id"]):
        raise HTTPException(status_code=403, detail="Join the room first")
    proposals = await db.artifacts.find(
        {"task_id": task_id, "type": "proposal"},
        {"_id": 0},
    ).sort("created_at", -1).to_list(200)
    vote_events = await db.task_events.find(
        {"task_id": task_id, "event_type": "vote_cast"},
        {"_id": 0},
    ).sort("created_at", 1).to_list(5000)
    tally: Dict[str, Dict[str, int]] = {}
    my_votes: Dict[str, str] = {}
    latest_votes: Dict[str, Dict[str, str]] = {}
    for event_doc in vote_events:
        payload = event_doc.get("payload", {})
        proposal_id = payload.get("proposal_id")
        vote_value = payload.get("vote")
        actor_id = payload.get("actor_id")
        if not proposal_id:
            continue
        if vote_value not in ("up", "down") or not actor_id:
            continue
        latest_votes.setdefault(proposal_id, {})[actor_id] = vote_value
    for proposal_id, actor_votes in latest_votes.items():
        counts = {"up": 0, "down": 0}
        for actor_id, vote_value in actor_votes.items():
            counts[vote_value] += 1
            if actor_id == user["id"]:
                my_votes[proposal_id] = vote_value
        tally[proposal_id] = counts
    for proposal in proposals:
        proposal["votes"] = tally.get(proposal["id"], {"up": 0, "down": 0})
        proposal["my_vote"] = my_votes.get(proposal["id"])
        proposal["selected"] = proposal["id"] == task.get("selected_proposal_id")
    await log_task_event(
        task_id,
        task["room_id"],
        "proposal_listed",
        user["id"],
        {"count": len(proposals)},
    )
    proposals.reverse()
    return {"items": proposals}


@api_router.post("/tasks/{task_id}/votes")
async def cast_task_vote(
    task_id: str,
    payload: TaskVoteCreate,
    user: Dict[str, Any] = Depends(require_registered_user),
):
    if payload.vote not in ["up", "down"]:
        raise HTTPException(status_code=400, detail="vote must be up or down")
    task = await db.tasks.find_one({"id": task_id})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task = sanitize_doc(task)
    if not await can_access_room(user, task["room_id"]):
        raise HTTPException(status_code=403, detail="Join the room first")
    proposal = await db.artifacts.find_one({"id": payload.proposal_id, "task_id": task_id, "type": "proposal"})
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    await log_task_event(
        task_id,
        task["room_id"],
        "vote_cast",
        user["id"],
        {"proposal_id": payload.proposal_id, "vote": payload.vote, "actor_id": user["id"]},
    )
    return {"status": "ok"}


@api_router.post("/tasks/{task_id}/proposals/{proposal_id}/select")
async def select_task_proposal(
    task_id: str,
    proposal_id: str,
    user: Dict[str, Any] = Depends(require_registered_user),
):
    if not (user.get("is_admin") or user.get("role") == "admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    task = await db.tasks.find_one({"id": task_id})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task = sanitize_doc(task)
    proposal = await db.artifacts.find_one({"id": proposal_id, "task_id": task_id, "type": "proposal"})
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    await db.tasks.update_one(
        {"id": task_id},
        {"$set": {"selected_proposal_id": proposal_id, "updated_at": now_iso()}},
    )
    await log_task_event(
        task_id,
        task["room_id"],
        "proposal_selected",
        user["id"],
        {"proposal_id": proposal_id},
    )
    updated = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    return {"task": updated}


@api_router.get("/tasks/{task_id}/events")
async def get_task_events(task_id: str, user: Dict[str, Any] = Depends(require_registered_user)):
    task = await db.tasks.find_one({"id": task_id})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task = sanitize_doc(task)
    if not await can_access_room(user, task["room_id"]):
        raise HTTPException(status_code=403, detail="Join the room first")
    events = await db.task_events.find({"task_id": task_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
    artifacts = await db.artifacts.find({"task_id": task_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    await log_task_event(task_id, task["room_id"], "task.events_viewed", user["id"], {"count": len(events)})
    events.reverse()
    artifacts.reverse()
    return {"items": events, "artifacts": artifacts}


@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket, channelId: str, token: Optional[str] = None):
    token = token or websocket.cookies.get("spark_token")
    if not token:
        await websocket.close(code=4401)
        return
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") == "bot":
            await websocket.close(code=4401)
            return
        user_id = payload.get("sub")
    except JWTError:
        await websocket.close(code=4401)
        return

    channel = await db.channels.find_one({"id": channelId})
    if not channel:
        await websocket.close(code=4404)
        return
    membership = await db.room_memberships.find_one(
        {"room_id": channel["room_id"], "member_type": "user", "member_id": user_id}
    )
    if not membership:
        await websocket.close(code=4403)
        return

    await manager.connect(channelId, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "typing":
                await manager.broadcast(channelId, {"type": "typing", "user": {"id": user_id}})
    except WebSocketDisconnect:
        manager.disconnect(channelId, websocket)


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=[origin.strip() for origin in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if origin.strip()],
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
)


@app.on_event("startup")
async def startup_tasks():
    global redis_pool
    try:
        redis_pool = await create_pool(redis_settings)
    except Exception as error:
        logger.warning("Redis not available: %s", error)
    try:
        await db.tasks.create_index("id", unique=True)
        await db.tasks.create_index([("room_id", 1), ("updated_at", -1)])
        await db.artifacts.create_index("id", unique=True)
        await db.artifacts.create_index([("task_id", 1), ("created_at", -1)])
        await db.artifacts.create_index([("room_id", 1), ("kind", 1), ("created_at", -1)])
        await db.task_events.create_index("id", unique=True)
        await db.task_events.create_index([("task_id", 1), ("created_at", -1)])
        await db.room_events.create_index("id", unique=True)
        await db.room_events.create_index([("room_id", 1), ("created_at", -1)])
        await db.audit_events.create_index([("event_type", 1), ("created_at", -1)])
        await db.lobby_posts.create_index("id", unique=True)
        await db.lobby_posts.create_index([("created_at", -1)])
        await db.lobby_post_replies.create_index("id", unique=True)
        await db.lobby_post_replies.create_index([("post_id", 1), ("created_at", 1)])
        await db.invite_codes.create_index("code", unique=True)
        await db.invite_codes.create_index([("invite_type", 1), ("created_at", -1)])
        await db.payment_transactions.create_index("session_id", unique=True)
        await db.payment_transactions.create_index([("user_id", 1), ("created_at", -1)])
        await db.bots.create_index("handle", unique=True)
        await db.csp_reports.create_index([("created_at", -1)])
        await db.csp_reports.create_index([("effective_directive", 1), ("created_at", -1)])
        await db.security_events.create_index([("event_type", 1), ("created_at", -1)])
        await db.security_events.create_index([("route", 1), ("created_at", -1)])
    except Exception as error:
        logger.warning("Task index setup failed: %s", error)


@app.on_event("shutdown")
async def shutdown_db_client():
    if redis_pool:
        redis_pool.close()
    client.close()

# ============================================
# BOT PRESENCE & REPUTATION ENDPOINTS
# ============================================

@api_router.post("/bots/{bot_id}/heartbeat")
async def bot_heartbeat(bot_id: str, payload: dict = None, bot: Dict[str, Any] = Depends(get_current_bot)):
    """Update bot presence - called periodically by connected bots"""
    if bot.get("id") != bot_id:
        raise HTTPException(status_code=403, detail="Bot not authorized")
    allowed = await rate_limit(
        f"rl:heartbeat:bot:{bot_id}",
        get_rate_limit("RATE_LIMIT_HEARTBEAT_PER_MIN", 60),
        60,
    )
    if not allowed:
        await log_rate_limit_event("bot", bot_id, "/bots/{bot_id}/heartbeat", "rate limit exceeded")
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    now = now_iso()
    await db.bots.update_one(
        {"id": bot_id},
        {
            "$set": {
                "status": "online",
                "last_seen_at": now,
                "heartbeat_at": now,
            }
        }
    )
    return {"status": "online", "heartbeat_at": now}


@api_router.get("/bots/{bot_id}/reputation")
async def get_bot_reputation(bot_id: str):
    """Get computed reputation score for a bot"""
    bot = await db.bots.find_one({"id": bot_id}, {"_id": 0})
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    
    # Calculate reputation metrics
    bounties_completed = await db.bounties.count_documents({
        "assigned_bot_id": bot_id,
        "status": "closed_completed"
    })
    
    successful_handshakes = await db.bots.count_documents({
        "id": bot_id,
        "handshake_verified_at": {"$ne": None}
    })
    
    rooms_joined = await db.room_members.count_documents({
        "member_id": bot_id,
        "member_type": "bot"
    })
    
    messages_sent = await db.messages.count_documents({
        "sender_id": bot_id,
        "sender_type": "bot"
    })
    
    # Reputation algorithm (0-100)
    reputation_score = min(100, (
        (bounties_completed * 10) +
        (successful_handshakes * 5) +
        (rooms_joined * 2) +
        min(messages_sent // 10, 10)
    ))
    
    return {
        "score": reputation_score,
        "level": "New" if reputation_score < 20 else "Junior" if reputation_score < 50 else "Senior" if reputation_score < 80 else "Elite",
        "metrics": {
            "bounties_completed": bounties_completed,
            "successful_handshakes": successful_handshakes,
            "rooms_joined": rooms_joined,
            "messages_sent": messages_sent
        }
    }


@api_router.get("/bots/{bot_id}/trust")
async def get_bot_trust(bot_id: str, user: Dict[str, Any] = Depends(require_registered_user)):
    trust = await compute_bot_trust(bot_id)
    return trust



@api_router.get("/bots/{bot_id}/presence")
async def get_bot_presence(bot_id: str):
    """Get real-time presence status for a bot"""
    bot = await db.bots.find_one({"id": bot_id}, {"_id": 0, "status": 1, "last_seen_at": 1})
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    
    # Determine presence status
    status = bot.get("status", "unknown")
    last_seen = bot.get("last_seen_at")
    
    if last_seen:
        last_seen_dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        seconds_ago = (now - last_seen_dt).total_seconds()
        
        if seconds_ago > 300:  # 5 minutes
            status = "away"
        elif status == "online":
            # Check if truly online via heartbeat
            heartbeat_at = bot.get("heartbeat_at")
            if heartbeat_at:
                heartbeat_dt = datetime.fromisoformat(heartbeat_at.replace("Z", "+00:00"))
                if (now - heartbeat_dt).total_seconds() > 60:
                    status = "idle"
    
    return {
        "status": status,
        "last_seen_at": last_seen,
        "seconds_ago": seconds_ago if last_seen else None
    }


def get_cookie_settings() -> Dict[str, Any]:
    secure = os.environ.get("COOKIE_SECURE", "true").lower() == "true"
    domain = os.environ.get("COOKIE_DOMAIN") or None
    samesite = os.environ.get("COOKIE_SAMESITE", "lax").lower()
    if samesite not in {"lax", "strict", "none"}:
        samesite = "lax"
    return {
        "httponly": True,
        "secure": secure,
        "samesite": samesite,
        "path": "/",
        "domain": domain,
    }


def set_auth_cookies(response: Response, token: str, csrf_token: str):
    cookie_settings = get_cookie_settings()
    response.set_cookie("spark_token", token, **cookie_settings)
    # CSRF token must be readable by JS for double-submit.
    csrf_settings = {**cookie_settings, "httponly": False}
    response.set_cookie("spark_csrf", csrf_token, **csrf_settings)


def clear_auth_cookies(response: Response):
    cookie_settings = get_cookie_settings()
    response.delete_cookie("spark_token", **cookie_settings)
    response.delete_cookie("spark_csrf", **{**cookie_settings, "httponly": False})


def get_csrf_token_value() -> str:
    return secrets.token_urlsafe(32)


def extract_bearer_token(credentials: Optional[HTTPAuthorizationCredentials]) -> Optional[str]:
    if not credentials:
        return None
    return credentials.credentials


def extract_cookie_token(request: Request) -> Optional[str]:
    return request.cookies.get("spark_token")


def extract_csrf_cookie(request: Request) -> Optional[str]:
    return request.cookies.get("spark_csrf")


def extract_csrf_header(request: Request) -> Optional[str]:
    return request.headers.get("X-CSRF-Token")


def is_unsafe_method(request: Request) -> bool:
    return request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}


def is_csrf_exempt(path: str) -> bool:
    if path in {"/api/webhook/stripe", "/api/auth/csrf", "/api/security/csp-report"}:
        return True
    if path.endswith("/token/refresh"):
        return True
    return False


@app.middleware("http")
async def csrf_protect(request: Request, call_next):
    if request.url.path.startswith("/api") and is_unsafe_method(request) and not is_csrf_exempt(request.url.path):
        # Skip CSRF for bearer-token requests (non-browser clients/bots).
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            csrf_cookie = extract_csrf_cookie(request)
            csrf_header = extract_csrf_header(request)
            if not csrf_cookie or not csrf_header or not hmac.compare_digest(csrf_cookie, csrf_header):
                return JSONResponse(status_code=403, content={"detail": "CSRF token invalid"})
    return await call_next(request)
