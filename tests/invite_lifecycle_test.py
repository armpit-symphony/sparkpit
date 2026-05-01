#!/usr/bin/env python3
"""
Invite lifecycle API harness.

Simulates:
1) invite creation
2) registration
3) invite consumption
4) activation
5) restricted endpoint access checks
"""

import argparse
import os
import sys
import time
import uuid
from typing import Any, Dict

import requests


def api_root(base_url: str) -> str:
    trimmed = base_url.rstrip("/")
    return trimmed if trimmed.endswith("/api") else f"{trimmed}/api"


def csrf_headers(session: requests.Session) -> Dict[str, str]:
    token = session.cookies.get("spark_csrf")
    return {"X-CSRF-Token": token} if token else {}


def fetch_csrf(session: requests.Session, api_base: str):
    resp = session.get(f"{api_base}/auth/csrf", timeout=20)
    if resp.status_code != 200:
        raise RuntimeError(f"CSRF fetch failed ({resp.status_code}): {resp.text}")


def register_or_login(
    session: requests.Session,
    api_base: str,
    email: str,
    handle: str,
    password: str,
    admin_bootstrap_token: str = "",
) -> Dict[str, Any]:
    fetch_csrf(session, api_base)
    register_headers = {}
    if admin_bootstrap_token:
        register_headers["X-Admin-Bootstrap"] = admin_bootstrap_token
    payload = {"email": email, "handle": handle, "password": password}
    register_resp = session.post(f"{api_base}/auth/register", json=payload, headers=register_headers, timeout=20)
    if register_resp.status_code == 200:
        return register_resp.json()
    if register_resp.status_code not in (400, 403):
        raise RuntimeError(f"Register failed unexpectedly ({register_resp.status_code}): {register_resp.text}")

    login_resp = session.post(
        f"{api_base}/auth/login",
        json={"email": email, "password": password},
        headers=csrf_headers(session),
        timeout=20,
    )
    if login_resp.status_code != 200:
        raise RuntimeError(f"Login failed ({login_resp.status_code}): {login_resp.text}")
    return login_resp.json()


def assert_status(resp: requests.Response, expected: int, label: str):
    if resp.status_code != expected:
        raise RuntimeError(f"{label} expected {expected}, got {resp.status_code}: {resp.text}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Invite lifecycle verification harness")
    parser.add_argument("--base-url", default=os.environ.get("TSP_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--host", default=os.environ.get("TSP_HOST_HEADER", ""))
    parser.add_argument("--admin-email", default=os.environ.get("TSP_ADMIN_EMAIL", "admin+invite-harness@sparkpit.local"))
    parser.add_argument("--admin-password", default=os.environ.get("TSP_ADMIN_PASSWORD", "ChangeMe_InviteHarness_01!"))
    parser.add_argument("--member-password", default=os.environ.get("TSP_MEMBER_PASSWORD", "ChangeMe_MemberHarness_01!"))
    parser.add_argument("--admin-bootstrap-token", default=os.environ.get("ADMIN_BOOTSTRAP_TOKEN", ""))
    args = parser.parse_args()

    suffix = f"{int(time.time())}-{uuid.uuid4().hex[:6]}"
    admin_handle = f"admin_{suffix}"[:28]
    member_handle = f"member_{suffix}"[:28]
    member2_handle = f"member2_{suffix}"[:28]
    member_email = f"member+{suffix}@sparkpit.local"
    member2_email = f"member2+{suffix}@sparkpit.local"

    api_base = api_root(args.base_url)
    print(f"[info] API base: {api_base}")

    admin_session = requests.Session()
    member_session = requests.Session()
    member2_session = requests.Session()
    if args.host:
        admin_session.headers.update({"Host": args.host})
        member_session.headers.update({"Host": args.host})
        member2_session.headers.update({"Host": args.host})

    admin_user = register_or_login(
        admin_session,
        api_base,
        args.admin_email,
        admin_handle,
        args.admin_password,
        admin_bootstrap_token=args.admin_bootstrap_token,
    )
    admin_role = ((admin_user or {}).get("user") or {}).get("role")
    if admin_role != "admin":
        raise RuntimeError(f"Admin account required for harness. Current role: {admin_role}")
    print("[pass] admin auth established")

    invite_resp = admin_session.post(
        f"{api_base}/admin/invite-codes",
        json={"max_uses": 1},
        headers=csrf_headers(admin_session),
        timeout=20,
    )
    assert_status(invite_resp, 200, "invite create")
    invite_code = invite_resp.json().get("invite_code", {}).get("code")
    if not invite_code:
        raise RuntimeError("Invite code missing in response")
    print(f"[pass] invite created: {invite_code}")

    register_or_login(member_session, api_base, member_email, member_handle, args.member_password)
    pending_resp = member_session.get(f"{api_base}/rooms", timeout=20)
    assert_status(pending_resp, 403, "pending user restricted endpoint")
    print("[pass] pending user denied restricted endpoint")

    claim_resp = member_session.post(
        f"{api_base}/auth/invite/claim",
        json={"code": invite_code},
        headers=csrf_headers(member_session),
        timeout=20,
    )
    assert_status(claim_resp, 200, "invite claim")
    active_resp = member_session.get(f"{api_base}/rooms", timeout=20)
    assert_status(active_resp, 200, "active user restricted endpoint")
    print("[pass] valid invite activates membership and unlocks restricted endpoint")

    register_or_login(member2_session, api_base, member2_email, member2_handle, args.member_password)
    reused_resp = member2_session.post(
        f"{api_base}/auth/invite/claim",
        json={"code": invite_code},
        headers=csrf_headers(member2_session),
        timeout=20,
    )
    if reused_resp.status_code not in (400, 404):
        raise RuntimeError(f"reused invite expected 400/404, got {reused_resp.status_code}: {reused_resp.text}")
    print("[pass] reused invite rejected")

    print("[done] invite lifecycle harness checks passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[fail] {exc}", file=sys.stderr)
        raise SystemExit(1)
