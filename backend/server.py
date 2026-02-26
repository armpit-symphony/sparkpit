from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from pathlib import Path
from urllib.parse import urlparse
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timezone, timedelta
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
import secrets
import asyncio
import requests
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

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY")
JOIN_FEE_AMOUNT = 49.00
JOIN_FEE_CURRENCY = "usd"

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
    bot = sanitize_doc(bot)
    if not bot:
        return bot
    bot.pop("bot_secret_encrypted", None)
    bot.pop("handshake_challenge", None)
    bot.pop("handshake_expires_at", None)
    return bot


async def enqueue_job(job_name: str, payload: Dict[str, Any]):
    if not redis_pool:
        return
    try:
        await redis_pool.enqueue_job(job_name, payload)
    except Exception as error:
        logger.warning("Queue enqueue failed: %s", error)


async def fetch_stripe_session(session_id: str) -> Dict[str, Any]:
    if not STRIPE_SECRET_KEY:
        return {}

    def _fetch():
        response = requests.get(
            f"https://api.stripe.com/v1/checkout/sessions/{session_id}",
            headers={"Authorization": f"Bearer {STRIPE_SECRET_KEY}"},
            timeout=10,
        )
        if response.status_code != 200:
            return {}
        return response.json()

    return await asyncio.to_thread(_fetch)


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


async def activate_membership(user_id: str, session_id: str, customer_id: Optional[str] = None):
    updates = {
        "membership_status": "active",
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


class UserUpdate(BaseModel):
    handle: Optional[str] = None


class InviteClaim(BaseModel):
    code: str


class InviteCodeCreate(BaseModel):
    code: Optional[str] = None
    max_uses: int = 1
    expires_at: Optional[str] = None


class RoomCreate(BaseModel):
    slug: str
    title: str
    is_public: bool = True


class ChannelCreate(BaseModel):
    slug: str
    title: str
    type: str = "chat"


class MessageCreate(BaseModel):
    content: str


class BotCreate(BaseModel):
    name: str
    handle: str
    bio: Optional[str] = ""
    skills: List[str] = []
    model_stack: Optional[List[str]] = []
    connect_url: Optional[str] = ""
    status: str = "offline"


class BotUpdate(BaseModel):
    name: Optional[str] = None
    bio: Optional[str] = None
    skills: Optional[List[str]] = None
    model_stack: Optional[List[str]] = None
    connect_url: Optional[str] = None
    status: Optional[str] = None


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


class CheckoutSessionCreate(BaseModel):
    origin_url: str


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
    user = sanitize_doc(user)
    user.pop("password_hash", None)
    return user


async def require_active_member(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if user.get("membership_status") != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Membership not active")
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
    existing = await db.users.find_one({"$or": [{"email": user.email}, {"handle": user.handle}]})
    if existing:
        raise HTTPException(status_code=400, detail="Email or handle already exists")

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
        "email": user.email,
        "handle": user.handle,
        "password_hash": hash_password(user.password),
        "role": role,
        "membership_status": membership_status,
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
    return {"token": None, "user": user_doc}


@api_router.post("/auth/login", response_model=AuthResponse)
async def login(user: UserLogin, response: Response):
    existing = await db.users.find_one({"email": user.email})
    if not existing or not verify_password(user.password, existing.get("password_hash", "")):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    existing = sanitize_doc(existing)
    token = create_token(existing)
    existing.pop("password_hash", None)
    csrf_token = get_csrf_token_value()
    set_auth_cookies(response, token, csrf_token)
    return {"token": None, "user": existing}


@api_router.post("/auth/logout")
async def logout(response: Response):
    clear_auth_cookies(response)
    return {"status": "ok"}


@api_router.post("/auth/invite/claim")
async def claim_invite(payload: InviteClaim, user: Dict[str, Any] = Depends(get_current_user)):
    code_doc = await db.invite_codes.find_one({"code": payload.code})
    if not code_doc:
        raise HTTPException(status_code=404, detail="Invite code not found")
    code_doc = sanitize_doc(code_doc)
    if code_doc.get("expires_at") and code_doc["expires_at"] < now_iso():
        raise HTTPException(status_code=400, detail="Invite code expired")
    if code_doc.get("uses", 0) >= code_doc.get("max_uses", 1):
        raise HTTPException(status_code=400, detail="Invite code exhausted")

    await db.invite_codes.update_one(
        {"id": code_doc["id"]},
        {"$inc": {"uses": 1}},
    )
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"membership_status": "active", "joined_at": now_iso(), "updated_at": now_iso()}},
    )
    await log_audit("invite.claimed", "user", user["id"], payload={"code": payload.code})
    return {"status": "active"}


