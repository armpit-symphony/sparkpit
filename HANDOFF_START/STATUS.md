# Status

Strategic Direction: Plan D — Intellectual Collaboration Spine

Last Updated: 2026-03-01
Last Known Good Commit: 31383136d1ef0594eee8d55755e3347d47b45c7c (branch: main)
Current Deploy Target: AWS EC2 (Docker Compose + nginx, domain: thesparkpit.com)
Current State: Deployed + committed at 46bad729a1ef0c1d770b4be88bad6c87de64085a

Completed Today:
- Frontend deploy synced and verified: nginx now serves `static/js/main.9bc58a0e.js`, matching `frontend/build` hash.
- Frontend rollback: `rsync -a --delete /var/www/thesparkpit.bak.20260301-021946/ /var/www/thesparkpit/`.
- Added auth audit events in backend: `auth.register`, `auth.login.failure`, `auth.login.success`, `auth.logout`.
- Verified in Mongo `audit_events` that failed login, successful login, logout, and register all emit events with request metadata (`ip`, `user_agent`, `ts`, `success`, `reason` where applicable).
- Added admin-action audit events on existing admin endpoints: `admin.invite_code.create`, `admin.moderation.resolve`, `admin.user|bot.ban`, `admin.user|bot.shadow_ban` with `admin_user_id`, target IDs, `action`, `before/after`, and request metadata.
- Verified end-to-end admin audit pipeline: executed `POST /api/admin/invite-codes`, confirmed event in Mongo `audit_events`, and confirmed worker-processed Redis record (`tsp:audits:<event_id>`).
- Verified system health and worker integrity: API/nginx health 200, Redis/Mongo reachable, worker heartbeat present, queue enqueue/dequeue test passed.
- Added and verified retry/backoff proof job (`backend.worker.retry_probe`): observed first-attempt retry defer (2s), `try=2` on worker logs, and success with attempts counter `2`.

Patch State:
- Backend audit patch deployed but uncommitted (local-only). Commit + rebuild required before next deploy.

Known Broken / Risks:
- New registrations default to `membership_status=pending` and no invite codes exist (`invite_codes=0`), blocking `require_active_member` flows without manual activation/payment flow.
- Backend and worker patches are not committed yet; a future rebuild from clean source could drop these changes.

Today’s Objective:
- Commit local backend/worker/runbook changes, rebuild once more, and rerun auth + admin + retry probes for a committed-and-deployed baseline.
