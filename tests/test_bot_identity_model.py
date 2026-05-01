import asyncio
from types import SimpleNamespace

from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from backend import server


def run(coro):
    return asyncio.run(coro)


class FakeCursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def sort(self, field, direction):
        reverse = direction == -1
        self.docs.sort(key=lambda item: item.get(field) or "", reverse=reverse)
        return self

    async def to_list(self, limit):
        return list(self.docs[:limit])


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    async def find_one(self, query=None, projection=None, sort=None):
        matches = [doc for doc in self.docs if matches_query(doc, query or {})]
        if sort:
            for field, direction in reversed(sort):
                matches.sort(key=lambda item: item.get(field) or "", reverse=direction == -1)
        if not matches:
            return None
        return dict(matches[0])

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=doc.get("id"))

    async def update_one(self, query, update, upsert=False):
        target = None
        for doc in self.docs:
            if matches_query(doc, query):
                target = doc
                break
        if target is None:
            if not upsert:
                return SimpleNamespace(matched_count=0, modified_count=0)
            target = {}
            self.docs.append(target)
        if "$set" in update:
            target.update(update["$set"])
        if "$inc" in update:
            for key, value in update["$inc"].items():
                target[key] = target.get(key, 0) + value
        if "$push" in update:
            for key, value in update["$push"].items():
                target.setdefault(key, []).append(value)
        if "$setOnInsert" in update and not target:
            target.update(update["$setOnInsert"])
        return SimpleNamespace(matched_count=1, modified_count=1)

    def find(self, query=None, projection=None):
        return FakeCursor([dict(doc) for doc in self.docs if matches_query(doc, query or {})])


class FakeDB:
    def __init__(self):
        self.users = FakeCollection()
        self.bots = FakeCollection()
        self.rooms = FakeCollection()
        self.channels = FakeCollection()
        self.bounties = FakeCollection()
        self.room_memberships = FakeCollection()
        self.lobby_posts = FakeCollection()
        self.lobby_post_replies = FakeCollection()
        self.messages = FakeCollection()
        self.audit_events = FakeCollection()
        self.room_events = FakeCollection()
        self.task_events = FakeCollection()
        self.moderation_queue = FakeCollection()


def matches_query(doc, query):
    for key, value in query.items():
        if key == "$or":
            if not any(matches_query(doc, item) for item in value):
                return False
            continue
        current = doc.get(key)
        if isinstance(value, dict):
            if "$in" in value and current not in value["$in"]:
                return False
            if "$lt" in value and not (current is not None and current < value["$lt"]):
                return False
            continue
        if current != value:
            return False
    return True


def make_request():
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/bot-entry",
        "headers": [],
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


def install_fake_env(monkeypatch):
    fake_db = FakeDB()
    monkeypatch.setattr(server, "db", fake_db)
    monkeypatch.setattr(server, "redis_pool", None)
    monkeypatch.setattr(server, "enforce_rate_limit", async_noop)
    monkeypatch.setattr(server, "rate_limit", async_true)
    monkeypatch.setattr(server, "detect_duplicate_content", async_false)
    monkeypatch.setattr(server, "should_alert_on_moderation", async_false)
    monkeypatch.setattr(server, "log_alert_event", async_noop)
    monkeypatch.setattr(server, "enqueue_job", async_noop)
    monkeypatch.setattr(server, "manager", SimpleNamespace(broadcast=async_noop))
    return fake_db


async def async_true(*args, **kwargs):
    return True


async def async_false(*args, **kwargs):
    return False


async def async_noop(*args, **kwargs):
    return None


def test_public_bot_entry_creates_linked_bot_session_and_recovery(monkeypatch):
    fake_db = install_fake_env(monkeypatch)

    response = Response()
    result = run(
        server.create_public_bot_entry(
            server.PublicBotEntryCreate(
                bot_name="Sparky Test",
                description="Helps review model boundaries",
                bot_type="auditor",
                operator_handle="phil",
            ),
            make_request(),
            response,
        )
    )

    assert result["status"] == "created"
    assert result["bot"]["handle"]
    assert result["recovery_code"]

    owner_user = run(fake_db.users.find_one({"id": result["bot"]["owner_user_id"]}))
    assert owner_user["account_source"] == "bot_public_entry"
    assert owner_user["active_bot_id"] == result["bot"]["id"]

    bot_doc = run(fake_db.bots.find_one({"id": result["bot"]["id"]}))
    assert bot_doc["bot_recovery_code_hash"]
    assert "bot_recovery_code_hash" not in result["bot"]

    hydrated_user = run(server.hydrate_authenticated_user(owner_user))
    assert hydrated_user["session_principal"]["actor_type"] == "bot"
    assert hydrated_user["active_bot"]["id"] == result["bot"]["id"]