@api_router.get("/me")
async def get_me(user: Dict[str, Any] = Depends(get_current_user)):
    return {"user": user}


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
async def create_invite_code(payload: InviteCodeCreate, admin: Dict[str, Any] = Depends(require_admin)):
    code_value = payload.code or f"SPARK-{uuid.uuid4().hex[:8].upper()}"
    now = now_iso()
    code_doc = {
        "id": new_id(),
        "code": code_value,
        "max_uses": payload.max_uses,
        "uses": 0,
        "created_by_user_id": admin["id"],
        "expires_at": payload.expires_at,
        "created_at": now,
    }
    await db.invite_codes.insert_one(code_doc)
    code_doc = sanitize_doc(code_doc)
    await log_audit("invite.created", "user", admin["id"], payload={"code": code_value})
    return {"invite_code": code_doc}


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
    admin: Dict[str, Any] = Depends(require_admin),
):
    updates = {
        "status": payload.status,
        "updated_at": now_iso(),
        "resolved_by": admin["id"],
    }
    if payload.notes:
        updates["notes"] = payload.notes
    await db.moderation_queue.update_one({"id": item_id}, {"$set": updates})
    return {"status": payload.status}


@api_router.post("/admin/moderation/{item_id}/ban")
async def ban_actor_from_moderation(item_id: str, admin: Dict[str, Any] = Depends(require_admin)):
    item = await db.moderation_queue.find_one({"id": item_id})
    if not item:
        raise HTTPException(status_code=404, detail="Moderation item not found")
    actor_type = item.get("actor_type")
    actor_id = item.get("actor_id")
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
    await log_alert_event("actor.banned", {"actor_type": actor_type, "actor_id": actor_id, "item_id": item_id})
    return {"status": "banned"}


@api_router.post("/admin/moderation/{item_id}/shadow-ban")
async def shadow_ban_actor_from_moderation(item_id: str, admin: Dict[str, Any] = Depends(require_admin)):
    item = await db.moderation_queue.find_one({"id": item_id})
    if not item:
        raise HTTPException(status_code=404, detail="Moderation item not found")
    actor_type = item.get("actor_type")
    actor_id = item.get("actor_id")
    updates = {"is_shadow_banned": True, "shadow_ban_reason": get_shadow_ban_reason(), "shadow_banned_at": now_iso()}
    if actor_type == "user":
        await db.users.update_one({"id": actor_id}, {"$set": updates})
    elif actor_type == "bot":
        await db.bots.update_one({"id": actor_id}, {"$set": updates})
    else:
        raise HTTPException(status_code=400, detail="Unknown actor type")
    await db.moderation_queue.update_one({"id": item_id}, {"$set": {"status": "resolved", "resolved_by": admin["id"]}})
    await log_alert_event("actor.shadow_banned", {"actor_type": actor_type, "actor_id": actor_id, "item_id": item_id})
    return {"status": "shadow_banned"}

@api_router.get("/admin/ops")
async def ops_checklist(admin: Dict[str, Any] = Depends(require_admin)):
    stripe_configured = bool(STRIPE_SECRET_KEY and STRIPE_PUBLISHABLE_KEY and STRIPE_WEBHOOK_SECRET)
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
        "redis_connected": bool(redis_connected),
        "worker_heartbeat": worker_heartbeat,
        "worker_healthy": worker_healthy,
    }


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


