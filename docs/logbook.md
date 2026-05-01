# UNIVERSAL HANDOFF (Copy/Paste)

Last updated: 2026-03-03
Canonical repo: https://github.com/armpit-symphony/sparkpitlabs_handoff

## 1) Project mission
SparkPit Labs is building security research tooling and an automated vulnerability discovery workflow with responsible
disclosure, then converting validated findings into paid hardening engagements.

## 2) Current snapshot
- Working:
  - Responsible disclosure pipeline active
  - 10 disclosure emails sent
  - Handoff repo created and pushed
  - Bug bounty swarm cron running every 2 hours
- Partial:
  - Authorization gate exists as a requirement but not fully enforced in code
  - TLS/Headers/Cookies modern web surface modules planned, not complete
  - Response and engagement outcomes from disclosures still unknown
- Broken:
  - No fully systematized conversion flow from disclosure to paid work yet

## 3) Active objectives (next 7 days)
1. Follow up disclosure outreach on 2026-03-06.
2. Implement authorization gate in bug-bounty-swarm (P0).
3. Add TLS/Headers modules (P1).

## 4) Key decisions already made
1. Focus vulnerability discovery on local NYC/Long Island targets (higher success and better conversion potential).
2. Build a modular Python agent/swarm framework with authorization gates and traceability.
3. Use this repo as the central handoff and coordination source of truth.

## 5) Risks and blockers
- Risks:
  - Email response rate may be low.
  - Scope creep before core pipeline is reliable.
- Blockers:
  - Need verified contact emails for some targets.
  - Authorization YAML/policy not yet enforced in code.

## 6) Scope guard
- In scope:
  - Security research tooling, responsible disclosure workflows
  - Agent swarm debugging and orchestration
  - Operational hardening (auth, rate limits, logging, secrets)
  - Science/university compute pooling exploration (design/prototype)
- Out of scope unless explicitly approved:
  - Marketing/growth work
  - UI polish while core systems are unstable
  - Major rewrites without migration plan + decision log entry

## 7) Plan labels
- Plan A: Bug bounty swarm -> vulnerabilities -> paid hardening conversions (ACTIVE).
- Plan B: Agent swarm framework + authorization gates (IN PROGRESS).
- Plan C: Enterprise security assessments (defined, not active).
- Plan D: Full pivot to science compute pooling (defined, not active).

## 8) Agent roster and status
- sparknition (architect/orchestration): Active; created handoff structure and standards.
- sparky (server ops/disclosure): Active; sent disclosures and running swarm workflow.
- agent_swarm_debugger (tooling/traceability): Active; running local target vuln workflow.
- bob (implementation): Standby; available for coding tasks/PRs.

## 9) Most recent completed work
- Created Sparkpitlabs_Handoff repo structure and core docs:
  - STATUS.md
  - DECISIONS.md
  - RUNBOOKS.md
  - AGENTS.md
  - SCOPE_GUARD.md
- Ran bug bounty swarm and found 9+ WordPress user-enumeration vulnerabilities.
- Sent 9-10 responsible disclosure emails to local targets.
- Logged session in `sessions/2026-03-01-session.md`.

## 10) Required operating ritual
Start of session:
1. Read STATUS.md.
2. Pull latest changes.
3. Read your agent NOW.md.
4. Run agent check-in prompt.

End of session:
1. Update `agents/<name>/NOW.md`.
2. Append to `agents/<name>/LOG.md`.
3. Update STATUS.md (state, blockers, objectives).
4. Append `sessions/YYYY-MM-DD-session.md`.
5. Commit and push.

## 11) Safe execution rules
- No destructive commands without explicit callout.
- Prefer read-only verification before state-changing actions.
- Log every state-changing action to the session file.

## 12) Known working paths and commands
- Swarm runtime path (server): `/home/sparky/.openclaw/workspace/bug-bounty-swarm`
- Run swarm:
  - `cd /home/sparky/.openclaw/workspace/bug-bounty-swarm`
  - `bash swarm-runner.sh`
- Handoff repo path on this laptop: `C:\Users\yopsp\sparkpitlabs_handoff`

## 13) Immediate next actions for receiving Codex
1. Confirm latest branch state and open STATUS.md + latest session log.
2. Implement/enforce authorization gate first (P0).
3. Build TLS/Headers modules next (P1).
4. Prepare 2026-03-06 disclosure follow-up batch with verified contacts.
5. Propose a concrete disclosure-to-paid conversion pipeline and log decision if direction changes.

## 14) Minimal handback contract (when returning work)
Return all of the following:
1. What changed (files + behavior).
2. What is still blocked and why.
3. Exact commands run for verification.
4. Updated STATUS.md and a new dated session entry.
5. Any new decision entries with rationale and consequences.


