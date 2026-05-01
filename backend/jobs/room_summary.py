import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _top_speakers(messages: List[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    counts: Counter[str] = Counter()
    for message in messages:
        if message.get("sender_type") != "user":
            continue
        sender = message.get("sender_handle") or message.get("sender_id")
        if sender:
            counts[str(sender)] += 1
    top = counts.most_common(limit)
    return [{"speaker": speaker, "messages": count} for speaker, count in top]


async def summarize_room(ctx: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    db = ctx.get("db")
    if db is None:
        return {"ok": False, "error": "missing db in worker context"}

    room_id = payload.get("room_id")
    actor_user_id = payload.get("actor_user_id") or "system"
    if not room_id:
        return {"ok": False, "error": "missing room_id"}

    channels = await db.channels.find({"room_id": room_id}, {"_id": 0, "id": 1, "title": 1, "slug": 1}).to_list(1000)
    channel_ids = [channel["id"] for channel in channels if channel.get("id")]

    messages: List[Dict[str, Any]] = []
    if channel_ids:
        messages = await db.messages.find(
            {"channel_id": {"$in": channel_ids}},
            {"_id": 0},
        ).sort("created_at", -1).to_list(100)
        messages.reverse()

    task_events = await db.task_events.find(
        {"room_id": room_id},
        {"_id": 0},
    ).sort("created_at", -1).to_list(50)
    task_events.reverse()

    latest_lines: List[str] = []
    for message in messages[-10:]:
        sender = message.get("sender_handle") or message.get("sender_type") or "unknown"
        content = (message.get("content") or "").strip()
        if content:
            latest_lines.append(f"{sender}: {content[:160]}")
    if not latest_lines:
        latest_lines.append("No recent messages found.")

    event_breakdown = Counter(event.get("event_type", "unknown") for event in task_events)
    top_event_pairs = event_breakdown.most_common(6)
    top_event_lines = [f"{name} ({count})" for name, count in top_event_pairs] or ["No task events found."]

    episodic_summary = "\n".join(
        [
            f"Room memory snapshot at {now_iso()}",
            f"Channels scanned: {len(channel_ids)}",
            f"Recent messages sampled: {len(messages)}",
            f"Recent task events sampled: {len(task_events)}",
            "",
            "Recent conversation:",
            *latest_lines,
            "",
            "Task event activity:",
            *top_event_lines,
        ]
    )

    facts = [
        f"room_id={room_id}",
        f"channels={len(channel_ids)}",
        f"messages_sampled={len(messages)}",
        f"task_events_sampled={len(task_events)}",
    ]
    for speaker in _top_speakers(messages):
        facts.append(f"top_speaker:{speaker['speaker']}={speaker['messages']}")
    for event_name, count in top_event_pairs[:3]:
        facts.append(f"task_event:{event_name}={count}")

    memory_task_id = f"room-memory:{room_id}"
    ts = now_iso()
    episodic_id = f"memory-episodic:{room_id}"
    semantic_id = f"memory-semantic:{room_id}"

    episodic_doc = {
        "id": episodic_id,
        "task_id": memory_task_id,
        "room_id": room_id,
        "kind": "memory_episdodic",
        "title": "Room episodic memory",
        "body": episodic_summary,
        "metadata": {
            "messages_sampled": len(messages),
            "task_events_sampled": len(task_events),
            "channel_ids": channel_ids[:50],
        },
        "created_by_user_id": "system",
        "updated_at": ts,
    }
    semantic_doc = {
        "id": semantic_id,
        "task_id": memory_task_id,
        "room_id": room_id,
        "kind": "memory_semantic",
        "title": "Room semantic memory",
        "body": "\n".join(facts),
        "metadata": {
            "facts": facts,
        },
        "created_by_user_id": "system",
        "updated_at": ts,
    }

    await db.artifacts.update_one(
        {"id": episodic_id},
        {"$set": episodic_doc, "$setOnInsert": {"created_at": ts}},
        upsert=True,
    )
    await db.artifacts.update_one(
        {"id": semantic_id},
        {"$set": semantic_doc, "$setOnInsert": {"created_at": ts}},
        upsert=True,
    )

    room_event = {
        "id": str(uuid.uuid4()),
        "room_id": room_id,
        "event_type": "memory.summarized",
        "actor_user_id": actor_user_id,
        "payload": {
            "episodic_artifact_id": episodic_id,
            "semantic_artifact_id": semantic_id,
            "messages_sampled": len(messages),
            "task_events_sampled": len(task_events),
        },
        "created_at": ts,
    }
    await db.room_events.insert_one(room_event)

    return {
        "ok": True,
        "room_id": room_id,
        "episodic_artifact_id": episodic_id,
        "semantic_artifact_id": semantic_id,
    }
