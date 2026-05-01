# Security Hardening Baseline Checklist

Scope: API-level verification automation for launch stabilization.

## Coverage
- Cookie flags (`Secure`, `HttpOnly`, `SameSite`)
- CSRF rotation behavior
- Auth failure audit logging
- Admin invite/audit logging
- Worker heartbeat visibility (`/api/admin/ops`)
- HTTPS enforcement signal

## Prerequisites
- API reachable at target base URL
- Admin account credentials available for admin-only checks
- `curl` installed

## Run
```bash
# Minimal checks (public + CSRF)
bash scripts/security_verify.sh

# Full checks (admin-authenticated)
VERIFY_ADMIN_EMAIL='admin@example.com' \
VERIFY_ADMIN_PASSWORD='***' \
VERIFY_ADMIN_BOOTSTRAP_TOKEN='' \
bash scripts/security_verify.sh https://thesparkpit.com
```

## Notes
- Script is verification-only and non-destructive.
- Missing admin credentials will skip admin-only checks with warnings.