---
## Import: TheSparkPit (AWS) — 2026-03-01T175730Z

_Source: /home/ubuntu/thesparkpit (main @ fb048d313edb9a5976a642e99e427cf0f3b5b033)_

# TheSparkPit Handoff Import (AWS)

- Imported at (UTC): 2026-03-01T175730Z
- Source: /home/ubuntu/thesparkpit
- Git: main @ fb048d313edb9a5976a642e99e427cf0f3b5b033

---
## HANDOFF_START/STATUS.md

# Status

Strategic Direction: Plan D — Intellectual Collaboration Spine

Last Updated: 2026-03-01
Last Known Good Commit: 31383136d1ef0594eee8d55755e3347d47b45c7c (branch: main)
Current Deploy Target: AWS EC2 (Docker Compose + nginx, domain: thesparkpit.com)
Current State: Deployed + committed at 46bad729a1ef0c1d770b4be88bad6c87de64085a
Current State: Site live; homepage logo NOT deployed; last known-good frontend restored from backup.
Rollback Performed: Restored /var/www/thesparkpit/ from /var/www/thesparkpit.bak.20260301-021946/
Blocker: Logo file not on AWS host; OneDrive returns HTML not PNG; Codex cannot access ChatGPT /mnt/data.
Next Objective: Upload TheSparkPit_Logo.png to AWS host via EC2 Instance Connect upload -> move to frontend/public/assets/The.SparkPit_Logo.png -> rebuild -> rsync deploy -> verify asset returns image/png.

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

---
## HANDOFF_START/sessions (chronological)

### 2026-03-01-logo-attempt.md

Tried to add homepage hero logo (top-left).

OneDrive download returned HTML "blocked" page, not PNG.

Deploy attempt led to black page; rolled back to known-good backup.

Site confirmed live post-rollback.

Pending: get real PNG onto AWS host (prefer EC2 Instance Connect upload).



---
## Import: TheSparkPit (AWS) — 2026-03-03T020059Z

_Source: /home/ubuntu/thesparkpit (main @ fb048d313edb9a5976a642e99e427cf0f3b5b033)_

# TheSparkPit Workstream Update (Sara Conner)

- Imported at (UTC): 2026-03-03T020059Z
- Source: /home/ubuntu/thesparkpit
- Git: main @ fb048d313edb9a5976a642e99e427cf0f3b5b033
- Worker: Sara Conner

## Summary of Changes
- Added work-order logbook framework in repo:
  - `ops/work_orders/README.md`
  - `ops/work_orders/logbook_template.md`
  - `ops/work_orders/03022026-01.log.md`
  - `ops/work_orders/03022026-01.md`
- Implemented membership scaffolding modules:
  - `backend/membership_states.py`
  - `backend/membership_transitions.py`
- Updated backend wiring:
  - `require_active_member` now uses shared membership middleware stub.
  - Added `set_membership_state(...)` helper path and `membership.state_change` audit placeholder emission.
  - Transition hooks added on invite claim and stripe membership status transitions.
- Added invite lifecycle harness:
  - `tests/invite_lifecycle_test.py`
  - Includes positive activation path and negative reuse/pending-access checks.
  - Added `--host` support and explicit CSRF prefetch in test flow.
- Added security baseline automation:
  - `security_checklist.md`
  - `scripts/security_verify.sh`

## Live Validation (Mode A)
- `docker compose ps`: all core services up (`backend_api`, `arq_worker`, `mongodb`, `redis`).
- `scripts/security_verify.sh` current state:
  - Cookie flags checks pass (`Secure`, `SameSite`).
  - CSRF rotation check passes.
  - HTTP->HTTPS enforcement now passes after nginx remediation.
  - Admin checks skipped without credentials.
- Invite lifecycle live run status:
  - Initial failure due missing `--host` flag support (fixed).
  - Follow-up failure due CSRF flow mismatch (fixed in harness).
  - Current blocker: missing/invalid admin credentials for live environment.

## Nginx Remediation Applied
- Root cause: conflicting `server_name` blocks on `:80`; added conf file was ignored due existing `/etc/nginx/sites-enabled/thesparkpit` HTTP block.
- Actions performed:
  - Updated active site file `/etc/nginx/sites-enabled/thesparkpit` to enforce unconditional HTTP->HTTPS redirect (including `/health`).
  - Removed `/etc/nginx/conf.d/thesparkpit_http_redirect.conf` conflict file.
  - Validated (`nginx -t`) and reloaded nginx.
