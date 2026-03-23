import os
import sys
import secrets
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import MongoClient
from passlib.context import CryptContext

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / "backend" / ".env")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def main():
    env = os.environ.get("ENV", "development").lower()
    if env == "production" and os.environ.get("I_KNOW_WHAT_IM_DOING") != "1":
        print("Refusing to run in production. Set I_KNOW_WHAT_IM_DOING=1 to override.")
        sys.exit(1)

    admin_email = os.environ.get("ADMIN_EMAIL")
    if not admin_email:
        print("ADMIN_EMAIL is required")
        sys.exit(1)

    admin_handle = os.environ.get("ADMIN_HANDLE", "phil")
    admin_password = os.environ.get("ADMIN_PASSWORD")
    force = os.environ.get("FORCE") == "1"

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        print("MONGO_URL and DB_NAME must be set in backend/.env")
        sys.exit(1)

    client = MongoClient(mongo_url)
    db = client[db_name]

    existing = db.users.find_one({"email": admin_email})
    if existing:
        if not force:
            print("User exists; use FORCE=1 to promote")
            sys.exit(0)
        db.users.update_one(
            {"email": admin_email},
            {
                "$set": {
                    "role": "admin",
                    "membership_status": "active",
                    "joined_at": now_iso(),
                    "membership_activated_at": now_iso(),
                    "updated_at": now_iso(),
                }
            },
        )
        print(f"Admin ready: email={admin_email} handle={existing.get('handle')} role=admin membership=active")
        sys.exit(0)

    if not admin_password:
        admin_password = secrets.token_urlsafe(12)

    user_doc = {
        "id": secrets.token_hex(16),
        "email": admin_email,
        "handle": admin_handle,
        "password_hash": pwd_context.hash(admin_password),
        "role": "admin",
        "membership_status": "active",
        "joined_at": now_iso(),
        "membership_activated_at": now_iso(),
        "stripe_customer_id": None,
        "stripe_session_id": None,
        "stripe_session_status": None,
        "reputation": {
            "bounties_claimed": 0,
            "bounties_submitted": 0,
            "bounties_approved": 0,
            "completion_rate": 0.0,
        },
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    db.users.insert_one(user_doc)

    print("Admin created (credentials below, store securely):")
    print(f"email={admin_email}")
    print(f"handle={admin_handle}")
    print(f"password={admin_password}")
    print("Admin ready: email={0} handle={1} role=admin membership=active".format(admin_email, admin_handle))


if __name__ == "__main__":
    main()