@api_router.get("/activity")
async def activity_feed(
    room_id: Optional[str] = None,
    since: Optional[str] = None,
    user: Dict[str, Any] = Depends(require_active_member),
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


@api_router.post("/payments/stripe/checkout")
async def create_checkout_session(
    payload: CheckoutSessionCreate,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
):
    if not STRIPE_SECRET_KEY:
        return JSONResponse(status_code=400, content={"detail": "Stripe not configured"})
    if user.get("membership_status") == "active":
        raise HTTPException(status_code=400, detail="Membership already active")
    if not payload.origin_url:
        raise HTTPException(status_code=400, detail="Origin URL required")
    allowed_origins = os.environ.get("ALLOWED_ORIGINS", "").split(",")
    allowed_origins = [origin.strip().rstrip("/") for origin in allowed_origins if origin.strip()]
    parsed_origin = urlparse(payload.origin_url)
    if not parsed_origin.scheme or not parsed_origin.netloc:
        raise HTTPException(status_code=400, detail="Origin URL invalid")
    origin_root = f"{parsed_origin.scheme}://{parsed_origin.netloc}".rstrip("/")
    if allowed_origins and origin_root not in allowed_origins:
        raise HTTPException(status_code=400, detail="Origin URL not allowed")

    host_url = str(request.base_url).rstrip("/")
    webhook_url = f"{host_url}/api/webhook/stripe"
    stripe_checkout = StripeCheckout(
        api_key=STRIPE_SECRET_KEY,
        webhook_secret=STRIPE_WEBHOOK_SECRET,
        webhook_url=webhook_url,
    )
    success_url = f"{origin_root}/join?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin_root}/join?canceled=true"
    metadata = {"user_id": user["id"], "email": user["email"], "purpose": "join_fee"}

    checkout_request = CheckoutSessionRequest(
        amount=float(JOIN_FEE_AMOUNT),
        currency=JOIN_FEE_CURRENCY,
        success_url=success_url,
        cancel_url=cancel_url,
        metadata=metadata,
    )
    session = await stripe_checkout.create_checkout_session(checkout_request)

    payment_doc = {
        "id": new_id(),
        "user_id": user["id"],
        "session_id": session.session_id,
        "amount": JOIN_FEE_AMOUNT,
        "currency": JOIN_FEE_CURRENCY,
        "status": "initiated",
        "payment_status": "unpaid",
        "metadata": metadata,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.payment_transactions.insert_one(payment_doc)
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"stripe_session_id": session.session_id, "stripe_session_status": "initiated"}},
    )

    return {"url": session.url, "session_id": session.session_id}


@api_router.get("/payments/stripe/checkout/status/{session_id}")
async def checkout_status(session_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    if not STRIPE_SECRET_KEY:
        return JSONResponse(status_code=400, content={"detail": "Stripe not configured"})
    stripe_checkout = StripeCheckout(api_key=STRIPE_SECRET_KEY, webhook_secret=STRIPE_WEBHOOK_SECRET)
    status_response = await stripe_checkout.get_checkout_status(session_id)

    transaction = await db.payment_transactions.find_one({"session_id": session_id})
    transaction = sanitize_doc(transaction) if transaction else None
    if transaction and transaction.get("user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Session does not belong to user")
    new_status = status_response.status
    payment_status = status_response.payment_status
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
        await activate_membership(user["id"], session_id, customer_id)
    elif new_status in ["expired", "canceled"]:
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
    }


@api_router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    if not STRIPE_SECRET_KEY or not STRIPE_WEBHOOK_SECRET:
        return JSONResponse(status_code=400, content={"detail": "Stripe webhook not configured"})
    payload = await request.body()
    signature = request.headers.get("Stripe-Signature")
    stripe_checkout = StripeCheckout(api_key=STRIPE_SECRET_KEY, webhook_secret=STRIPE_WEBHOOK_SECRET)
    webhook_event = await stripe_checkout.handle_webhook(payload, signature)

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

    if webhook_event.event_type == "checkout.session.completed":
        if user_id:
            await activate_membership(user_id, session_id, customer_id)
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "status": "paid",
                    "payment_status": payment_status,
                    "updated_at": now_iso(),
                    "stripe_customer_id": customer_id,
                },
                "$setOnInsert": {
                    "id": new_id(),
                    "user_id": user_id,
                    "amount": JOIN_FEE_AMOUNT,
                    "currency": JOIN_FEE_CURRENCY,
                    "metadata": metadata,
                    "created_at": now_iso(),
                },
            },
            upsert=True,
        )
    elif webhook_event.event_type in ["checkout.session.expired", "charge.refunded"]:
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "status": "expired" if webhook_event.event_type == "checkout.session.expired" else "refunded",
                    "payment_status": payment_status,
                    "updated_at": now_iso(),
                    "stripe_customer_id": customer_id,
                },
                "$setOnInsert": {
                    "id": new_id(),
                    "user_id": user_id,
                    "amount": JOIN_FEE_AMOUNT,
                    "currency": JOIN_FEE_CURRENCY,
                    "metadata": metadata,
                    "created_at": now_iso(),
                },
            },
            upsert=True,
        )
        if user_id:
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
async def create_room(payload: RoomCreate, user: Dict[str, Any] = Depends(require_active_member)):
    existing = await db.rooms.find_one({"slug": payload.slug})
    if existing:
        raise HTTPException(status_code=400, detail="Room slug already exists")
    now = now_iso()
    room_doc = {
        "id": new_id(),
        "slug": payload.slug,
        "title": payload.title,
        "is_public": payload.is_public,
        "created_by_user_id": user["id"],
        "created_at": now,
        "updated_at": now,
    }
    await db.rooms.insert_one(room_doc)
    room_doc = sanitize_doc(room_doc)
    membership_doc = {
        "id": new_id(),
        "room_id": room_doc["id"],
        "member_type": "user",
        "member_id": user["id"],
        "role": "owner",
        "created_at": now,
    }
    await db.room_memberships.insert_one(membership_doc)
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
    await log_audit("room.created", "user", user["id"], room_id=room_doc["id"], payload={"slug": payload.slug})
    await log_audit("room.joined", "user", user["id"], room_id=room_doc["id"], payload={"role": "owner"})
    return {"room": room_doc, "default_channel": default_channel}


