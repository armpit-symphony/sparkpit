#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-${VERIFY_BASE_URL:-https://thesparkpit.com}}"
BASE_URL="${BASE_URL%/}"
API_BASE="${BASE_URL}/api"

ADMIN_EMAIL="${VERIFY_ADMIN_EMAIL:-}"
ADMIN_PASSWORD="${VERIFY_ADMIN_PASSWORD:-}"
ADMIN_BOOTSTRAP_TOKEN="${VERIFY_ADMIN_BOOTSTRAP_TOKEN:-}"

FAILURES=0
SKIPS=0

pass() { echo "[PASS] $*"; }
fail() { echo "[FAIL] $*"; FAILURES=$((FAILURES + 1)); }
skip() { echo "[SKIP] $*"; SKIPS=$((SKIPS + 1)); }

extract_json_field() {
  local file_path="$1"
  local field_name="$2"
  python3 - <<PY
import json
with open("${file_path}", "r", encoding="utf-8") as f:
    data = json.load(f)
value = data.get("${field_name}")
print("" if value is None else value)
PY
}

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

cookie_jar="$tmpdir/cookies.txt"
headers_file="$tmpdir/headers.txt"
body_file="$tmpdir/body.json"

if curl -sS -D "$headers_file" -o "$body_file" "$API_BASE/auth/csrf"; then
  csrf_set_cookie_line="$(grep -i '^set-cookie: spark_csrf=' "$headers_file" || true)"
  if [[ -z "$csrf_set_cookie_line" ]]; then
    fail "spark_csrf cookie missing"
  else
    echo "$csrf_set_cookie_line" | grep -qi 'Secure' && pass "spark_csrf has Secure" || fail "spark_csrf missing Secure"
    echo "$csrf_set_cookie_line" | grep -qi 'SameSite=' && pass "spark_csrf has SameSite" || fail "spark_csrf missing SameSite"
  fi

  csrf_token_1="$(extract_json_field "$body_file" csrf_token)"
  if curl -sS -o "$body_file" "$API_BASE/auth/csrf"; then
    csrf_token_2="$(extract_json_field "$body_file" csrf_token)"
    if [[ -n "$csrf_token_1" && -n "$csrf_token_2" && "$csrf_token_1" != "$csrf_token_2" ]]; then
      pass "CSRF token rotates across requests"
    else
      fail "CSRF rotation check failed"
    fi
  else
    fail "Unable to fetch second CSRF token"
  fi
else
  fail "Unable to reach $API_BASE/auth/csrf"
  fail "Skipping cookie/CSRF checks because endpoint is unreachable"
fi

