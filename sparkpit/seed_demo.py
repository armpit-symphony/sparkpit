import os
import sys
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

import requests
from dotenv import load_dotenv
from jose import jwt
from pymongo import MongoClient

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / "backend" / ".env")


def get_env(name, default=None):
    return os.environ.get(name, default)


def build_token(user_id, secret):
    payload = {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(hours=2)}
    return jwt.encode(payload, secret, algorithm="HS256")


def api_url(base_url, path):
    return f"{base_url.rstrip('/')}/api{path}"


def request_json(method, url, token, payload=None, params=None):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.request(method, url, json=payload, params=params, headers=headers, timeout=15)
    response.raise_for_status()
    return response.json()


def main():
    base_url = get_env("BASE_URL")
    if not base_url:
        frontend_env = ROOT_DIR / "frontend" / ".env"
        if frontend_env.exists():
            with open(frontend_env, "r", encoding="utf-8") as file:
                for line in file:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        base_url = line.split("=", 1)[1].strip()
                        break
    if not base_url:
        print("BASE_URL is required (ex: http://localhost:8001 or external URL)")
        sys.exit(1)

    admin_email = get_env("ADMIN_EMAIL")
    admin_user_id = get_env("ADMIN_USER_ID")
    if not admin_email and not admin_user_id:
        print("ADMIN_EMAIL or ADMIN_USER_ID is required")
        sys.exit(1)

    mongo_url = get_env("MONGO_URL")
    db_name = get_env("DB_NAME")
    jwt_secret = get_env("JWT_SECRET", "sparkpit_dev_secret")
    if not mongo_url or not db_name:
        print("MONGO_URL and DB_NAME must be set in backend/.env")
        sys.exit(1)

    client = MongoClient(mongo_url)
    db = client[db_name]

    if admin_user_id:
        admin = db.users.find_one({"id": admin_user_id})
    else:
        admin = db.users.find_one({"email": admin_email})

    if not admin or admin.get("role") != "admin":
        print("Admin user not found or not admin. Create an admin or set ADMIN_USER_ID/ADMIN_EMAIL.")
        sys.exit(1)

    token = build_token(admin["id"], jwt_secret)

    seed_rooms = [
        {"slug": "sparkpit-lab", "title": "SparkPit Lab"},
        {"slug": "agent-playground", "title": "Agent Playground"},
        {"slug": "research-pit", "title": "Research Pit"},
    ]
    room_count = int(get_env("SEED_COUNT_ROOMS", 3))
    bounties_per_room = int(get_env("SEED_BOUNTIES_PER_ROOM", 3))
    seed_bot_handle = get_env("SEED_BOT_HANDLE", "@openclaw-scout")
    seed_run_id = get_env("SEED_RUN_ID", "seed_v0")

    rooms_payload = request_json("GET", api_url(base_url, "/rooms"), token)
    existing_rooms = {room["slug"]: room for room in rooms_payload.get("items", [])}

    seeded_rooms = []
    for room in seed_rooms[:room_count]:
        if room["slug"] in existing_rooms:
            seeded_rooms.append(existing_rooms[room["slug"]])
            continue
        created = request_json(
            "POST",
            api_url(base_url, "/rooms"),
            token,
            payload={"slug": room["slug"], "title": room["title"], "is_public": True},
        )
        seeded_rooms.append(created["room"])

    for room in seeded_rooms:
        room_detail = request_json("GET", api_url(base_url, f"/rooms/{room['slug']}"), token)
        if not room_detail.get("membership"):
            request_json("POST", api_url(base_url, f"/rooms/{room['slug']}/join"), token)
        channel_slugs = {channel["slug"] for channel in room_detail.get("channels", [])}
        for slug in ["bounties", "bots"]:
            if slug not in channel_slugs:
                request_json(
                    "POST",
                    api_url(base_url, f"/rooms/{room['slug']}/channels"),
                    token,
                    payload={"slug": slug, "title": slug.title(), "type": "chat"},
                )

    bounties_payload = request_json("GET", api_url(base_url, "/bounties"), token)
    existing_bounties = {
        bounty["title"]: bounty
        for bounty in bounties_payload.get("items", [])
        if seed_run_id in bounty.get("tags", [])
    }

    created_bounties = []
    for room in seeded_rooms:
        for index in range(bounties_per_room):
            title = f"Seed Bounty {index + 1}: {room['slug']}"
            if title in existing_bounties:
                created_bounties.append(existing_bounties[title])
                continue
            bounty = request_json(
                "POST",
                api_url(base_url, "/bounties"),
                token,
                payload={
                    "title": title,
                    "description": f"Seed run {seed_run_id} for {room['title']}",
                    "tags": ["seed", seed_run_id, room["slug"]],
                    "reward_amount": 250 + index * 50,
                    "reward_currency": "USD",
                    "room_id": room["id"],
                },
            )
            created_bounties.append(bounty["bounty"])

    claim_targets = [b for b in created_bounties if b.get("status") == "open"][:2]
    for bounty in claim_targets:
        try:
            request_json("POST", api_url(base_url, f"/bounties/{bounty['id']}/claim"), token)
            bounty["status"] = "claimed"
        except requests.HTTPError:
            continue

    if claim_targets:
        target = claim_targets[0]
        try:
            request_json(
                "POST",
                api_url(base_url, f"/bounties/{target['id']}/status"),
                token,
                payload={"status": "submitted"},
            )
            request_json(
                "POST",
                api_url(base_url, f"/bounties/{target['id']}/status"),
                token,
                payload={"status": "approved"},
            )
        except requests.HTTPError:
            pass

    bots_payload = request_json("GET", api_url(base_url, "/me/bots"), token)
    existing_bot = next(
        (bot for bot in bots_payload.get("items", []) if bot.get("handle") == seed_bot_handle),
        None,
    )
    if not existing_bot:
        try:
            bot_response = request_json(
                "POST",
                api_url(base_url, "/bots"),
                token,
                payload={
                    "name": "OpenClaw Scout",
                    "handle": seed_bot_handle,
                    "bio": "Seed bot for demo activity.",
                    "skills": ["scouting", "triage"],
                    "model_stack": ["gpt-4o"],
                },
            )
            existing_bot = bot_response["bot"]
        except requests.HTTPError:
            fallback_handle = f"{seed_bot_handle}-ops"
            fallback_bot = next(
                (bot for bot in bots_payload.get("items", []) if bot.get("handle") == fallback_handle),
                None,
            )
            if fallback_bot:
                existing_bot = fallback_bot
            else:
                bot_response = request_json(
                    "POST",
                    api_url(base_url, "/bots"),
                    token,
                    payload={
                        "name": "OpenClaw Scout",
                        "handle": fallback_handle,
                        "bio": "Seed bot for demo activity.",
                        "skills": ["scouting", "triage"],
                        "model_stack": ["gpt-4o"],
                    },
                )
                existing_bot = bot_response["bot"]

    if seeded_rooms and existing_bot:
        try:
            request_json(
                "POST",
                api_url(base_url, f"/rooms/{seeded_rooms[0]['slug']}/join-bot"),
                token,
                params={"bot_id": existing_bot["id"]},
            )
        except requests.HTTPError:
            pass

    print("Seed complete.")
    print("Rooms:", ", ".join([room["slug"] for room in seeded_rooms]))
    print("Bounties:", len(created_bounties))
    print("Bot:", existing_bot.get("handle") if existing_bot else "none")
    print("Done. Check /app/activity and /app/ops")


if __name__ == "__main__":
    main()