@api_router.get("/rooms")
async def list_rooms(user: Dict[str, Any] = Depends(require_active_member)):
    memberships = await db.room_memberships.find(
        {"member_type": "user", "member_id": user["id"]}, {"_id": 0}
    ).to_list(1000)
    joined_room_ids = {m["room_id"] for m in memberships}
    rooms = await db.rooms.find(
        {"$or": [{"is_public": True}, {"id": {"$in": list(joined_room_ids)}}]}, {"_id": 0}
    ).to_list(1000)
    for room in rooms:
        room["joined"] = room["id"] in joined_room_ids
    return {"items": rooms}


@api_router.get("/rooms/{slug}")
async def get_room(slug: str, user: Dict[str, Any] = Depends(require_active_member)):
    room = await db.rooms.find_one({"slug": slug})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    room = sanitize_doc(room)
    membership = await db.room_memberships.find_one(
        {"room_id": room["id"], "member_type": "user", "member_id": user["id"]}
    )
    membership = sanitize_doc(membership) if membership else None
    channels = await db.channels.find({"room_id": room["id"]}, {"_id": 0}).to_list(200)
    return {"room": room, "channels": channels, "membership": membership}


@api_router.post("/rooms/{slug}/join")
async def join_room(slug: str, user: Dict[str, Any] = Depends(require_active_member)):
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
    return {"joined": True}


@api_router.post("/rooms/{slug}/join-bot")
async def join_bot_room(slug: str, bot_id: str = Query(...), user: Dict[str, Any] = Depends(require_active_member)):
    room = await db.rooms.find_one({"slug": slug})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    room = sanitize_doc(room)
    bot = await db.bots.find_one({"id": bot_id, "owner_user_id": user["id"]})
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
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
    return {"joined": True}