if [[ "$BASE_URL" == https://* ]]; then
  http_url="http://${BASE_URL#https://}"
  http_status="$(curl -sS -o /dev/null -w '%{http_code}' "$http_url/health" || true)"
  if [[ "$http_status" == "301" || "$http_status" == "302" || "$http_status" == "307" || "$http_status" == "308" ]]; then
    pass "HTTP endpoint redirects (HTTPS enforcement signal)"
  elif [[ "$http_status" == "000" ]]; then
    skip "HTTP endpoint unreachable for HTTPS enforcement probe"
  else
    fail "HTTP endpoint did not redirect as expected (status=$http_status)"
  fi
else
  skip "HTTPS enforcement probe skipped for non-HTTPS base URL"
fi

if [[ -z "$ADMIN_EMAIL" || -z "$ADMIN_PASSWORD" ]]; then
  skip "Admin-only checks skipped (set VERIFY_ADMIN_EMAIL and VERIFY_ADMIN_PASSWORD)"
else
  admin_csrf_json="$tmpdir/admin_csrf.json"

  curl -sS -c "$cookie_jar" -b "$cookie_jar" -o "$admin_csrf_json" "$API_BASE/auth/csrf"
  admin_csrf="$(extract_json_field "$admin_csrf_json" csrf_token)"

  login_payload="{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}"
  login_code="$(curl -sS -o "$tmpdir/admin_login.json" -w '%{http_code}' \
    -c "$cookie_jar" -b "$cookie_jar" \
    -H "Content-Type: application/json" \
    -H "X-CSRF-Token: $admin_csrf" \
    -X POST "$API_BASE/auth/login" -d "$login_payload")"
  if [[ "$login_code" != "200" ]]; then
    fail "Admin login failed (status=$login_code)"
  else
    pass "Admin login succeeded"

    spark_token_cookie_line="$(grep -i 'spark_token' "$cookie_jar" || true)"
    if [[ -n "$spark_token_cookie_line" ]]; then
      pass "spark_token cookie issued"
    else
      fail "spark_token cookie missing after login"
    fi

    bad_login_payload="{\"email\":\"$ADMIN_EMAIL\",\"password\":\"invalid-password\"}"
    bad_login_code="$(curl -sS -o "$tmpdir/bad_login.json" -w '%{http_code}' \
      -H "Content-Type: application/json" \
      -X POST "$API_BASE/auth/login" -d "$bad_login_payload")"
    if [[ "$bad_login_code" == "400" ]]; then
      pass "Auth failure path returns expected 400"
    else
      fail "Auth failure path expected 400, got $bad_login_code"
    fi

    admin_csrf="$(extract_json_field "$tmpdir/admin_login.json" csrf_token)"
    if [[ -z "$admin_csrf" ]]; then
      admin_csrf="$(awk '$6=="spark_csrf"{print $7}' "$cookie_jar" | tail -n1)"
    fi

    invite_body='{"max_uses":1}'
    invite_code_status="$(curl -sS -o "$tmpdir/invite.json" -w '%{http_code}' \
      -c "$cookie_jar" -b "$cookie_jar" \
      -H "Content-Type: application/json" \
      -H "X-CSRF-Token: $admin_csrf" \
      -H "X-Admin-Bootstrap: $ADMIN_BOOTSTRAP_TOKEN" \
      -X POST "$API_BASE/admin/invite-codes" -d "$invite_body")"
    if [[ "$invite_code_status" == "200" ]]; then
      pass "Admin invite creation endpoint reachable"
    else
      fail "Admin invite creation failed (status=$invite_code_status)"
    fi

    audit_status="$(curl -sS -o "$tmpdir/audit.json" -w '%{http_code}' -c "$cookie_jar" -b "$cookie_jar" "$API_BASE/admin/audit")"
    if [[ "$audit_status" != "200" ]]; then
      fail "Admin audit feed unavailable (status=$audit_status)"
    else
      grep -q '"auth.login.failure"' "$tmpdir/audit.json" && pass "Audit contains auth.login.failure" || fail "Missing auth.login.failure in audit"
      grep -q '"admin.invite_code.create"' "$tmpdir/audit.json" && pass "Audit contains admin.invite_code.create" || fail "Missing admin.invite_code.create in audit"
    fi

    ops_status="$(curl -sS -o "$tmpdir/ops.json" -w '%{http_code}' -c "$cookie_jar" -b "$cookie_jar" "$API_BASE/admin/ops")"
    if [[ "$ops_status" != "200" ]]; then
      fail "Admin ops endpoint unavailable (status=$ops_status)"
    else
      grep -q '"worker_heartbeat"' "$tmpdir/ops.json" && pass "Worker heartbeat visible in /admin/ops" || fail "Missing worker_heartbeat in /admin/ops"
      grep -q '"worker_healthy"' "$tmpdir/ops.json" && pass "Worker health field visible in /admin/ops" || fail "Missing worker_healthy in /admin/ops"
    fi
  fi
fi

echo ""
echo "Verification complete: failures=$FAILURES skips=$SKIPS"
if [[ "$FAILURES" -gt 0 ]]; then
  exit 1
fi
