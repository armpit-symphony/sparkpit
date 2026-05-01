#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
ADMIN_EMAIL="${ADMIN_EMAIL:-phil@thesparkpit.com}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"
TEST_PASSWORD="${TEST_PASSWORD:-ChangeMe_123!}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TEST_EMAIL="phil+modea-${STAMP}@thesparkpit.com"

command -v curl >/dev/null 2>&1 || { echo "Missing curl"; exit 2; }
command -v jq >/dev/null 2>&1 || { echo "Missing jq"; exit 2; }

if [ -z "$ADMIN_PASSWORD" ]; then
  echo "Use: ADMIN_PASSWORD='yourpass' ./scripts/mode_a_verify.sh"
  exit 2
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
AC="$TMP/admin.cookies"
UC="$TMP/user.cookies"

csrf() {
  awk 'BEGIN{IGNORECASE=1} $6 ~ /csrf/ {print $7}' "$1" | tail -n1
}

api() {
  local method="$1" url="$2" jar="$3" data="${4:-}"
  shift 4 || true
  if [ -n "$data" ]; then
    curl -sS -X "$method" "$url" \
      -H "Content-Type: application/json" \
      -b "$jar" -c "$jar" "$@" \
      --data "$data"
  else
    curl -sS -X "$method" "$url" \
      -H "Content-Type: application/json" \
      -b "$jar" -c "$jar" "$@"
  fi
}

code() {
  curl -sS -o /dev/null -w "%{http_code}" "$@"
}

echo "== Admin login"
api POST "$BASE_URL/api/auth/login" "$AC" \
  "$(jq -cn --arg e "$ADMIN_EMAIL" --arg p "$ADMIN_PASSWORD" '{email:$e,password:$p}')" \
  >/dev/null

echo "== Create invite"
A_CSRF="$(csrf "$AC" || true)"
if [ -n "${A_CSRF:-}" ]; then
  INVITE_RESP="$(api POST "$BASE_URL/api/admin/invite-codes" "$AC" '{}' -H "X-CSRF-Token: $A_CSRF")"
else
  INVITE_RESP="$(api POST "$BASE_URL/api/admin/invite-codes" "$AC" '{}')"
fi

INVITE_CODE="$(echo "$INVITE_RESP" | jq -r '.code // .invite_code // .data.code // empty')"
[ -n "$INVITE_CODE" ] || { echo "Could not parse invite code"; echo "$INVITE_RESP"; exit 2; }
echo "Invite: $INVITE_CODE"

echo "== Register test user"
api POST "$BASE_URL/api/auth/register" "$UC" \
  "$(jq -cn --arg e "$TEST_EMAIL" --arg p "$TEST_PASSWORD" --arg c "$INVITE_CODE" '{email:$e,password:$p,invite_code:$c}')" \
  >/dev/null

echo "== User login"
api POST "$BASE_URL/api/auth/login" "$UC" \
  "$(jq -cn --arg e "$TEST_EMAIL" --arg p "$TEST_PASSWORD" '{email:$e,password:$p}')" \
  >/dev/null

echo "== Check /api/tasks blocked before claim"
BEFORE_CODE="$(code -b "$UC" -c "$UC" "$BASE_URL/api/tasks")"
echo "tasks before claim: $BEFORE_CODE"
[ "$BEFORE_CODE" = "403" ] || { echo "Expected 403 before claim"; exit 2; }

echo "== Claim invite"
U_CSRF="$(csrf "$UC" || true)"
if [ -n "${U_CSRF:-}" ]; then
  CLAIM_RESP="$(api POST "$BASE_URL/api/auth/invite/claim" "$UC" \
    "$(jq -cn --arg c "$INVITE_CODE" '{code:$c}')" \
    -H "X-CSRF-Token: $U_CSRF")"
else
  CLAIM_RESP="$(api POST "$BASE_URL/api/auth/invite/claim" "$UC" \
    "$(jq -cn --arg c "$INVITE_CODE" '{code:$c}')")"
fi
echo "$CLAIM_RESP" | jq .

echo "== Check active status"
ME2="$(api GET "$BASE_URL/api/me" "$UC")"
STATUS2="$(echo "$ME2" | jq -r '.membership_status // .membership.status // empty')"
echo "membership_status after claim: ${STATUS2:-missing}"
[ "$STATUS2" = "active" ] || { echo "Expected active after claim"; echo "$ME2"; exit 2; }

echo "== Check /api/tasks allowed after claim"
AFTER_CODE="$(code -b "$UC" -c "$UC" "$BASE_URL/api/tasks")"
echo "tasks after claim: $AFTER_CODE"
[ "$AFTER_CODE" = "200" ] || { echo "Expected 200 after claim"; exit 2; }

echo "MODE A VERIFY SUCCESS"
echo "Test user: $TEST_EMAIL"
echo "Invite: $INVITE_CODE"