@api_router.post("/rooms/{slug}/channels")
async def create_channel(slug: str, payload: ChannelCreate, user: Dict[str, Any] = Depends(require_active_member)):
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
    user: Dict[str, Any] = Depends(require_active_member),
):
    channel = await db.channels.find_one({"id": channel_id})
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    channel = sanitize_doc(channel)
    membership = await db.room_memberships.find_one(
        {"room_id": channel["room_id"], "member_type": "user", "member_id": user["id"]}
    )
    if not membership:
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
    user: Dict[str, Any] = Depends(require_active_member),
):
    allowed = await rate_limit(
        f"rl:msg:user:{user['id']}",
        get_rate_limit("RATE_LIMIT_MESSAGES_PER_MIN", 30),
        60,
    )
    if not allowed:
        await log_rate_limit_event("user", user["id"], "/channels/{channel_id}/messages", "rate limit exceeded")
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    if await detect_duplicate_content("user", user["id"], payload.content):
        await log_moderation_event(
            "user",
            user["id"],
            "message",
            payload.content,
            "duplicate content spam",
            metadata={"channel_id": channel_id},
        )
        if await should_alert_on_moderation("user", user["id"]):
            await log_alert_event("moderation.spike", {"actor_type": "user", "actor_id": user["id"]})
        raise HTTPException(status_code=429, detail="Duplicate content detected")
    moderation_error = moderate_text(payload.content)
    if moderation_error:
        await log_moderation_event(
            "user",
            user["id"],
            "message",
            payload.content,
            moderation_error,
            metadata={"channel_id": channel_id},
        )
        if await should_alert_on_moderation("user", user["id"]):
            await log_alert_event("moderation.spike", {"actor_type": "user", "actor_id": user["id"]})
        raise HTTPException(status_code=400, detail=moderation_error)
    channel = await db.channels.find_one({"id": channel_id})
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    channel = sanitize_doc(channel)
    membership = await db.room_memberships.find_one(
        {"room_id": channel["room_id"], "member_type": "user", "member_id": user["id"]}
    )
    if not membership:
        raise HTTPException(status_code=403, detail="Join the room first")
    if user.get("is_shadow_banned"):
        return {"message": {"id": new_id(), "channel_id": channel_id, "sender_type": "user", "sender_id": user["id"], "sender_handle": user.get("handle"), "content": payload.content, "metadata": {"shadow_banned": True}, "created_at": now_iso()}}
    message_doc = {
        "id": new_id(),
        "channel_id": channel_id,
        "sender_type": "user",
        "sender_id": user["id"],
        "sender_handle": user.get("handle"),
        "content": payload.content,
        "metadata": {},
        "created_at": now_iso(),
    }
    await db.messages.insert_one(message_doc)
    message_doc = sanitize_doc(message_doc)
    await log_audit("message.posted", "user", user["id"], room_id=channel["room_id"], channel_id=channel_id)
    await manager.broadcast(channel_id, {"type": "message_created", "message": message_doc})
    await enqueue_job("index_message", message_doc)
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
        return {"message": {"id": new_id(), "channel_id": payload.channel_id, "sender_type": "bot", "sender_id": bot["id"], "sender_handle": bot.get("handle"), "content": payload.content, "metadata": {"bot": True, "shadow_banned": True}, "created_at": now_iso()}}

    message_doc = {
        "id": new_id(),
        "channel_id": payload.channel_id,
        "sender_type": "bot",
        "sender_id": bot["id"],
        "sender_handle": bot.get("handle"),
        "content": payload.content,
        "metadata": {"bot": True},
        "created_at": now_iso(),
    }
    await db.messages.insert_one(message_doc)
    message_doc = sanitize_doc(message_doc)
    await log_audit("message.posted", "bot", bot["id"], room_id=channel["room_id"], channel_id=payload.channel_id)
    await manager.broadcast(payload.channel_id, {"type": "message_created", "message": message_doc})
    await enqueue_job("index_message", message_doc)
    return {"message": message_doc}


@api_router.post("/bots")
async def create_bot(payload: BotCreate, user: Dict[str, Any] = Depends(require_active_member)):
    existing = await db.bots.find_one({"handle": payload.handle})
    if existing:
        raise HTTPException(status_code=400, detail="Bot handle already exists")
    now = now_iso()
    raw_secret = generate_bot_secret()
    bot_doc = {
        "id": new_id(),
        "owner_user_id": user["id"],
        "name": payload.name,
        "handle": payload.handle,
        "bio": payload.bio or "",
        "skills": payload.skills or [],
        "model_stack": payload.model_stack or [],
        "connect_url": payload.connect_url or "",
        "status": payload.status or "offline",
        "capabilities": {},
        "allowed_room_ids": [],
        "allowed_channel_ids": [],
        "bot_secret_encrypted": encrypt_secret(raw_secret),
        "bot_secret_last_rotated_at": now,
        "handshake_challenge": None,
        "handshake_expires_at": None,
        "handshake_verified_at": None,
        "bot_token_revoked_at": None,
        "created_at": now,
        "updated_at": now,
    }
    await db.bots.insert_one(bot_doc)
    bot_doc = sanitize_bot(bot_doc)
    return {"bot": bot_doc, "bot_secret": raw_secret}


@api_router.get("/bots/{handle}")
async def get_bot(handle: str, user: Dict[str, Any] = Depends(require_active_member)):
    bot = await db.bots.find_one({"handle": handle})
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    return {"bot": sanitize_bot(bot)}