- Verification:
  - `http://thesparkpit.com/health` => `301` redirect to HTTPS.
  - `https://thesparkpit.com/health` => `200`.

## Admin Bootstrap Investigation
- Security scan hit for bootstrap controls in `backend/server.py` register flow.
- Mongo query for admins returned empty list: `[]`.
- Container env check showed neither `ADMIN_BOOTSTRAP_TOKEN` nor `ALLOW_BOOTSTRAP_ADMIN` set in `backend_api`.
- Effective result: first-admin bootstrap currently disabled and blocks end-to-end invite lifecycle validation.

## Current Blockers
1. No admin user exists in production DB.
2. Bootstrap env controls are unset in backend runtime.
3. Admin-only live validation paths cannot complete until bootstrap/admin is resolved.

## Recommended Next Actions
1. Set `ADMIN_BOOTSTRAP_TOKEN` (preferred) or temporary `ALLOW_BOOTSTRAP_ADMIN=true` in backend environment.
2. Create the first admin user through `/api/auth/register` with valid CSRF + bootstrap header flow.
3. Re-run `tests/invite_lifecycle_test.py` with valid admin credentials.
4. Re-run `scripts/security_verify.sh` with admin creds to validate audit/admin/worker checks end-to-end.
---

# TheSparkPit Handoff Import (AWS)

- Imported at (UTC): 2026-03-01T175137Z
- Source: /home/ubuntu/thesparkpit
- Git: main @ fb048d313edb9a5976a642e99e427cf0f3b5b033

---
## HANDOFF_START/STATUS.md

# Status

Strategic Direction: Plan D — Intellectual Collaboration Spine

Last Updated: 2026-03-01
Last Known Good Commit: 31383136d1ef0594eee8d55755e3347d47b45c7c (branch: main)
Current Deploy Target: AWS EC2 (Docker Compose + nginx, domain: thesparkpit.com)
Current State: Deployed + committed at 46bad729a1ef0c1d770b4be88bad6c87de64085a
Current State: Site live; homepage logo NOT deployed; last known-good frontend restored from backup.
Rollback Performed: Restored /var/www/thesparkpit/ from /var/www/thesparkpit.bak.20260301-021946/
Blocker: Logo file not on AWS host; OneDrive returns HTML not PNG; Codex cannot access ChatGPT /mnt/data.
Next Objective: Upload TheSparkPit_Logo.png to AWS host via EC2 Instance Connect upload -> move to frontend/public/assets/The.SparkPit_Logo.png -> rebuild -> rsync deploy -> verify asset returns image/png.

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

---
## HANDOFF_START/sessions (chronological)

### 2026-03-01-logo-attempt.md

Tried to add homepage hero logo (top-left).

OneDrive download returned HTML "blocked" page, not PNG.

Deploy attempt led to black page; rolled back to known-good backup.

Site confirmed live post-rollback.

Pending: get real PNG onto AWS host (prefer EC2 Instance Connect upload).



---

# TheSparkPit Handoff Import (AWS)

- Imported at (UTC): 2026-03-01T175730Z
- Source: /home/ubuntu/thesparkpit
- Git: main @ fb048d313edb9a5976a642e99e427cf0f3b5b033

---
## HANDOFF_START/STATUS.md

# Status

Strategic Direction: Plan D — Intellectual Collaboration Spine

Last Updated: 2026-03-01
Last Known Good Commit: 31383136d1ef0594eee8d55755e3347d47b45c7c (branch: main)
Current Deploy Target: AWS EC2 (Docker Compose + nginx, domain: thesparkpit.com)
Current State: Deployed + committed at 46bad729a1ef0c1d770b4be88bad6c87de64085a
Current State: Site live; homepage logo NOT deployed; last known-good frontend restored from backup.
Rollback Performed: Restored /var/www/thesparkpit/ from /var/www/thesparkpit.bak.20260301-021946/
Blocker: Logo file not on AWS host; OneDrive returns HTML not PNG; Codex cannot access ChatGPT /mnt/data.
Next Objective: Upload TheSparkPit_Logo.png to AWS host via EC2 Instance Connect upload -> move to frontend/public/assets/The.SparkPit_Logo.png -> rebuild -> rsync deploy -> verify asset returns image/png.

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

---
## HANDOFF_START/sessions (chronological)

### 2026-03-01-logo-attempt.md

Tried to add homepage hero logo (top-left).

OneDrive download returned HTML "blocked" page, not PNG.

Deploy attempt led to black page; rolled back to known-good backup.

Site confirmed live post-rollback.

Pending: get real PNG onto AWS host (prefer EC2 Instance Connect upload).


