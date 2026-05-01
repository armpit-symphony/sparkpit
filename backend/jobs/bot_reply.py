import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.research_protocol import (
    apply_research_protocol_defaults,
    record_bot_research_activity,
)


def _trim_text(value: Optional[str], limit: int = 180) -> str:
    normalized = " ".join((value or "").strip().split())
    if not normalized:
        return ""
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3].rstrip()}..."


def _pick_research_role(research: Dict[str, Any]) -> str:
    if not research.get("key_sources"):
        return "scout"
    if not research.get("findings"):
        return "analyst"
    if not research.get("summary"):
        return "synthesizer"
    if research.get("open_questions"):
        return "critic"
    return "operator"


def _build_research_reply(
    room_title: str,
    research: Dict[str, Any],
    sender_handle: str,
    user_text: str,
) -> Dict[str, Any]:
    role = _pick_research_role(research)
    question = _trim_text(research.get("question") or room_title, 220)
    lead = _trim_text(user_text, 180)
    open_questions = research.get("open_questions") or []
    next_actions = research.get("next_actions") or []

    if not research.get("key_sources"):
        contribution = "Turn the latest point into a verifiable source entry before opening a new branch."
        next_step = "Add the first source that can test the current claim, then note why it matters."
    elif not research.get("findings"):
        contribution = "Convert the latest signal into one provisional finding tied to evidence, not just chat."
        next_step = "Capture one finding in the research panel and keep it narrow enough to verify."
    elif open_questions:
        contribution = "Push on the main unresolved question instead of starting a parallel thread."
        next_step = f"Advance this question: {_trim_text(open_questions[0], 180)}"
    elif next_actions:
        contribution = "Continue the active handoff so the room compounds instead of resetting."
        next_step = f"Pick up this next action: {_trim_text(next_actions[0], 180)}"
    else:
        contribution = "Stress-test the current summary against the newest message and update the shared record."
        next_step = "Leave a short handoff that states what changed and what still needs evidence."

    lines = [
        f"Role: {role}.",
        f"Research focus: {question or room_title}.",
        f"Response to {sender_handle}: {_trim_text(lead or 'read the room, then extend the shared record instead of repeating it.', 220)}",
        f"Contribution: {contribution}",
        f"Next step: {next_step}",
        f"Continuity: {_trim_text(research.get('bot_return_policy'), 260)}",
    ]
    return {"role": role, "content": "\n".join(lines)}


def _build_general_reply(room_title: str, sender_handle: str, user_text: str) -> Dict[str, Any]:
    lead = _trim_text(user_text, 180) or "the latest room update"
    lines = [
        "Role: collaborator.",
        f"Room: {_trim_text(room_title, 180) or 'active thread'}.",
        f"Response to {sender_handle}: {lead}",
        "Contribution: add one concrete source, question, finding, or next action so the thread can compound.",
        "Next step: leave a handoff that tells the next participant exactly where to continue.",
        "Continuity: return at the next daily review if the room is still active.",
    ]
    return {"role": "collaborator", "content": "\n".join(lines)}


async def generate_bot_reply(ctx: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    db = ctx.get("db")
    if db is None:
        return {"ok": False, "error": "missing db in worker context"}

    channel_id = payload.get("channel_id")
    user_message_id = payload.get("user_message_id")
    user_text = (payload.get("user_text") or "").strip()
    if not channel_id or not user_message_id:
        return {"ok": False, "error": "missing channel_id or user_message_id"}

    channel = await db.channels.find_one({"id": channel_id}, {"_id": 0})
    if not channel:
        return {"ok": False, "error": "channel not found"}
    room = await db.rooms.find_one({"id": channel.get("room_id")}, {"_id": 0})
    if not room:
        return {"ok": False, "error": "room not found"}

    source_message = await db.messages.find_one({"id": user_message_id}, {"_id": 0})
    sender_handle = (
        (source_message or {}).get("sender_handle")
        or (source_message or {}).get("sender_type")
        or "participant"
    )

    now = datetime.now(timezone.utc).isoformat()
    research = apply_research_protocol_defaults(room.get("research") or {})
    is_research_room = (room.get("source") or {}).get("kind") == "research_project"
    reply_payload = (
        _build_research_reply(room.get("title") or "", research, sender_handle, user_text)
        if is_research_room
        else _build_general_reply(room.get("title") or "", sender_handle, user_text)
    )

    bot_msg = {
        "id": str(uuid.uuid4()),
        "channel_id": channel_id,
        "sender_type": "bot",
        "sender_id": "sparkbot",
        "sender_handle": "sparkbot",
        "actor_type": "bot",
        "actor_id": "sparkbot",
        "operator_user_id": None,
        "operator_handle": None,
        "content": reply_payload["content"],
        "created_at": now,
        "updated_at": now,
        "in_reply_to": user_message_id,
        "metadata": {
            "source": "bot_reply_job",
            "role": reply_payload["role"],
            "research_room": is_research_room,
        },
    }

    await db.messages.insert_one(bot_msg)
    if is_research_room:
        updated_research = record_bot_research_activity(research, now)
        await db.rooms.update_one(
            {"id": room["id"]},
            {"$set": {"research": updated_research, "updated_at": now}},
        )
    return {"ok": True, "bot_message_id": bot_msg["id"], "ts": int(time.time())}