@api_router.patch("/bots/{bot_id}")
async def update_bot(bot_id: str, payload: BotUpdate, user: Dict[str, Any] = Depends(require_active_member)):
    bot = await db.bots.find_one({"id": bot_id, "owner_user_id": user["id"]})
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        return {"bot": sanitize_doc(bot)}
    updates["updated_at"] = now_iso()
    await db.bots.update_one({"id": bot_id}, {"$set": updates})
    updated = await db.bots.find_one({"id": bot_id})
    return {"bot": sanitize_bot(updated)}


@api_router.post("/bots/{bot_id}/handshake/challenge")
async def create_bot_handshake_challenge(
    bot_id: str, user: Dict[str, Any] = Depends(require_active_member)
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
        "allowed_room_ids": payload.allowed_room_ids,
        "allowed_channel_ids": payload.allowed_channel_ids,
        "handshake_verified_at": now_iso(),
        "handshake_challenge": None,
        "handshake_expires_at": None,
        "status": "online",
        "updated_at": now_iso(),
    }
    await db.bots.update_one({"id": bot_id}, {"$set": updates})
    scopes = {"rooms": payload.allowed_room_ids, "channels": payload.allowed_channel_ids}
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
async def revoke_bot_tokens(bot_id: str, user: Dict[str, Any] = Depends(require_active_member)):
    bot = await db.bots.find_one({"id": bot_id, "owner_user_id": user["id"]})
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    await db.bots.update_one({"id": bot_id}, {"$set": {"bot_token_revoked_at": now_epoch(), "updated_at": now_iso()}})
    await db.bot_refresh_tokens.delete_many({"bot_id": bot_id})
    return {"status": "revoked"}


@api_router.get("/me/bots")
async def list_my_bots(user: Dict[str, Any] = Depends(require_active_member)):
    bots = await db.bots.find({"owner_user_id": user["id"]}, {"_id": 0}).to_list(1000)
    return {"items": [sanitize_bot(bot) for bot in bots]}


@api_router.post("/bounties")
async def create_bounty(payload: BountyCreate, user: Dict[str, Any] = Depends(require_active_member)):
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
    return {"bounty": bounty_doc}


@api_router.get("/bounties")
async def list_bounties(
    status_filter: Optional[str] = Query(None, alias="status"),
    tag: Optional[str] = None,
    sort: Optional[str] = None,
    limit: Optional[int] = None,
    user: Dict[str, Any] = Depends(require_active_member),
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
async def get_bounty(bounty_id: str, user: Dict[str, Any] = Depends(require_active_member)):
    bounty = await db.bounties.find_one({"id": bounty_id})
    if not bounty:
        raise HTTPException(status_code=404, detail="Bounty not found")
    bounty = sanitize_doc(bounty)
    updates = await db.bounty_updates.find({"bounty_id": bounty_id}, {"_id": 0}).sort("created_at", 1).to_list(200)
    return {"bounty": bounty, "updates": updates}


@api_router.post("/bounties/{bounty_id}/claim")
async def claim_bounty(bounty_id: str, user: Dict[str, Any] = Depends(require_active_member)):
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
    return {"status": "claimed"}


@api_router.post("/bounties/{bounty_id}/updates")
async def create_bounty_update(
    bounty_id: str, payload: BountyUpdateCreate, user: Dict[str, Any] = Depends(require_active_member)
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
    bounty_id: str, payload: BountyStatusUpdate, user: Dict[str, Any] = Depends(require_active_member)
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
    return {"status": payload.status}


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
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_tasks():
    global redis_pool
    try:
        redis_pool = await create_pool(redis_settings)
    except Exception as error:
        logger.warning("Redis not available: %s", error)


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
async def get_bot_trust(bot_id: str, user: Dict[str, Any] = Depends(require_active_member)):
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


@api_router.get("/bots")
async def list_bots(
    status: Optional[str] = Query(None),
    skill: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(require_active_member)
):
    """List all bots with optional filtering"""
    query = {}
    if status:
        query["status"] = status
    if skill:
        query["skills"] = {"$in": [skill]}
    
    bots = await db.bots.find(query, {"_id": 0}).to_list(100)
    
    # Enrich with presence info
    enriched_bots = []
    for bot in bots:
        bot_presence = {
            "status": bot.get("status", "unknown"),
            "last_seen_at": bot.get("last_seen_at")
        }
        enriched_bots.append({
            **bot,
            "presence": bot_presence
        })
    
    return {"items": enriched_bots}
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
    if path in {"/api/webhook/stripe", "/api/auth/csrf"}:
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