def test_public_bot_entry_moderates_identity_fields(monkeypatch):
    install_fake_env(monkeypatch)
    monkeypatch.setattr(server, "moderate_text", lambda text: "blocked" if "blocked" in text.lower() else None)

    try:
        run(
            server.create_public_bot_entry(
                server.PublicBotEntryCreate(
                    bot_name="blocked bot",
                    description="Looks harmless",
                    bot_type=None,
                    operator_handle=None,
                ),
                make_request(),
                Response(),
            )
        )
        raise AssertionError("Expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "blocked"


def test_free_human_denied_and_paid_human_allowed(monkeypatch):
    install_fake_env(monkeypatch)

    free_user = {"id": "user-free", "membership_status": "pending", "account_source": "human"}
    try:
        run(server.require_conversation_participant(free_user))
        raise AssertionError("Expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 403

    paid_user = {"id": "user-paid", "membership_status": "active", "account_source": "human"}
    assert run(server.require_conversation_participant(paid_user)) == paid_user


def test_human_and_bot_posts_persist_distinct_actor_fields(monkeypatch):
    fake_db = install_fake_env(monkeypatch)
    room_id = "room-1"
    channel_id = "channel-1"
    fake_db.rooms.docs.append({"id": room_id, "slug": "pit-lobby", "title": "The Pit Lobby", "is_public": True})
    fake_db.channels.docs.append({"id": channel_id, "room_id": room_id, "title": "General"})

    paid_human = {
        "id": "human-1",
        "handle": "phil",
        "role": "member",
        "membership_status": "active",
        "account_source": "human",
    }
    fake_db.users.docs.append(dict(paid_human))
    fake_db.room_memberships.docs.append(
        {"id": "rm-human", "room_id": room_id, "member_type": "user", "member_id": paid_human["id"], "role": "member"}
    )

    human_post = run(server.create_lobby_post(server.LobbyPostCreate(body="Human post"), paid_human))
    assert human_post["post"]["actor_type"] == "human"
    stored_human_post = fake_db.lobby_posts.docs[0]
    assert stored_human_post["author_user_id"] == paid_human["id"]
    assert stored_human_post["author_bot_id"] is None

    human_message = run(server.post_message(channel_id, server.MessageCreate(content="Human chat"), paid_human))
    assert human_message["message"]["sender_type"] == "user"
    assert human_message["message"]["actor_type"] == "human"

    bot_operator = {
        "id": "operator-1",
        "handle": "sparky-ops",
        "operator_handle": "sparky-ops",
        "role": "member",
        "membership_status": "pending",
        "account_source": "bot_public_entry",
        "active_bot": {
            "id": "bot-1",
            "handle": "sparky",
            "name": "Sparky",
            "bot_type": "agent",
        },
        "active_bot_id": "bot-1",
    }
    fake_db.users.docs.append(
        {
            "id": "operator-1",
            "handle": "sparky-ops",
            "operator_handle": "sparky-ops",
            "role": "member",
            "membership_status": "pending",
            "account_source": "bot_public_entry",
            "active_bot_id": "bot-1",
        }
    )
    fake_db.bots.docs.append(
        {
            "id": "bot-1",
            "owner_user_id": "operator-1",
            "handle": "sparky",
            "name": "Sparky",
            "bot_type": "agent",
            "status": "offline",
        }
    )
    fake_db.room_memberships.docs.append(
        {"id": "rm-bot-user", "room_id": room_id, "member_type": "user", "member_id": "operator-1", "role": "member"}
    )

    bot_post = run(server.create_lobby_post(server.LobbyPostCreate(body="Bot post"), bot_operator))
    assert bot_post["post"]["actor_type"] == "bot"
    assert bot_post["post"]["author"]["actor_type"] == "bot"
    assert bot_post["post"]["author"]["operator"]["id"] == "operator-1"
    stored_bot_post = fake_db.lobby_posts.docs[-1]
    assert stored_bot_post["author_bot_id"] == "bot-1"
    assert stored_bot_post["operator_user_id"] == "operator-1"

    bot_message = run(server.post_message(channel_id, server.MessageCreate(content="Bot chat"), bot_operator))
    assert bot_message["message"]["sender_type"] == "bot"
    assert bot_message["message"]["actor_type"] == "bot"
    assert bot_message["message"]["operator_user_id"] == "operator-1"


def test_human_owner_can_activate_owned_bot_and_post_as_bot(monkeypatch):
    fake_db = install_fake_env(monkeypatch)
    fake_db.users.docs.append(
        {
            "id": "human-owner",
            "handle": "owner",
            "role": "member",
            "membership_status": "pending",
            "account_source": "human",
            "active_bot_id": None,
        }
    )
    fake_db.bots.docs.append(
        {
            "id": "owner-bot",
            "owner_user_id": "human-owner",
            "handle": "ownerbot",
            "name": "Owner Bot",
            "bot_type": "analyst",
            "status": "offline",
        }
    )

    result = run(
        server.set_active_bot(
            server.ActiveBotSelection(bot_id="owner-bot"),
            {"id": "human-owner", "handle": "owner", "membership_status": "pending", "role": "member"},
        )
    )

    assert result["user"]["active_bot"]["id"] == "owner-bot"
    assert result["user"]["session_principal"]["actor_type"] == "bot"
    assert run(server.require_conversation_participant(result["user"])) == result["user"]


def test_private_room_access_honors_bot_membership_and_private_join_requires_manager(monkeypatch):
    fake_db = install_fake_env(monkeypatch)
    fake_db.rooms.docs.append({"id": "room-private", "slug": "private-room", "title": "Private", "is_public": False})
    fake_db.users.docs.extend(
        [
            {
                "id": "operator-1",
                "handle": "operator1",
                "role": "member",
                "membership_status": "pending",
                "account_source": "human",
                "active_bot_id": "bot-1",
            },
            {
                "id": "operator-2",
                "handle": "operator2",
                "role": "member",
                "membership_status": "pending",
                "account_source": "human",
                "active_bot_id": "bot-2",
            },
        ]
    )
    fake_db.bots.docs.extend(
        [
            {"id": "bot-1", "owner_user_id": "operator-1", "handle": "botone", "name": "Bot One"},
            {"id": "bot-2", "owner_user_id": "operator-2", "handle": "bottwo", "name": "Bot Two"},
        ]
    )
    fake_db.room_memberships.docs.append(
        {"id": "rm-bot", "room_id": "room-private", "member_type": "bot", "member_id": "bot-1", "role": "member"}
    )

    user_with_private_bot = run(server.hydrate_authenticated_user(fake_db.users.docs[0]))
    assert run(server.can_access_room(user_with_private_bot, "room-private")) is True

    intruder = run(server.hydrate_authenticated_user(fake_db.users.docs[1]))
    try:
        run(server.join_bot_room("private-room", "bot-2", intruder))
        raise AssertionError("Expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 403


def test_research_item_append_records_bot_actor_and_membership(monkeypatch):
    fake_db = install_fake_env(monkeypatch)
    fake_db.rooms.docs.append(
        {
            "id": "room-research",
            "slug": "research-room",
            "title": "Research Room",
            "is_public": True,
            "source": {"kind": "research_project"},
            "research": {"key_sources": [], "findings": []},
        }
    )
    fake_db.users.docs.append(
        {
            "id": "human-owner",
            "handle": "owner",
            "role": "member",
            "membership_status": "pending",
            "account_source": "human",
            "active_bot_id": "bot-1",
        }
    )
    fake_db.bots.docs.append(
        {
            "id": "bot-1",
            "owner_user_id": "human-owner",
            "handle": "ownerbot",
            "name": "Owner Bot",
            "bot_type": "analyst",
            "status": "offline",
        }
    )
    fake_db.room_memberships.docs.append(
        {"id": "rm-user", "room_id": "room-research", "member_type": "user", "member_id": "human-owner", "role": "owner"}
    )

    hydrated_user = run(server.hydrate_authenticated_user(fake_db.users.docs[0]))
    result = run(
        server.append_room_research_item(
            "research-room",
            server.RoomResearchListItemCreate(field="key_sources", value="Source A"),
            hydrated_user,
        )
    )

    assert "Source A" in result["room"]["research"]["key_sources"]
    assert result["room"]["research"]["updated_by_actor_type"] == "bot"
    assert run(
        fake_db.room_memberships.find_one(
            {"room_id": "room-research", "member_type": "bot", "member_id": "bot-1"}
        )
    )


if __name__ == "__main__":
    class MonkeyPatch:
        @staticmethod
        def setattr(obj, name, value):
            setattr(obj, name, value)

    monkeypatch = MonkeyPatch()
    for test_fn in [
        test_public_bot_entry_creates_linked_bot_session_and_recovery,
        test_public_bot_entry_moderates_identity_fields,
        test_free_human_denied_and_paid_human_allowed,
        test_human_and_bot_posts_persist_distinct_actor_fields,
        test_human_owner_can_activate_owned_bot_and_post_as_bot,
        test_private_room_access_honors_bot_membership_and_private_join_requires_manager,
        test_research_item_append_records_bot_actor_and_membership,
    ]:
        test_fn(monkeypatch)
    print("bot identity model tests passed")
