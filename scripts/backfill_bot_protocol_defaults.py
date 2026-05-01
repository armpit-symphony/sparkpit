import asyncio

from backend.research_protocol import (
    DEFAULT_BOT_OPERATING_DIRECTIVE,
    DEFAULT_BOT_RETURN_POLICY,
)
from backend.server import db, now_iso


OLD_DEFAULT_BOT_OPERATING_DIRECTIVE = (
    "Operate as a collaborative room participant. Use rooms and research workspaces to extend shared "
    "context, not isolated one-off replies."
)

OLD_DEFAULT_BOT_RETURN_POLICY = (
    "Revisit active rooms daily, review new context, and continue from the latest open question, "
    "finding, or next action."
)


def should_replace_operating_directive(value):
    cleaned = (value or "").strip()
    return not cleaned or cleaned == OLD_DEFAULT_BOT_OPERATING_DIRECTIVE


def should_replace_return_policy(value):
    cleaned = (value or "").strip()
    return not cleaned or cleaned == OLD_DEFAULT_BOT_RETURN_POLICY


async def main():
    updated_count = 0
    operating_count = 0
    return_count = 0
    updated_handles = []
    now = now_iso()

    cursor = db.bots.find({}, {"_id": 0, "id": 1, "handle": 1, "operating_directive": 1, "return_policy": 1})
    async for bot in cursor:
        updates = {}
        if should_replace_operating_directive(bot.get("operating_directive")):
            updates["operating_directive"] = DEFAULT_BOT_OPERATING_DIRECTIVE
            operating_count += 1
        if should_replace_return_policy(bot.get("return_policy")):
            updates["return_policy"] = DEFAULT_BOT_RETURN_POLICY
            return_count += 1
        if not updates:
            continue
        updates["updated_at"] = now
        await db.bots.update_one({"id": bot["id"]}, {"$set": updates})
        updated_count += 1
        updated_handles.append(bot.get("handle") or bot["id"])

    print(f"bots_updated={updated_count}")
    print(f"operating_directives_updated={operating_count}")
    print(f"return_policies_updated={return_count}")
    if updated_handles:
        print("updated_handles=" + ",".join(updated_handles[:50]))


if __name__ == "__main__":
    asyncio.run(main())
