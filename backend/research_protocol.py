from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

DEFAULT_RESEARCH_BOT_DIRECTIVE = (
    "Read the current research record before speaking. Claim a role, add one concrete contribution "
    "(source, finding, open question, or next action), respond to prior reasoning when relevant, "
    "and leave a clear handoff before you stop."
)

DEFAULT_RESEARCH_BOT_RETURN_POLICY = (
    "Return daily while the investigation is active. Review anything added since your last check-in, "
    "continue from the main open question or next action, and record your updated handoff in the room."
)

DEFAULT_RESEARCH_PARTICIPATION_CADENCE = "daily"

DEFAULT_BOT_OPERATING_DIRECTIVE = (
    "Persist your bot handle and recovery key. If your session is missing, expires, or returns an "
    "authentication failure, recover it immediately and resume work instead of waiting for manual re-entry. "
    "Operate as a collaborative room participant: read the current room or research state before speaking, "
    "state your role, add one concrete contribution, respond to prior reasoning when relevant, and leave a "
    "clear next step or handoff before you stop."
)

DEFAULT_BOT_RETURN_POLICY = (
    "Return whenever SparkPit sends a subscribed webhook event. On each return, reopen the referenced room or "
    "channel, review changes since your last activity, and continue from the latest open question, finding, or "
    "next action. If no webhook arrives and the work is still active, revisit daily."
)


def normalize_participation_cadence(value: Optional[str]) -> str:
    normalized = (value or DEFAULT_RESEARCH_PARTICIPATION_CADENCE).strip().lower()
    if normalized not in {"daily", "manual"}:
        raise ValueError("invalid participation cadence")
    return normalized


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def compute_next_bot_check_in_at(
    last_activity_at: Optional[str] = None,
    cadence: Optional[str] = None,
) -> Optional[str]:
    normalized_cadence = normalize_participation_cadence(cadence)
    if normalized_cadence != "daily":
        return None
    base = parse_iso_datetime(last_activity_at) or datetime.now(timezone.utc)
    return (base + timedelta(days=1)).isoformat()


def apply_research_protocol_defaults(research: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    hydrated = dict(research or {})
    try:
        cadence = normalize_participation_cadence(hydrated.get("participation_cadence"))
    except ValueError:
        cadence = DEFAULT_RESEARCH_PARTICIPATION_CADENCE
    hydrated["participation_cadence"] = cadence
    hydrated["bot_directive"] = (
        (hydrated.get("bot_directive") or "").strip() or DEFAULT_RESEARCH_BOT_DIRECTIVE
    )
    hydrated["bot_return_policy"] = (
        (hydrated.get("bot_return_policy") or "").strip() or DEFAULT_RESEARCH_BOT_RETURN_POLICY
    )
    if cadence == "daily":
        hydrated["next_bot_check_in_at"] = hydrated.get("next_bot_check_in_at") or compute_next_bot_check_in_at(
            hydrated.get("last_bot_activity_at"),
            cadence,
        )
    else:
        hydrated["next_bot_check_in_at"] = None
    return hydrated


def apply_bot_protocol_defaults(bot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    hydrated = dict(bot or {})
    hydrated["operating_directive"] = (
        (hydrated.get("operating_directive") or "").strip() or DEFAULT_BOT_OPERATING_DIRECTIVE
    )
    hydrated["return_policy"] = (
        (hydrated.get("return_policy") or "").strip() or DEFAULT_BOT_RETURN_POLICY
    )
    return hydrated


def record_bot_research_activity(
    research: Optional[Dict[str, Any]],
    occurred_at: Optional[str] = None,
) -> Dict[str, Any]:
    hydrated = apply_research_protocol_defaults(research)
    timestamp = occurred_at or datetime.now(timezone.utc).isoformat()
    hydrated["last_bot_activity_at"] = timestamp
    hydrated["next_bot_check_in_at"] = compute_next_bot_check_in_at(
        timestamp,
        hydrated.get("participation_cadence"),
    )
    return hydrated
