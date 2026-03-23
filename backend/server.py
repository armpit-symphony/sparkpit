from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Query, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from pathlib import Path
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timezone, timedelta
from emergentintegrations.payments.stripe.checkout import StripeCheckout, CheckoutSessionRequest
from arq import create_pool
from arq.connections import RedisSettings
from cryptography.fernet import Fernet
import os
import uuid
import logging
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

JWT_SECRET = os.environ.get("JWT_SECRET", "sparkpit_dev_secret")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 7
BOT_TOKEN_EXPIRE_DAYS = 30
BOT_SECRET_KEY = os.environ.get("BOT_SECRET_KEY", JWT_SECRET)

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
security = HTTPBearer()

app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def create_token(user: Dict[str, Any]) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRE_DAYS)
    payload = {"sub": user["id"], "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_bot_token(bot_id: str, scopes: Dict[str, List[str]]) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=BOT_TOKEN_EXPIRE_DAYS)
    payload = {"sub": bot_id, "type": "bot", "scopes": scopes, "exp": expire}
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
    token: str
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


class BotMessageCreate(BaseModel):
    channel_id: str
    content: str


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    token = credentials.credentials
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


async def get_current_bot(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    token = credentials.credentials
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


@api_router.post("/auth/register", response_model=AuthResponse)
async def register(user: UserCreate):
    existing = await db.users.find_one({"$or": [{"email": user.email}, {"handle": user.handle}]})
    if existing:
        raise HTTPException(status_code=400, detail="Email or handle already exists")

    admin_count = await db.users.count_documents({"role": "admin"})
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
    return {"token": token, "user": user_doc}


@api_router.post("/auth/login", response_model=AuthResponse)
async def login(user: UserLogin):
    existing = await db.users.find_one({"email": user.email})
    if not existing or not verify_password(user.password, existing.get("password_hash", "")):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    existing = sanitize_doc(existing)
    token = create_token(existing)
    existing.pop("password_hash", None)
    return {"token": token, "user": existing}


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

    host_url = str(request.base_url).rstrip("/")
    webhook_url = f"{host_url}/api/webhook/stripe"
    stripe_checkout = StripeCheckout(
        api_key=STRIPE_SECRET_KEY,
        webhook_secret=STRIPE_WEBHOOK_SECRET,
        webhook_url=webhook_url,
    )
    success_url = f"{payload.origin_url}/join?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{payload.origin_url}/join?canceled=true"
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
    channel = await db.channels.find_one({"id": channel_id})
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    channel = sanitize_doc(channel)
    membership = await db.room_memberships.find_one(
        {"room_id": channel["room_id"], "member_type": "user", "member_id": user["id"]}
    )
    if not membership:
        raise HTTPException(status_code=403, detail="Join the room first")
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
        "bot_secret_encrypted": encrypt_secret(raw_secret),
        "bot_secret_last_rotated_at": now,
        "handshake_challenge": None,
        "handshake_expires_at": None,
        "handshake_verified_at": None,
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
        "handshake_verified_at": now_iso(),
        "handshake_challenge": None,
        "handshake_expires_at": None,
        "status": "online",
        "updated_at": now_iso(),
    }
    await db.bots.update_one({"id": bot_id}, {"$set": updates})
    scopes = {"rooms": payload.allowed_room_ids, "channels": payload.allowed_channel_ids}
    bot_token = create_bot_token(bot_id, scopes)
    return {"bot_token": bot_token, "scopes": scopes, "expires_in_days": BOT_TOKEN_EXPIRE_DAYS}


@api_router.get("/me/bots")
async def list_my_bots(user: Dict[str, Any] = Depends(require_active_member)):
    bots = await db.bots.find({"owner_user_id": user["id"]}, {"_id": 0}).to_list(1000)
    return {"items": [sanitize_bot(bot) for bot in bots]}


@api_router.post("/bounties")
async def create_bounty(payload: BountyCreate, user: Dict[str, Any] = Depends(require_active_member)):
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
    bounties = await db.bounties.find(query, {"_id": 0}).sort(sort_field, sort_direction).to_list(500)
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
async def websocket_endpoint(websocket: WebSocket, channelId: str):
    await manager.connect(channelId, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "typing":
                await manager.broadcast(channelId, {"type": "typing", "user": data.get("user")})
    except WebSocketDisconnect:
        manager.disconnect(channelId, websocket)


# --- /v1/health endpoint (public, no auth required) ---
@app.get("/v1/health")
async def v1_health():
    """Public health check — used by nginx /v1/ proxy to verify service is up."""
    mongo_ok = False
    try:
        await client.admin.command("ping")
        mongo_ok = True
    except Exception:
        pass
    return {"status": "ok", "version": "1.0.0", "mongo": "ok" if mongo_ok else "degraded"}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
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