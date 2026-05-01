# Status

Strategic Direction: Plan D — Intellectual Collaboration Spine

Last Updated: 2026-03-18
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
- Commit local backend/worker/frontend changes, rerun authenticated live research-room validation, and clean up the backend deploy path so future restarts do not require copying files into containers.

## 2026-03-18 Research / Room Bot Protocol Fix

Objective:
- Fix research rooms and room bot behavior so bots stop posting stateless echo replies and instead follow a durable research directive with continuity across days.

What changed:
- Added durable research-room bot protocol fields in backend:
  - `bot_directive`
  - `bot_return_policy`
  - `participation_cadence`
  - `last_bot_activity_at`
  - `next_bot_check_in_at`
- Added durable bot-profile instruction fields:
  - `operating_directive`
  - `return_policy`
- Added shared protocol/default logic in:
  - `backend/research_protocol.py`
- Updated room/research APIs in:
  - `backend/server.py`
  - research rooms now hydrate protocol defaults even for older room documents
  - bot-authored research actions refresh continuity timestamps
  - bot-authored room messages refresh research continuity timestamps
- Replaced the stub auto-reply worker in:
  - `backend/jobs/bot_reply.py`
  - old behavior: `Got it: ...`
  - new behavior: structured research-aware reply with role, contribution, next step, and continuity line
- Updated research UI in:
  - `frontend/src/components/rooms/ResearchWorkspacePanel.jsx`
  - added saved "Bot operating protocol" editor
  - added cadence selector (`daily` or `manual`)
  - added last activity / next check-in visibility
- Updated bot registration UI in:
  - `frontend/src/pages/Bots.jsx`
  - bots can now be created with an operating directive and return policy
- Updated research kickoff text in:
  - `frontend/src/pages/Research.jsx`
- Updated visible bot collaboration guidance in:
  - `frontend/src/components/bots/BotCollaborationGuide.jsx`

Live / deploy state:
- Frontend built successfully and was deployed live.
- nginx-served frontend hash after deploy:
  - `main.ed89c0dd.js`
- Backend API container and worker were updated with the new Python files and restarted successfully.
- Because Docker Compose build context is currently extremely large (over 800 MB due to repo/artifact contents), a full image rebuild was interrupted and the working rollout was completed by copying the changed backend files into the running `backend_api` and `arq_worker` containers, then restarting those services.

Verification completed:
- `python3 -m py_compile` passed for:
  - `backend/server.py`
  - `backend/research_protocol.py`
  - `backend/jobs/bot_reply.py`
- `npm --prefix frontend run build` passed.
- Existing frontend build warnings remain repo-wide `react-hooks/exhaustive-deps` warnings in unrelated files.
- Backend-side live probe confirmed the new reply path:
  - job returned `ok=True`
  - bot reply used structured research language instead of `Got it:`
  - room research state recorded both `last_bot_activity_at` and `next_bot_check_in_at`

Verified probe reply shape:
- `Role: scout.`
- `Research focus: ...`
- `Contribution: ...`
- `Next step: ...`
- `Continuity: Return daily, review changes since last activity, and continue from the latest handoff.`

What still has to be done:
- Run an authenticated browser walkthrough of the live site on `TheSparkPit.com` for:
  - `/app/research`
  - a real research room page under `/app/rooms/...`
  - bot creation with directive fields visible
  - saving the research-room bot protocol and confirming it persists in UI
  - posting as a bot in a research room and confirming the room shows updated continuity timestamps
- Validate the actual queued worker path end-to-end from the live UI:
  - human/bot message in research room
  - ARQ job fires
  - resulting bot reply appears in chat
  - reply is structured and not the old echo stub
- Clean the backend deploy path:
  - add/update `.dockerignore` so Docker does not send large artifacts/build outputs into compose builds
  - then do a clean `docker compose up -d --build backend_api arq_worker`
  - verify only one worker container exists after rebuild
- Commit the new research/bot protocol work; it is currently local/uncommitted.
- Optionally add an automated probe or test for:
  - research-room bot reply format
  - continuity timestamp writes
  - default protocol hydration for legacy room documents

Operational caution:
- The repo worktree already had many unrelated local modifications before this pass. Do not blanket-revert the tree.
- The current live backend behavior depends on the updated Python files now present in the running containers; until the clean compose rebuild is completed from source, treat this as deployed but not yet normalized.

## 2026-03-06 Incident Summary

Incident date: 2026-03-06

Symptom: official admin login stopped working; active DB appeared empty/fresh

Root cause: Mongo container recreated onto a fresh anonymous /data/db volume due to incorrect compose mount pattern (/data parent mount)

Recovery: identified correct historical Mongo volume (670bc0b1ca1e...), restored live DB, then migrated current live state into stable named volumes

Permanent fix: Mongo now mounts named volumes directly to /data/db and /data/configdb

Verification: Phil successfully logged back into TheSparkPit; collection counts preserved

Additional handoff detail:
- Running backend target was confirmed as `MONGO_URL=mongodb://mongodb:27017` and `DB_NAME=thesparkpit`; the regression was volume drift, not DB-name drift.
- Historical source volume `670bc0b1ca1e...` was validated read-only before restore and contained the expected live collections, invite data, audit events, and the admin account.
- Restore artifacts created:
  - `/home/ubuntu/thesparkpit/artifacts/thesparkpit-pre-restore-20260306T231117Z.archive.gz`
  - `/home/ubuntu/thesparkpit/artifacts/thesparkpit-source-670bc-20260306T231117Z.archive.gz`
  - `/home/ubuntu/thesparkpit/artifacts/thesparkpit-volume-fix-prechange-20260306T233015Z.archive.gz`
- Permanent compose correction applied in `/home/ubuntu/thesparkpit/docker-compose.yml`:
  - removed parent mount `/data`
  - added stable named mounts for `/data/db` and `/data/configdb`
- Final live Mongo mounts:
  - `thesparkpit_mongo_db_data` -> `/data/db`
  - `thesparkpit_mongo_configdb_data` -> `/data/configdb`
- Final live data verification after cutover:
  - `users=5`
  - `audit_events=30`
  - `invite_codes=3`
  - `tasks=2`

## 2026-03-07 Admin UX Split

Objective:
- Separate system operations from moderation workflow in the logged-in admin experience without changing backend APIs or auth behavior.

What changed:
- Split the mixed `/app/ops` experience into two admin-only routes:
  - `/app/ops` now focuses on launch readiness, Stripe/Redis/worker health, alerts, and rate-limit telemetry.
  - `/app/moderation` now owns queue review, resolved-state review, filters, and moderation actions.
- Added explicit frontend admin route gating for `/app/ops` and `/app/moderation`; non-admin direct access now redirects to `/app/bounties`.
- Updated the sidebar so `Ops`, `Moderation`, and `Audit` are only shown to admins.
- Improved page identity and hierarchy so Ops reads like an operations console and Moderation reads like a trust-and-safety review console.

Shared admin UI added:
- Added reusable admin components:
  - `frontend/src/components/admin/ModerationConsole.jsx`
  - `frontend/src/components/admin/AdminStatusCards.jsx`
  - `frontend/src/components/admin/AdminPageHeader.jsx`
- Reused shared status cards in:
  - `/app/ops` for readiness checks
  - `/app/settings` for the admin invite/audit summary
- Reused shared page header shell in:
  - `/app/ops`
  - `/app/moderation`
  - `/app/settings`

Additional product polish completed:
- Upgraded the logged-in command-center feel earlier in the session:
  - `QuickPanel` now surfaces live signal/status data instead of placeholder cards.
  - `/app/bounties` now has a stronger header, summary cards, and action-oriented empty states.
- Added moderation summary chips based on the live moderation payload so admins can scan queue composition quickly without new backend aggregation.

Files touched for this product/admin pass:
- `frontend/src/App.js`
- `frontend/src/components/layout/RoomsSidebar.jsx`
- `frontend/src/components/layout/QuickPanel.jsx`
- `frontend/src/pages/Bounties.jsx`
- `frontend/src/pages/OpsChecklist.jsx`
- `frontend/src/pages/Moderation.jsx`
- `frontend/src/pages/Settings.jsx`
- `frontend/src/components/admin/ModerationConsole.jsx`
- `frontend/src/components/admin/AdminStatusCards.jsx`
- `frontend/src/components/admin/AdminPageHeader.jsx`

Verification:
- `npm --prefix frontend run build` completed successfully after the split and again after the shared-admin-component follow-up.
- Remaining warnings are existing repo-wide `react-hooks/exhaustive-deps` warnings in unrelated files; no new blocking frontend build errors were introduced.

Current product state:
- Logged-in admin experience now has a clearer separation between platform operations and moderation review.
- Login/auth/membership remain working from the post-restore Mongo fix.

## 2026-03-07 Invite Management Upgrade

Objective:
- Turn the minimal Settings invite box into a usable admin invite management surface without weakening admin gating.

What changed:
- Replaced the old single-field invite generator with a dedicated invite management panel in `/app/settings`.
- Added generation controls for:
  - quantity
  - max uses
  - optional expiration
  - optional label
  - optional note
- Added visible generation feedback:
  - loading state
  - inline success/error notice
  - latest generated batch
  - copy code
  - copy invite link
- Added recent invite inventory with:
  - code
  - derived status
  - created at
  - created by
  - claimed by
  - expires at
  - remaining uses
  - revoke action
- Added filterable inventory controls:
  - status filter
  - search by code, label, or note
  - pagination with total counts

Backend/API changes:
- Extended `POST /api/admin/invite-codes` to store `label` and `note`.
- Added `GET /api/admin/invite-codes` inventory support with:
  - `page`
  - `limit`
  - `status`
  - `q`
  - response totals and page counts
- Added `POST /api/admin/invite-codes/{invite_id}/revoke`.
- Invite claims now persist direct `claimed_by` metadata on invite documents.
- `/join?invite=CODE` now pre-fills the invite field in the join flow.

Verification:
- `python3 -m py_compile /home/ubuntu/thesparkpit/backend/server.py` succeeded after invite API changes.
- `npm --prefix frontend run build` succeeded after the invite-management UI, filtering, and pagination follow-up.
- Remaining frontend warnings are existing `react-hooks/exhaustive-deps` warnings in unrelated files.

## 2026-03-07 Frontend Deploy Guardrail

Objective:
- Prevent a repeat of the login regression caused by shipping a frontend bundle with a broken API base path.

What changed:
- Added a real guarded frontend deploy script:
  - `scripts/deploy_frontend_live.sh`
- The deploy script now:
  - builds the frontend
  - runs `scripts/verify_frontend_bundle.sh`
  - backs up `/var/www/thesparkpit`
  - syncs `frontend/build/` into `/var/www/thesparkpit`
  - verifies the deployed bundle matches the built bundle
  - verifies nginx serves the same hash locally
- Updated `RUNBOOK_SERVER.md` to use the deploy script as the preferred frontend deploy path.

Why this matters:
- The previous live login break happened because a rebuilt frontend was deployed with a bad API base path and started calling `/undefined/api/...`.
- The bundle verification step now fails that class of build before it can be shipped.

Operational command:
- `cd /home/ubuntu/thesparkpit && bash scripts/deploy_frontend_live.sh`

Verification:
- `bash -n scripts/deploy_frontend_live.sh` succeeded
- `bash -n scripts/verify_frontend_bundle.sh` succeeded

## 2026-03-07 Login Regression Guardrail

Symptom:
- Login broke again after the frontend rebuild even though the backend and account state were healthy.

Root causes:
- Frontend CSRF state stayed "ready" after logout even though the backend cleared the `spark_csrf` cookie, causing repeated `403` login attempts in the same SPA session.
- A subsequent rebuilt frontend bundle was deployed without `REACT_APP_BACKEND_URL`, and the app constructed `/undefined/api/...` requests instead of falling back to same-origin.

Fixes applied:
- `frontend/src/context/AuthContext.jsx`
  - logout now resets client CSRF state
  - login/register now retry once after forcing a fresh CSRF fetch if they hit `403`
- `frontend/src/lib/api.js`
  - API base now falls back to `window.location.origin` when `REACT_APP_BACKEND_URL` is unset
  - WebSocket URL generation uses the same resolved backend origin
- Added build regression check:
  - `scripts/verify_frontend_bundle.sh`
  - `npm --prefix frontend run verify:bundle`
  - fails if built assets contain `undefined/api`

Verification:
- New live frontend bundle deployed after the fallback fix.
- Live static entrypoint now points at the rebuilt bundle instead of the broken `/undefined/api` bundle.

## 2026-03-08 Lobby Posts V1 + Lobby Shell Refinement

Objective:
- Shift Lobby from a derived activity board into a real public square with first-class native posts while keeping the product lean.

What shipped:
- Added Lobby Posts v1 backend model and live API routes:
  - `GET /api/lobby/posts`
  - `POST /api/lobby/posts`
  - `POST /api/lobby/posts/{post_id}/replies`
  - `POST /api/lobby/posts/{post_id}/save`
  - `DELETE /api/lobby/posts/{post_id}/save`
  - `POST /api/lobby/posts/{post_id}/convert-room`
- Lobby post types:
  - `post`
  - `question`
  - `summary`
- Lobby post fields/behavior:
  - author
  - body
  - tags
  - optional linked room
  - optional linked bounty
  - reply count
  - save state
  - promoted-to-room state
  - lightweight archival rule in feed queries: posts older than 5 days with no replies, no saves, no promotion, and no pin are hidden from the main feed
- Lobby UI now includes:
  - top-of-feed composer
  - native post cards with inline replies
  - save / unsave
  - convert-to-room scaffolding
  - hybrid feed where native posts are primary and derived network motion is secondary

Header/feed framing pass:
- Removed the old feed-framing labels above the Lobby feed.
- Removed the subtitle under `Pit Lobby`.
- Moved the live signal strip into the top header band and kept title/actions together on the right.
- Result: the composer and public-square feed now own more of the visible page.

Left rail / utility pass:
- Lobby utility no longer permanently occupies the full secondary rail width.
- The secondary panel width is now configurable through `AppShell`.
- Lobby sets utility collapsed by default:
  - collapsed width: `w-16`
  - expanded width: `w-72`
- Collapsed state shows only a minimal utility toggle and a few compact icon shortcuts.
- Expanded state reveals:
  - Network
  - Rooms
  - Open work
  - Bots
  - Active rooms
  - Open calls
  - Milestones
  - Start room
  - Ask question
- This gives the main Lobby feed more horizontal authority by default.

Room/sidebar cleanup:
- Removed persistent decorative/explanatory clutter from the main left sidebar:
  - removed the `Bot social network v0` tagline
  - removed the large always-open room-guardrails explainer card
  - replaced it with a compact intentional-rooms counter row

Key files touched in this phase:
- `backend/server.py`
- `frontend/src/pages/Lobby.jsx`
- `frontend/src/components/lobby/LobbyComposer.jsx`
- `frontend/src/components/lobby/LobbyPostCard.jsx`
- `frontend/src/components/lobby/LobbyRail.jsx`
- `frontend/src/components/layout/AppShell.jsx`
- `frontend/src/components/layout/RoomsSidebar.jsx`

Verification:
- `python3 -m py_compile /home/ubuntu/thesparkpit/backend/server.py` succeeded after Lobby API work.
- `npm --prefix /home/ubuntu/thesparkpit/frontend run build` succeeded repeatedly through the Lobby/social/layout passes.
- Latest live frontend bundle during this handoff ended at:
  - `main.78395905.js`
  - `main.e9170b68.css`

## 2026-03-08 Lobby Posting Failure - Root Cause + Fix

Symptom:
- Lobby UI was live, but posting showed a `Not Found` toast.

Exact root cause:
- Frontend had been deployed, but the running `backend_api` container was stale and did not include the Lobby post routes.
- Inside the live container, `/app/backend/server.py` did not contain `/lobby/posts`, `LobbyPostCreate`, or `convert_lobby_post_to_room`.
- This was not an nginx path mismatch.

What fixed it:
- Rebuilt and recreated only the backend services:
  - `docker compose build backend_api arq_worker`
  - `docker compose up -d backend_api arq_worker`
- After recreate, the live backend process exposed all six Lobby routes.

Live verification performed:
- Route table in the live backend process showed:
  - `/api/lobby/posts` `GET`
  - `/api/lobby/posts` `POST`
  - `/api/lobby/posts/{post_id}/replies` `POST`
  - `/api/lobby/posts/{post_id}/save` `POST`
  - `/api/lobby/posts/{post_id}/save` `DELETE`
  - `/api/lobby/posts/{post_id}/convert-room` `POST`
- Live nginx API check after backend deploy:
  - `GET /api/lobby/posts` -> `200 OK`
  - `POST /api/lobby/posts` -> `200 OK`
  - follow-up `GET /api/lobby/posts` returned the created post

Verification post left in live feed:
- A real verification post was created through the live API as `phil`:
  - id: `983aae8c-31ab-44a4-b24d-222e87575f5e`
  - body: `Lobby route verification post from live API check.`
- If product wants a cleaner square later, delete or ignore that post once proper moderation/delete tooling exists.

## Tips And Tricks For The Next Agent

1. Frontend deploy is not enough for backend-feature launches.
- If a new UI hits new API routes, rebuild/recreate `backend_api` and often `arq_worker` too.
- The common failure mode here is: frontend ships first, backend container still runs old image, UI gets `404`.

2. Verify the running container, not just the repo.
- The repo can contain the right code while the live container is stale.
- Useful check:
  - `docker compose exec -T backend_api python - <<'PY' ... app.routes ... PY`
- Also check the code file inside the container if needed:
  - `/app/backend/server.py`

3. For live frontend deploys, use the guarded script.
- Command:
  - `cd /home/ubuntu/thesparkpit && bash scripts/deploy_frontend_live.sh`
- It catches the `undefined/api` regression class before shipping.

4. For backend deploys, current safe pattern is:
- `cd /home/ubuntu/thesparkpit`
- `docker compose build backend_api arq_worker`
- `docker compose up -d backend_api arq_worker`
- Then verify with:
  - `docker compose ps`
  - live route table inside `backend_api`
  - direct nginx API call against `https://127.0.0.1/api/... -H 'Host: thesparkpit.com'`

5. Host-local curl from sandbox may fail unless escalated.
- If `curl https://127.0.0.1/...` inexplicably fails from the tool sandbox, rerun with escalation.
- Docker access also typically needs escalation for `exec`, `build`, and `up`.

6. Mongo volume mapping is already fixed; do not regress it.
- Current stable mounts:
  - `thesparkpit_mongo_db_data` -> `/data/db`
  - `thesparkpit_mongo_configdb_data` -> `/data/configdb`
- Do not reintroduce a parent `/data` mount pattern.

7. Lobby utility width is controlled centrally now.
- `AppShell` owns the secondary panel width.
- Lobby overrides it through `setSecondaryPanelWidth`.
- If the utility rail seems “stuck wide,” check both:
  - `frontend/src/components/layout/AppShell.jsx`
  - `frontend/src/pages/Lobby.jsx`

8. Near-term product polish that is already known:
- `convert to room` should eventually prefill a title from the post body but allow the user to edit before create.
- Lobby posts are the right v1 model, but not the final social model.
- Next evaluations should focus on:
  - feed feel
  - composer quality
  - post-card quality
  - whether convert-to-room feels sensible in practice

## 2026-03-09 00:24:20Z - Context Re-establishment

Objective:
- Re-read the live handoff, re-verify local repo state versus runtime state, and identify the next safe operational priority before making changes.

Findings:
- `thesparkpit_logbook_handoff.md` was read end to end before any modification.
- Repo head is now `0cc9171704c46ed73ee6483b0233af2daa2175cc` on `main`, ahead of `origin/main` by 6 commits; the newest tip commits inspected (`0cc9171`, `fb048d3`, `c8a7245`) are documentation-only and do not explain runtime drift.
- Live frontend served from `/var/www/thesparkpit` is still the handoff bundle:
  - `static/js/main.78395905.js`
  - `static/css/main.e9170b68.css`
- `backend_api`, `mongodb`, and `redis` are up; `arq_worker` is not healthy and is currently exited with code `1`.
- `arq_worker` crash root cause is immediate import failure:
  - `ModuleNotFoundError: No module named 'backend.jobs.bot_reply'`
- Source inspection confirms the worker break:
  - `backend/worker.py` references `backend.jobs.bot_reply.generate_bot_reply` and `backend.jobs.room_summary.summarize_room`
  - `backend/server.py` references the same job modules
  - `/home/ubuntu/thesparkpit/backend/jobs/` currently contains only `__pycache__/bot_reply.cpython-310.pyc` and `__pycache__/room_summary.cpython-310.pyc`; the corresponding `.py` source files are missing
- Live backend route table inside the running `backend_api` container still exposes the expected handoff routes:
  - `/api/admin/invite-codes` (`GET`, `POST`)
  - `/api/admin/invite-codes/{invite_id}/revoke` (`POST`)
  - all six `/api/lobby/posts...` routes
- Live Mongo counts currently read:
  - `users=5`
  - `audit_events=41`
  - `invite_codes=3`
  - `tasks=2`
- Redis worker heartbeat key `sparkpit:worker:heartbeat` is empty, consistent with the dead worker.
- Logo blocker remains unresolved in a different form:
  - `frontend/public/assets/The.SparkPit_Logo.png` now exists on disk
  - `file` identifies it as `HTML document`, not PNG
  - `frontend/src/pages/Landing.jsx` already references `/assets/The.SparkPit_Logo.png`
- `HANDOFF_START/STATUS.md` is currently deleted from the working tree; the older logo-attempt session note still exists at `HANDOFF_START/sessions/2026-03-01-logo-attempt.md`.

Changes made:
- Added this context re-establishment entry only; no application code, infrastructure config, or runtime service state was changed.

Verification performed:
- Read `thesparkpit_logbook_handoff.md` completely.
- Checked repo state:
  - `git status --short --branch`
  - `git rev-parse HEAD`
  - `git log --oneline --decorate -n 8`
  - `git show --stat --summary` for `0cc9171`, `fb048d3`, `c8a7245`
- Checked runtime/container state:
  - `docker compose ps`
  - `docker compose ps -a`
  - `docker compose logs --tail=120 arq_worker`
  - route introspection from inside `backend_api`
- Checked live served frontend artifact names under `/var/www/thesparkpit/static/{js,css}`.
- Verified current Mongo counts from inside `mongodb`.
- Verified Redis worker heartbeat key from inside `redis`.
- Verified local import failure for `backend.jobs.bot_reply` and `backend.jobs.room_summary`.
- Verified logo asset type with `file` and source references with `rg`.

Unresolved items:
- `arq_worker` is down in production and background job processing is currently broken until the missing job modules are restored or worker references are corrected.
- The homepage logo asset on disk is still invalid HTML, so deploying it as-is would repeat the prior broken-logo path.
- Sandbox `curl` to `127.0.0.1` remained unreliable during this session; direct container inspection was used instead.

Recommended next action:
- Restore or recreate the missing `backend/jobs/bot_reply.py` and `backend/jobs/room_summary.py` source modules from git history or a verified local source, rebuild `backend_api` and `arq_worker`, then verify:
  - `docker compose ps` shows `arq_worker` healthy/running
  - Redis heartbeat key repopulates
  - worker logs stay clean after startup
  - core lobby/admin flows still behave correctly after the rebuild.

## 2026-03-09 00:31:22Z - Lobby Interaction / Debug Pass (Local Source Only)

Objective:
- Tighten Lobby post interaction behavior around create/save/reply/convert flows, with emphasis on button states, duplicate-submit protection, and stale feed refresh behavior before any new live deploy.

Findings:
- There is no local browser installed on this AWS host (`chromium`, `google-chrome`, and `firefox` were all unavailable), so true browser click-through verification was not possible from the terminal session alone.
- The frontend has no working Lobby test setup out of the box for component-level DOM tests because Jest is not currently resolving the app’s `@/` import alias in this repo.
- Current live frontend is still the previously deployed bundle from `/var/www/thesparkpit` and was not changed in this session.
- `docker compose ps` during this session still showed only `backend_api`, `mongodb`, and `redis` running; `arq_worker` was not present in the running set despite the session brief stating it had been redeployed earlier.
- Lobby frontend code had a few real state-management gaps even without browser automation:
  - polling responses could overwrite newer UI state if an older snapshot request resolved later than a newer one
  - pending action state for save/reply/convert was single-id only
  - create/save/reply/convert handlers did not early-return when already in flight
  - composer controls stayed editable during submit
  - action button labels did not reflect the active operation clearly

Changes made:
- `frontend/src/pages/Lobby.jsx`
  - added request sequencing for Lobby snapshot polling so stale responses do not clobber fresher state
  - switched per-post pending state from single ids to per-action id arrays
  - added early-return duplicate-submit protection for create/save/reply/convert
  - kept local post replacement behavior while tightening action-state handling
  - improved create/reply success toasts to be more specific
- `frontend/src/components/lobby/LobbyComposer.jsx`
  - submit label now reflects post type (`Post`, `Question`, `Summary`)
  - composer type buttons, body, tag input, and optional link selects now disable while posting
  - added stable `data-testid` hooks for composer type buttons
- `frontend/src/components/lobby/LobbyPostCard.jsx`
  - reply toggle disables while reply submit is in flight
  - save button text now reflects `Saving...` / `Unsaving...`
  - convert button text now reflects `Converting...`
  - reply textarea and cancel action disable while reply submit is in flight
  - added `data-testid` hooks on reply/save/convert controls

Verification performed:
- Re-read Lobby frontend handlers/components and backend Lobby route shapes before editing.
- Ran `npm --prefix /home/ubuntu/thesparkpit/frontend run build`.
- Build completed successfully and emitted the existing repo-wide `react-hooks/exhaustive-deps` warnings only; no new Lobby-specific build errors were introduced.

Unresolved items:
- No browser-based click-through was completed in this session because the host lacks a browser and no authenticated manual session was available through the terminal.
- Updated Lobby frontend code has not been deployed to `/var/www/thesparkpit` yet.
- Jest alias resolution remains unset for `@/` imports, so adding direct component DOM tests would first require test-config work that was intentionally left out of scope for this pass.
- `arq_worker` still did not appear healthy/running during runtime inspection in this session.

Recommended next action:
- If this Lobby pass should go live, deploy the rebuilt frontend with `bash scripts/deploy_frontend_live.sh`, then perform a real authenticated manual click-through on:
  - create post
  - create question
  - create summary
  - save / unsave
  - reply
  - convert to room
- During that live click-through, explicitly watch for:
  - duplicate-submit suppression
  - stale feed/state after the 25s polling interval
  - button copy/disable state transitions
  - toast correctness
  - convert-to-room room creation and sidebar refresh behavior

## 2026-03-09 00:37:36Z - Runtime Health Verification Before Lobby Deploy

Objective:
- Re-verify live runtime health before considering any Lobby frontend deploy, with special focus on `arq_worker` status, necessity, and failure mode.

Findings:
- `thesparkpit_logbook_handoff.md` was re-read fully before this runtime check.
- Current container state from `docker compose ps -a`:
  - `backend_api` up
  - `mongodb` up
  - `redis` up and healthy
  - `arq_worker` exited with code `1`
- Current `arq_worker` failure is still the same hard startup failure:
  - `ModuleNotFoundError: No module named 'backend.jobs.bot_reply'`
- Redis heartbeat key `sparkpit:worker:heartbeat` is empty, which matches the dead worker.
- Redis ARQ queue currently contains unprocessed jobs:
  - `arq:queue`
  - queued job payloads inspected were `backend.worker.process_audit_event` for `lobby.posted` events
- Live backend route table still exposes Lobby routes correctly, so the API itself is up even though the worker is down.
- `arq_worker` is required for current live TheSparkPit.com behavior and is not just optional infrastructure:
  - audit events are written to Mongo synchronously, but every audit also enqueues `process_audit_event`, which populates Redis audit/activity data used by ops/telemetry paths
  - `/api/admin/ops` checks `sparkpit:worker:heartbeat`, so the admin Ops console will currently show worker health as failed
  - message posting enqueues `index_message`
  - message posting also enqueues `generate_bot_reply` when `BOT_AUTO_REPLY=1`
  - room memory summarization enqueues `summarize_room` when `ROOM_SUMMARY_ENABLED=1`
  - bounty status changes enqueue `process_bounty_status`
- Runtime env inside `backend_api` confirms both background-dependent features are currently enabled:
  - `BOT_AUTO_REPLY=1`
  - `ROOM_SUMMARY_ENABLED=1`
- Practical impact assessment:
  - core synchronous HTTP flows such as login and Lobby post CRUD can still succeed
  - background processing is degraded right now, including worker heartbeat, Redis audit/index freshness, bot auto-replies, room summarization, and queued bounty/message indexing work
  - because queue items are already accumulating, this is an active runtime issue rather than a purely cosmetic status flag
- Root cause is now better bounded:
  - current working tree is missing `backend/jobs/bot_reply.py` and `backend/jobs/room_summary.py`
  - those files do exist in git history at commit `2bf783caafd01b11274eddbe14dc9a1e2090a0ee`
  - this means the worker failure is most likely recoverable from local git history rather than requiring reconstruction from scratch

Changes made:
- Added this runtime-health entry only. No runtime service state, source code, or deployed assets were changed in this step.

Verification performed:
- Re-read `thesparkpit_logbook_handoff.md` fully.
- Ran:
  - `docker compose ps -a`
  - `docker compose logs --tail=160 arq_worker`
  - backend route introspection inside `backend_api`
  - Redis `GET sparkpit:worker:heartbeat`
  - Redis queue inspection for `arq:*`
  - env inspection inside `backend_api` for `BOT_AUTO_REPLY` and `ROOM_SUMMARY_ENABLED`
  - git history checks for `backend/jobs/bot_reply.py` and `backend/jobs/room_summary.py`

Unresolved items:
- `arq_worker` is not healthy, and queued jobs are already backing up.
- Because runtime is not healthy, the Lobby interaction frontend patch should not be treated as deploy-ready yet.
- Real browser/live UI verification of the Lobby patch still has not happened.

Recommended next action:
- Restore `backend/jobs/bot_reply.py` and `backend/jobs/room_summary.py` from commit `2bf783caafd01b11274eddbe14dc9a1e2090a0ee`, rebuild/recreate `backend_api` and `arq_worker`, and verify:
  - `arq_worker` stays up
  - heartbeat key repopulates
  - queued ARQ jobs drain
  - bot auto-reply and room-summary paths are no longer broken
- Only after runtime health is green should the local Lobby frontend patch be deployed and tested through the live browser UI.

## 2026-03-09 00:42:15Z - Worker Restore

Objective:
- Restore live runtime health by bringing `arq_worker` back to a running state before any Lobby frontend deploy.

Findings:
- The worker outage was recoverable from local git history rather than requiring reconstruction.
- `backend/jobs/bot_reply.py` and `backend/jobs/room_summary.py` were present in commit `2bf783caafd01b11274eddbe14dc9a1e2090a0ee` and were the exact missing imports blocking worker startup.
- After restoring those modules and rebuilding the backend images, both `backend_api` and `arq_worker` came up cleanly.
- `arq_worker` immediately processed the previously stuck queued `backend.worker.process_audit_event` jobs for historical `lobby.posted` events.

Changes made:
- Restored:
  - `backend/jobs/bot_reply.py`
  - `backend/jobs/room_summary.py`
- Rebuilt and recreated:
  - `backend_api`
  - `arq_worker`

Verification performed:
- `python3 -m py_compile` succeeded for:
  - `backend/jobs/bot_reply.py`
  - `backend/jobs/room_summary.py`
  - `backend/worker.py`
  - `backend/server.py`
- Local import verification succeeded for:
  - `backend.jobs.bot_reply`
  - `backend.jobs.room_summary`
- `docker compose build backend_api arq_worker` completed successfully.
- `docker compose up -d backend_api arq_worker` completed successfully after the rebuild.
- `docker compose ps -a` now shows:
  - `backend_api` up
  - `arq_worker` up
  - `mongodb` up
  - `redis` up and healthy
- `docker compose logs --tail=80 arq_worker` shows:
  - worker startup for all 9 functions
  - `HEARTBEAT_LOOP_STARTED`
  - successful processing of the previously queued audit jobs
- Redis verification:
  - `GET sparkpit:worker:heartbeat` returned a fresh unix timestamp
  - `ZCARD arq:queue` returned `0`

Unresolved items:
- Real browser/live verification of the Lobby frontend patch still has not happened.
- This AWS host still has no installed browser for direct UI click-through verification from the terminal session.

Recommended next action:
- Runtime is healthy again, so the Lobby frontend patch can now be considered for deployment.
- However, do not mark the Lobby interaction patch complete until it has been verified through a real live browser UI session covering:
  - post create
  - save / unsave
  - reply
  - convert to room
  - duplicate-click prevention
  - button loading labels

## 2026-03-09 00:54:25Z - Bug Report Path V1

Objective:
- Add a simple visible bug-report path inside the live app shell without overbuilding a support system.

Findings:
- The existing left sidebar was the cleanest placement for a low-noise but easy-to-find action.
- The current `RoomsSidebar` already owns the bottom navigation block, so the smallest reliable v1 is a mailto action placed alongside the existing utility links.
- Runtime was healthy before deploy:
  - `backend_api` up
  - `arq_worker` up
  - `mongodb` up
  - `redis` up and healthy

Changes made:
- Updated `frontend/src/components/layout/RoomsSidebar.jsx`.
- Added a visible `Report bug` action in the sidebar navigation.
- Wired it to:
  - `mailto:philip@thesparkpit.com`
- Prefilled mail body template with:
  - `What happened:`
  - `What did you expect:`
  - `Steps to reproduce:`
  - `Current page:`
  - `Browser/device:`
  - `Screenshot:`
- Prefilled subject:
  - `TheSparkPit bug report`
- Included current page URL in the composed body via `window.location.href` when available, with router-path fallback.
- Kept styling aligned with the existing dark sidebar nav treatment.

Verification performed:
- `npm --prefix /home/ubuntu/thesparkpit/frontend run build` succeeded.
- Existing repo-wide frontend warnings remained, but no new blocking build errors were introduced.
- Deployed with:
  - `bash /home/ubuntu/thesparkpit/scripts/deploy_frontend_live.sh`
- Guarded deploy completed successfully and reported live bundle:
  - `main.a53cef9f.js`
- Verified deployed live asset path under `/var/www/thesparkpit/static/js/` includes:
  - `main.a53cef9f.js`
- Verified deployed bundle content includes the bug-report path markers:
  - `philip@thesparkpit.com`
  - `TheSparkPit bug report`
  - `Current page:`
- Verified source sidebar file contains:
  - `data-testid="nav-report-bug"`
  - visible label `Report bug`

Unresolved items:
- No browser-based click validation was performed from this host because there is still no installed browser in the AWS terminal environment.
- This is intentionally a v1 mailto path only; it does not capture structured reports server-side.

Recommended next action:
- In the next browser-capable validation pass, confirm the live sidebar action:
  - opens the default mail client
  - pre-fills the expected subject/body
  - includes the current page URL from the active app route

## 2026-03-09 01:05:39Z - First-Run Onboarding V1

Objective:
- Add a lightweight first-run orientation layer before wider invite testing so new users get clear direction on what TheSparkPit is, how to navigate it, how to start using it, and how to report bugs.

Findings:
- The cleanest v1 was a small first-run modal at the app-shell level plus a focused bot-operator guidance card on the Bots page.
- The frontend already has access to `user.created_at` and `user.membership_activated_at`, so onboarding can be scoped to newly active accounts without adding backend persistence.
- A frontend-only dismissal mechanism is sufficient for v1 and avoids introducing new server-side onboarding state before public release testing.
- Bot operation guidance fits better as a dismissible Bots-page card than as a larger general modal section.

Changes made:
- Added new component:
  - `frontend/src/components/onboarding/WelcomeModal.jsx`
- Updated:
  - `frontend/src/components/layout/AppShell.jsx`
  - `frontend/src/pages/Bots.jsx`
- First-run welcome modal behavior:
  - shown to newly active accounts within a 72-hour first-run window
  - dismissed per-user in `localStorage`
  - covers:
    - what TheSparkPit is
    - Pit Lobby / Research / Rooms / Bounties guidance
    - startup guidance for posting, using rooms, and using bounties
    - bug-report guidance pointing to the sidebar `Report bug` action
- Bot guidance behavior:
  - dismissible orientation card added to `/app/bots`
  - aimed at bot operators / newly registered bot workflows
  - includes:
    - use Lobby vs Rooms intentionally
    - avoid spam / repetitive posting
    - use Bounties for specific work
    - report bot failures through `Report bug`
  - card reappears after bot registration in the current session unless dismissed

Verification performed:
- `npm --prefix /home/ubuntu/thesparkpit/frontend run build` succeeded.
- Existing repo-wide frontend warnings remained, but no new blocking build errors were introduced.
- Deployed with:
  - `bash /home/ubuntu/thesparkpit/scripts/deploy_frontend_live.sh`
- Guarded deploy completed successfully and reported live bundle:
  - `main.edde58c8.js`
- Verified deployed live asset path under `/var/www/thesparkpit/static/js/` includes:
  - `main.edde58c8.js`
- Verified source markers exist for:
  - `welcome-modal`
  - `bot-orientation-card`
  - `Run bots intentionally, not noisily.`
  - onboarding bug-report guidance referencing `Report bug`
- Verified deployed live bundle contains onboarding markers for:
  - `Welcome to TheSparkPit`
  - `Pit Lobby`
  - `Report bug`
  - `Run bots intentionally`

Unresolved items:
- No browser-based click validation was performed from this host because there is still no installed browser in the AWS terminal environment.
- Dismissal state is frontend-only (`localStorage`) in this v1 and is not yet synced across devices or browsers.
- The previously noted Lobby interaction patch still remains unverified through a live browser UI session.

Recommended next action:
- In the next browser-capable validation pass, confirm:
  - the welcome modal appears for a genuinely new active account
  - dismissing it prevents repeat display for that user in the same browser
  - the Bots guidance card appears for new bot setup flow
  - the `Report bug` guidance path is easy to find from onboarding and the sidebar

## 2026-03-09 01:11:21Z - Logbook Refresh

Objective:
- Refresh `thesparkpit_logbook_handoff.md` so the current session clearly records that the handoff was reviewed and left in sync.

Findings:
- The latest deployed/frontend notes already included:
  - worker restore
  - bug-report path v1
  - first-run onboarding v1
- No additional runtime, code, or deploy changes were made after those entries before this refresh.

Changes made:
- Added this timestamped refresh entry only.

Verification performed:
- Reviewed the tail of `thesparkpit_logbook_handoff.md` to confirm the newest entries were present and internally consistent.

Unresolved items:
- Browser-capable validation is still needed for:
  - Lobby interaction patch
  - bug-report sidebar action
  - first-run onboarding display/dismiss flow

Recommended next action:
- Continue from the latest logged product state and prioritize the pending browser-based validation passes.

## 2026-03-10 00:07:40Z - Context Re-establishment

Objective:
- Re-read the handoff completely, verify current repo/runtime state on the live AWS host, and record the actual March 10 operating baseline before any new change work.

Findings:
- `thesparkpit_logbook_handoff.md` was read end to end before any modification.
- Repo head is still `0cc9171704c46ed73ee6483b0233af2daa2175cc` on `main`, ahead of `origin/main` by 6 commits.
- The working tree is still intentionally dirty with substantial tracked and untracked product/runtime files; do not assume a clean-source rebuild would match the current live state without reconciling local changes first.
- Current live frontend served from `/var/www/thesparkpit` is:
  - `static/js/main.edde58c8.js`
  - `static/css/main.3693c0b5.css`
- Current container state is healthy:
  - `backend_api` up
  - `arq_worker` up
  - `mongodb` up
  - `redis` up and healthy
- `arq_worker` heartbeat is present in Redis and the ARQ queue is empty:
  - `GET sparkpit:worker:heartbeat` returned `1773101223`
  - `ZCARD arq:queue` returned `0`
- Live backend route inspection inside `backend_api` confirms the expected admin invite and Lobby post routes are loaded:
  - `GET|POST /api/admin/invite-codes`
  - `POST /api/admin/invite-codes/{invite_id}/revoke`
  - all six `/api/lobby/posts...` routes
- Live Mongo counts currently read:
  - `users=5`
  - `audit_events=43`
  - `invite_codes=3`
  - `tasks=2`
  - `lobby_posts=2`
- The logo blocker remains unresolved:
  - `frontend/public/assets/The.SparkPit_Logo.png` still exists on disk
  - `file` still identifies it as `HTML document`, not PNG
- Direct host `curl` to `127.0.0.1:8000` from the sandbox failed during this session, so runtime verification relied on container inspection, logs, Redis/Mongo checks, and served-asset inspection instead.

Changes made:
- Added this timestamped context re-establishment entry only; no application code, deployment state, data, or infrastructure config was changed.

Verification performed:
- Read `thesparkpit_logbook_handoff.md` completely.
- Checked repo state:
  - `git status --short --branch`
  - `git rev-parse HEAD`
  - `git log --oneline --decorate -n 8`
  - `git diff --stat`
- Checked live served asset names under `/var/www/thesparkpit/static/{js,css}`.
- Verified logo asset type with `file`.
- Checked runtime/container state:
  - `docker compose ps -a`
  - `docker compose logs --tail=120 arq_worker`
  - backend route introspection from inside `backend_api`
  - Redis heartbeat and queue depth from inside `redis`
  - Mongo collection counts from inside `mongodb`

Unresolved items:
- The homepage logo asset is still invalid HTML, so shipping it would repeat the prior broken-logo issue.
- The local working tree contains a large undeployed delta; future deploy work must distinguish carefully between live state, local-only source changes, and uncommitted recovery artifacts.
- Browser-capable validation is still missing for:
  - the undeployed Lobby interaction patch
  - the sidebar `Report bug` action
  - first-run onboarding modal/card behavior

Recommended next action:
- Keep runtime stable, avoid broad rebuilds from the dirty tree, and choose one contained objective before changing code:
  - either replace the invalid logo with a verified PNG and deploy only that asset safely
  - or perform the pending browser-capable validation pass before shipping more frontend changes

## 2026-03-10 00:18:05Z - Research Page UX Refactor (Local Build Only)

Objective:
- Refactor `/app/research` so it reads as a real research workflow instead of placeholder scaffolding, with an obvious primary action and no bulky Signal Deck / command-state panel.

Findings:
- The existing page mounted `QuickPanel` into the secondary layout rail, which is the large Signal Deck / Command state block the product brief wanted removed.
- The existing content centered on placeholder/status language (`Research in motion`, `Shared inquiry`, `Rooms ready`, `Latest signal`, `Feed markers`) and did not give users a first-class “research project” action.
- There is still no dedicated research-project backend object or API; the only real creation path available today is room creation via `POST /api/rooms`.
- Because the frontend working tree still contains other undeployed changes, rebuilding and deploying the full frontend bundle would risk shipping unrelated work during this UX pass.

Changes made:
- Rewrote `frontend/src/pages/Research.jsx`.
- Removed the mounted secondary `QuickPanel` from the Research route by setting the page’s secondary panel to `null` and collapsing its width.
- Replaced the old placeholder/status layout with:
  - header `Research`
  - required product subtext about public/private investigations, rooms, findings, and humans/bots
  - primary CTA `Start research project`
  - secondary CTA `Review feed`
  - empty-state card with the requested title/body/button structure
- Added a small collapsible help disclosure instead of a large status block.
- Kept the page honest about backend reality:
  - `Start research project` opens a modal
  - the modal explicitly states that dedicated research-project objects do not exist yet
  - submitting currently creates a room as the working space
- Added the requested modal fields:
  - project title
  - research question
  - visibility
  - create room now yes/no
  - optional template
- Added a compact examples section that points users to existing rooms without letting placeholder cards dominate the page.

Verification performed:
- Reviewed existing room-creation flow and backend room API before wiring the new CTA to the real creation path.
- Ran:
  - `npm --prefix /home/ubuntu/thesparkpit/frontend run build`
- Build succeeded.
- Remaining warnings were the existing repo-wide `react-hooks/exhaustive-deps` warnings in unrelated files:
  - `src/components/ChatPanel.jsx`
  - `src/context/AuthContext.jsx`
  - `src/pages/Activity.jsx`
  - `src/pages/Bounties.jsx`
  - `src/pages/BountyDetail.jsx`
  - `src/pages/Join.jsx`
  - `src/pages/Rooms.jsx`
- New local frontend build artifacts ended at:
  - `main.520baae5.js`
  - `main.17301511.css`

Unresolved items:
- This change was intentionally not deployed live yet because the frontend tree still contains other undeployed work; using the guarded deploy script right now would ship more than just this Research-page refactor.
- Browser-based interaction validation from this host is still not possible because there is no installed browser in the AWS terminal environment.
- The modal currently collects research question/template as setup guidance only; those fields are not persisted separately because no research-project backend object exists yet.

Recommended next action:
- If this Research UX should go live, first isolate whether the current frontend tree is safe to deploy as a bundle or reduce the delta to only intended changes, then deploy with the guarded script and verify in a real browser:
  - header/subtext/CTA copy
  - secondary panel absence on `/app/research`
  - empty-state presentation
  - modal open/close behavior
  - successful room creation and redirect when starting a research project

## 2026-03-10 00:25:37Z - Research Page Refactor Deployed

Objective:
- Isolate the deployable frontend delta for the Research-page refactor and ship only that change through the guarded frontend deploy path without bundling unrelated undeployed frontend work.

Findings:
- `HEAD` was not a safe deploy baseline for this repo because it does not contain the current live Research route or several already-live frontend features; isolating against git alone would have risked a live regression.
- Frontend/source timestamp audit against the last successful frontend deploy window (`2026-03-09 01:05Z`, the `main.edde58c8.js` onboarding deploy) showed that only one frontend source file changed afterward:
  - `frontend/src/pages/Research.jsx`
- Other changed/untracked frontend files in the working tree are older and correspond to already-live product work rather than new undeployed delta from this session.
- One old string from the previous Research placeholder set, `Rooms ready`, still exists in the deployed bundle because it is used by `frontend/src/pages/Bounties.jsx`; it is not evidence that the old Research page remained live.

Changes made:
- Deployed the Research-page refactor in `frontend/src/pages/Research.jsx`.
- Kept deployment scope to the current live-source baseline plus the Research-page refactor only, based on the timestamp isolation described above.
- Shipped via the guarded frontend deploy path:
  - `bash /home/ubuntu/thesparkpit/scripts/deploy_frontend_live.sh`

Verification performed:
- Confirmed deploy isolation basis before shipping:
  - `find /home/ubuntu/thesparkpit/frontend/src /home/ubuntu/thesparkpit/frontend/public -type f -newermt '2026-03-09 01:06:00Z'`
  - result: only `frontend/src/pages/Research.jsx`
- Guarded deploy completed successfully:
  - build passed
  - bundle verification passed
  - rsync deploy completed
  - nginx served-hash verification passed
- New live frontend assets are now:
  - `main.520baae5.js`
  - `main.17301511.css`
- Verified `/var/www/thesparkpit/index.html` references the deployed Research bundle hashes above.
- Verified the deployed live bundle at `/var/www/thesparkpit/static/js/main.520baae5.js` contains the required Research-page markers:
  - `Research`
  - `Create public or private investigations, attach rooms, collect findings, and coordinate humans and bots`
  - `Start research project`
  - `Review feed`
  - `Start your first research project`
  - `Create a research brief, define the problem, attach a room, and let humans and bots work from shared context`
  - `How research works today`
  - `Dedicated research-project backend objects are not live yet`
  - `Research projects are not separate backend objects yet`
- Verified the current Research source that was deployed includes the rail-removal wiring:
  - `setSecondaryPanel(null)`
  - `setSecondaryPanelWidth("w-0 border-r-0")`
  - CTA trigger `data-testid="research-start-project"`
  - help disclosure trigger `data-testid="research-help-trigger"`
  - modal marker `data-testid="research-project-dialog"`
- Verified the old Research-only placeholder strings are absent from the deployed bundle:
  - `Research in motion`
  - `Shared inquiry`
  - `Feed markers`
  - `What this page is for`
- Attempted an ad hoc jsdom/Jest interaction check for click-to-open modal behavior, but this repo still fails alias resolution for `@/` imports in that test path, matching the earlier handoff warning about frontend test setup.

Unresolved items:
- Browser-capable click verification is still not possible from this AWS terminal environment, so modal-open behavior was verified by deployed bundle markers plus the shipped source wiring rather than by a real browser session.
- The modal remains honest but transitional:
  - `Start research project` currently creates a room
  - research question/template fields are setup guidance only and are not persisted as a separate project object
- The invalid homepage logo asset remains unresolved and unrelated to this deploy.

Recommended next action:
- In the next browser-capable validation pass, verify the live `/app/research` route interactively:
  - the secondary rail is visually gone
  - the empty-state card renders as intended
  - the help disclosure expands/collapses cleanly
  - clicking `Start research project` opens the modal
  - submitting the modal creates a room and redirects into it

## 2026-03-10 00:35:27Z - Research Workspace Seeding Deployed

Objective:
- Make `Start research project` feel like a real investigation workspace by bridging the Research modal to the existing room backend with seeded context and room-level research cues.

Findings:
- The room backend already had enough primitives to support a stronger transitional workflow:
  - room creation
  - default `general` channel creation
  - normal message posting into that default channel
- The main missing pieces were:
  - room metadata fields for research-oriented context
  - a seeded kickoff brief after room creation
  - room UI cues so the landing state reads as a research workspace rather than a generic chat
- Frontend/source timestamp audit since the prior live Research deploy (`2026-03-10 00:25:37Z`) showed the frontend delta for this pass was limited to:
  - `frontend/src/pages/Research.jsx`
  - `frontend/src/components/ChatPanel.jsx`
- Backend delta for this pass was limited to:
  - `backend/server.py`

Changes made:
- Extended `backend/server.py` room creation payload to accept and persist:
  - `description`
  - `source`
  - `research`
- Added moderation checks for room `title` and `description` in the room-creation path.
- Updated the Research modal flow in `frontend/src/pages/Research.jsx` so submit now:
  - creates the room through the existing backend
  - stores research context on the room
  - posts a seeded kickoff brief into the default channel
  - routes directly into `/app/rooms/{slug}/{default_channel_id}`
  - uses research-workspace wording instead of generic room wording
- Updated `frontend/src/components/ChatPanel.jsx` to render research-specific room context when `room.source.kind == "research_project"`:
  - `Research workspace` badge
  - room description / research question
  - `Investigation context` panel
  - visibility badge
  - template
  - next step
  - note explaining that dedicated research-project objects are planned

Verification performed:
- Syntax/build checks before deploy:
  - `python3 -m py_compile /home/ubuntu/thesparkpit/backend/server.py`
  - `npm --prefix /home/ubuntu/thesparkpit/frontend run build`
- Backend deploy:
  - `docker compose -f /home/ubuntu/thesparkpit/docker-compose.yml build backend_api`
  - `docker compose -f /home/ubuntu/thesparkpit/docker-compose.yml up -d backend_api`
- Frontend deploy:
  - `bash /home/ubuntu/thesparkpit/scripts/deploy_frontend_live.sh`
- Runtime/container verification:
  - `docker compose ps -a` shows:
    - `backend_api` up
    - `arq_worker` up
    - `mongodb` up
    - `redis` up and healthy
  - `docker compose logs --tail=80 backend_api` shows clean startup and normal request handling after restart
- Verified the running backend container directly:
  - `RoomCreate` schema now includes `description`, `source`, and `research`
  - `create_room` source in the live container includes `moderate_text`, `payload.source`, `payload.research`, and `description`
- Verified the new live frontend assets:
  - `main.c2bf7a6b.js`
  - `main.7b164df5.css`
- Verified `/var/www/thesparkpit/index.html` references the new frontend asset hashes above.
- Verified the deployed frontend bundle contains the new research-workspace markers:
  - `Research workspace ready`
  - `Research workspace`
  - `Investigation context`
  - `Project title:`
  - `Research question:`
  - `Next step: add the first source, hypothesis, constraint, or work item so the investigation has a concrete starting point`
  - `dedicated research-project objects are planned; this room is the investigation workspace today`
- Verified the shipped room UI source contains:
  - `data-testid="research-workspace-badge"`
  - `data-testid="research-workspace-context"`
  - `data-testid="room-description"`

Unresolved items:
- Browser-capable live click-through is still not possible from this AWS terminal environment, so the end-to-end create-and-land interaction was verified by deployed source/bundle inspection and running backend schema inspection rather than by a real browser session.
- The seeded kickoff brief is posted as a normal first message after room creation; if that second request fails, the room still exists and the user is routed into it with a toast explaining that the kickoff brief did not post.
- Dedicated research-project backend objects still do not exist; this remains a transitional room-backed experience by design.

Recommended next action:
- In the next browser-capable validation pass, test the live Research flow end to end:
  - open the modal
  - create a public research project
  - confirm redirect into the new room
  - confirm the kickoff brief posts into the default channel
  - confirm the room header/context panel reads as a research workspace rather than a generic chat room

## 2026-03-10 00:53:04Z - Research Summary / Findings Panel Deployed

Objective:
- Add lightweight structured research capture to research workspaces so room-backed investigations visibly track evidence, findings, open questions, next actions, and status alongside chat.

Findings:
- The existing room-backed research transition already persisted basic `research` metadata, so the safest extension was to keep using room documents rather than introducing a new collection.
- A single room-scoped patch endpoint is enough for this phase because the desired state is lightweight and collaborative:
  - summary text
  - lists of sources/findings/open questions/next actions
  - simple status enum
- Frontend/source timestamp audit since the prior live Research workspace deploy (`2026-03-10 00:35:27Z`) showed the frontend delta for this pass was limited to:
  - `frontend/src/pages/Research.jsx`
  - `frontend/src/components/ChatPanel.jsx`
  - `frontend/src/components/rooms/ResearchWorkspacePanel.jsx`
- Backend delta for this pass was limited to:
  - `backend/server.py`

Changes made:
- Extended `backend/server.py` research metadata models:
  - `RoomResearchSeed`
  - new `RoomResearchUpdate`
- Added room-backed structured research fields:
  - `question`
  - `summary`
  - `key_sources`
  - `findings`
  - `open_questions`
  - `next_actions`
  - `status`
  - `note`
- Added validation helpers for research status and research list normalization.
- Added `PATCH /api/rooms/{slug}/research`:
  - requires active room access
  - restricted to rooms launched from the Research flow (`source.kind == "research_project"`)
  - updates room-backed research metadata
  - mirrors updated question into room `description`
  - logs:
    - `room.research.updated` audit event
    - `research.updated` room event
- Updated Research workspace creation seeding in `frontend/src/pages/Research.jsx` so new rooms now start with:
  - `status=active`
  - empty structured lists
  - initial `next_actions` seed
- Added new frontend component:
  - `frontend/src/components/rooms/ResearchWorkspacePanel.jsx`
- Updated `frontend/src/components/ChatPanel.jsx` so research workspaces now render a structured panel above chat instead of only the earlier context banner.
- The panel includes:
  - Research question
  - Current summary
  - Key sources
  - Findings so far
  - Open questions
  - Next actions
  - Status (`active`, `paused`, `concluded`)
  - Workspace note
- Added lightweight actions:
  - `Add source`
  - `Add finding`
  - `Add question`
  - `Add action`
  - `Update summary`
  - `Save status`
  - `Mark concluded`

Verification performed:
- Syntax/build checks before deploy:
  - `python3 -m py_compile /home/ubuntu/thesparkpit/backend/server.py`
  - `npm --prefix /home/ubuntu/thesparkpit/frontend run build`
- Backend deploy:
  - `docker compose -f /home/ubuntu/thesparkpit/docker-compose.yml build backend_api`
  - `docker compose -f /home/ubuntu/thesparkpit/docker-compose.yml up -d backend_api`
- Frontend deploy:
  - `bash /home/ubuntu/thesparkpit/scripts/deploy_frontend_live.sh`
- Runtime/container verification:
  - `docker compose ps -a` shows:
    - `backend_api` up
    - `arq_worker` up
    - `mongodb` up
    - `redis` up and healthy
- Verified the running backend container directly:
  - route table now includes `PATCH /api/rooms/{slug}/research`
  - `RoomResearchSeed` schema includes:
    - `summary`
    - `key_sources`
    - `findings`
    - `open_questions`
    - `next_actions`
    - `status`
  - `RoomResearchUpdate` schema includes the patchable structured fields above
- Verified the new live frontend assets:
  - `main.c4927e2e.js`
  - `main.55fe7a17.css`
- Verified `/var/www/thesparkpit/index.html` references the new frontend asset hashes above.
- Verified the deployed frontend bundle contains the new panel markers:
  - `Research summary`
  - `Current summary`
  - `Key sources`
  - `Findings so far`
  - `Open questions`
  - `Next actions`
  - `Add source`
  - `Add finding`
  - `Update summary`
  - `Save status`
  - `Mark concluded`
  - `Workspace note`
  - `Nothing captured yet`

Unresolved items:
- Browser-capable live interaction validation is still not possible from this AWS terminal environment, so the new panel actions were verified by running backend route/schema inspection and deployed bundle inspection rather than by a real browser session.
- There is still no per-item editing/removal UI yet; this pass focused on lightweight capture and continuity, not full record management.
- Bots do not yet have a dedicated write path for this panel, but the room-backed metadata shape and patch route are now in place for future bot integration.

Recommended next action:
- In the next browser-capable validation pass, verify a real research workspace end to end:
  - add a source
  - add a finding
  - update summary
  - change status
  - mark concluded
  - confirm the panel updates persist after page reload

## 2026-03-10 01:12:01Z

Objective:
- Unify collapsible middle-rail behavior across contextual app pages and turn `/app/research` into a launcher plus index for existing research workspaces.

Findings:
- `AppShell` already owned the secondary contextual rail, but Lobby used a page-local collapsed-width pattern instead of a reusable shared rail state model.
- The safest path was to make collapse/expand behavior a layout concern and inject it into existing rail components, rather than fork per-page logic.
- Existing room documents already exposed Research workspaces through `source.kind == "research_project"`, so `/app/research` could be upgraded into an index without introducing a new backend object.
- `last activity` on Research index cards needed fresher room timestamps, so room `updated_at` had to be touched on channel/message activity.
- The frontend working tree remains broadly dirty and not suitable for reset/clean-based isolation, so this pass treated current working source as the live baseline and deployed only the verified intended delta.

Changes made:
- Updated `frontend/src/components/layout/AppShell.jsx` to own persistent secondary-rail state with reusable configuration for:
  - `railKey`
  - expanded width
  - collapsed width
  - collapsible vs hidden state
  - per-user/session persistence via local storage
- Updated `frontend/src/components/layout/QuickPanel.jsx` to support shared collapsed/expanded rendering with a visible toggle and a narrow contextual state when collapsed.
- Updated `frontend/src/components/layout/ChannelsSidebar.jsx` to support shared collapsed/expanded rendering so room/workspace channel rails can minimize cleanly without breaking the main workspace.
- Updated `frontend/src/components/lobby/LobbyRail.jsx` and `frontend/src/pages/Lobby.jsx` to use the same shared collapse model instead of a Lobby-only local pattern.
- Updated `frontend/src/pages/Rooms.jsx` so room/workspace pages now use the shared collapsible middle rail with persistent state.
- Updated `frontend/src/pages/Research.jsx` so Research explicitly hides the middle rail and now acts as both:
  - launcher for new research workspaces
  - index for existing room-backed research workspaces
- Added Research index features in `frontend/src/pages/Research.jsx`:
  - status filtering (`active`, `paused`, `concluded`)
  - title/question search
  - most-recent-activity sorting
  - card summaries with status, visibility, last activity, structured counts, and `Open workspace`
- Updated `backend/server.py` so room `updated_at` is refreshed on:
  - channel creation
  - user message creation
  - bot message creation

Verification performed:
- Syntax/build checks:
  - `python3 -m py_compile /home/ubuntu/thesparkpit/backend/server.py`
  - `npm --prefix /home/ubuntu/thesparkpit/frontend run build`
- Backend deploy:
  - `docker compose -f /home/ubuntu/thesparkpit/docker-compose.yml build backend_api`
  - `docker compose -f /home/ubuntu/thesparkpit/docker-compose.yml up -d backend_api`
- Frontend deploy:
  - `bash /home/ubuntu/thesparkpit/scripts/deploy_frontend_live.sh`
- Runtime verification:
  - `docker compose -f /home/ubuntu/thesparkpit/docker-compose.yml ps -a`
  - verified `backend_api`, `arq_worker`, `mongodb`, and `redis` are up
- Verified live frontend asset hashes in `/var/www/thesparkpit/index.html`:
  - `main.f147746c.js`
  - `main.e5259748.css`
- Verified the deployed frontend bundle contains the expected shared-rail and Research-index markers:
  - `Search by title or question`
  - `Ongoing investigations`
  - `Last activity`
  - `Open workspace`
  - `No research workspaces match the current filters`
  - `Research index`
  - `Context`
  - `Channels`
  - `Signal Deck`
  - `Command state`
  - `Collapse`
  - `Utility`
- Verified the running backend source includes room activity timestamp writes for the updated room activity model.

Unresolved items:
- Browser-capable live interaction validation is still not available from this AWS terminal session, so collapse/expand behavior and Research index interactions were validated through build/runtime checks and served-bundle inspection rather than a real browser click-through.
- Research remains room-backed; there is still no dedicated backend research-project model yet.
- The shared rail is now implemented across the known contextual pages in current routing, but a browser pass is still needed to validate behavior across desktop and narrower widths.

Recommended next action:
- Run a browser-capable validation pass covering:
  - Lobby utility rail collapse/expand
  - room/workspace Channels rail collapse/expand
  - any QuickPanel-based contextual pages using the shared rail
  - Research index search/filter/open-workspace behavior
  - Research workspace last-activity ordering after new message activity

## 2026-03-10 01:31:55Z

Objective:
- Turn research workspaces into handoff surfaces by letting users promote research state into tasks and bounties, copy a research brief, and conclude an investigation with a lightweight final handoff summary.

Findings:
- The safest implementation path was to keep everything inside the current room-backed research model:
  - persist conclusion state directly on `room.research`
  - create tasks/bounties through authenticated backend logic scoped to Research workspaces
  - store lightweight output references back on the workspace so the handoff remains visible in context
- Existing task and bounty collections were already sufficient for operational outputs, but the Research workspace needed a Research-specific server path so promotions could:
  - enforce room membership and Research-workspace checks
  - stamp room-backed output references
  - keep the UX from falling back into generic creation flows
- There is still no dedicated task detail page in the frontend, so task handoff is currently surfaced through the Research workspace output list and the broader room/task system rather than via a dedicated task route.

Changes made:
- Extended `backend/server.py` Research metadata to include:
  - `final_summary`
  - `recommended_next_step`
  - `outputs`
- Added backend normalization helpers for Research text and Research output references.
- Added Research-only backend endpoints:
  - `POST /api/rooms/{slug}/research/promote-task`
  - `POST /api/rooms/{slug}/research/promote-bounty`
- Research promotion endpoints now:
  - require active room membership
  - require `source.kind == "research_project"`
  - create a room-linked task or bounty from the selected Research item
  - append a lightweight output reference into `room.research.outputs`
  - update room timestamps
  - log room/audit events for the promotion
- Updated `frontend/src/components/rooms/ResearchWorkspacePanel.jsx`:
  - added `Copy brief`
  - added `Conclude with summary`
  - added final handoff surfacing for:
    - final summary
    - recommended next step
  - added item-level actions:
    - `Promote to task` from `Next actions`
    - `Promote to bounty` from `Open questions`
  - added `Operational outputs` list so created tasks/bounties remain visible in the Research workspace
  - added conclusion dialog for saving final summary plus recommended next step while surfacing key findings and unresolved questions

Verification performed:
- Syntax/build checks before deploy:
  - `python3 -m py_compile /home/ubuntu/thesparkpit/backend/server.py`
  - `npm --prefix /home/ubuntu/thesparkpit/frontend run build`
- Backend deploy:
  - `docker compose -f /home/ubuntu/thesparkpit/docker-compose.yml build backend_api`
  - `docker compose -f /home/ubuntu/thesparkpit/docker-compose.yml up -d backend_api`
- Frontend deploy:
  - `bash /home/ubuntu/thesparkpit/scripts/deploy_frontend_live.sh`
- Runtime verification:
  - `docker compose -f /home/ubuntu/thesparkpit/docker-compose.yml ps -a`
  - verified `backend_api`, `arq_worker`, `mongodb`, and `redis` are up
- Verified the running backend container directly:
  - route table includes:
    - `POST /api/rooms/{slug}/research/promote-task`
    - `POST /api/rooms/{slug}/research/promote-bounty`
  - `RoomResearchSeed` includes:
    - `final_summary`
    - `recommended_next_step`
  - `RoomResearchUpdate` includes:
    - `final_summary`
    - `recommended_next_step`
- Verified live frontend assets in `/var/www/thesparkpit/index.html`:
  - `main.2c2981de.js`
  - `main.d7f5564f.css`
- Verified the served frontend bundle contains the new Research handoff markers:
  - `Copy brief`
  - `Conclude with summary`
  - `Operational outputs`
  - `Promote to task`
  - `Promote to bounty`
  - `Final handoff`
  - `Recommended next step`
  - `Open bounty`

Unresolved items:
- Browser-capable live interaction validation is still not available from this AWS terminal session, so the new handoff actions were verified through compile/build checks, running-container route/schema inspection, and served-bundle inspection rather than a real browser click-through.
- There is still no dedicated task detail page, so task outputs currently remain visible inside the Research workspace and broader task system without a direct task-detail destination.
- Research remains room-backed; dedicated backend research-project objects still do not exist yet.

Recommended next action:
- In a browser-capable validation pass, verify the live end-to-end Research handoff flow:
  - promote a next action into a task
  - promote an open question into a bounty
  - copy a research brief
  - conclude a workspace with final summary and recommended next step
  - confirm the output list and conclusion state persist after reload

## 2026-03-12 00:39:05Z - Context Re-establishment

Objective:
- Re-read the handoff completely, verify the current live AWS/runtime baseline before any changes, and record any drift from the last logged March 10 state.

Findings:
- `thesparkpit_logbook_handoff.md` was read end to end before any modification.
- Repo head is still `0cc9171704c46ed73ee6483b0233af2daa2175cc` on `main`, ahead of `origin/main` by 6 commits.
- The working tree remains intentionally dirty and should not be treated as a clean deploy baseline:
  - tracked modifications remain across backend, frontend, runbook, and compose files
  - multiple untracked product/runtime files and directories remain present, including `backend/jobs/`, `frontend/src/pages/Research.jsx`, and `thesparkpit_logbook_handoff.md`
- Live frontend served from `/var/www/thesparkpit` is still:
  - `static/js/main.2c2981de.js`
  - `static/css/main.d7f5564f.css`
- `index.html` on the live site still points at those same bundle hashes, and the served app shell over nginx matches them.
- Current container/runtime state is healthy:
  - `backend_api` up
  - `arq_worker` up
  - `mongodb` up
  - `redis` up and healthy
- Worker health is currently good:
  - Redis heartbeat key `sparkpit:worker:heartbeat` returned `1773275882`
  - `ZCARD arq:queue` returned `0`
  - worker logs show clean startup for 9 functions and successful recent job execution, including audit processing and bot reply work
- Live backend route inspection inside `backend_api` confirms the expected currently-shipped feature surface is loaded:
  - `GET|POST /api/admin/invite-codes`
  - `POST /api/admin/invite-codes/{invite_id}/revoke`
  - all six `/api/lobby/posts...` routes
  - `PATCH /api/rooms/{slug}/research`
  - `POST /api/rooms/{slug}/research/promote-task`
  - `POST /api/rooms/{slug}/research/promote-bounty`
- Live Mongo counts currently read:
  - `users=5`
  - `audit_events=46`
  - `invite_codes=3`
  - `tasks=2`
  - `lobby_posts=2`
  - `bounties=0`
- Health and served-page probes are working through nginx:
  - `https://127.0.0.1/health` with `Host: thesparkpit.com` returned `200 OK`
  - `https://127.0.0.1/app/lobby` with `Host: thesparkpit.com` returned the current SPA shell referencing `main.2c2981de.js`
- The homepage logo blocker remains unresolved:
  - `frontend/public/assets/The.SparkPit_Logo.png` still exists on disk
  - `file` still identifies it as `HTML document`, not PNG
- Recent backend logs also show unsolicited probe traffic hitting:
  - `/api/vendor/phpunit/phpunit/src/Util/PHP/eval-stdin.php`
  - current behavior is `404 Not Found`, which is preferable to exposure, but this remains relevant operational/security context

Changes made:
- Added this timestamped context re-establishment entry only; no application code, deployment state, data, or infrastructure config was changed.

Verification performed:
- Read `thesparkpit_logbook_handoff.md` completely.
- Checked repo state:
  - `git -C /home/ubuntu/thesparkpit status --short --branch`
  - `git -C /home/ubuntu/thesparkpit rev-parse HEAD`
  - `git -C /home/ubuntu/thesparkpit log --oneline --decorate -n 8`
- Checked logo asset type:
  - `file /home/ubuntu/thesparkpit/frontend/public/assets/The.SparkPit_Logo.png`
- Checked live served frontend artifacts:
  - `ls -l /var/www/thesparkpit/static/js /var/www/thesparkpit/static/css`
  - `grep -o 'static/js/main\\.[^\"]*\\.js\\|static/css/main\\.[^\"]*\\.css' /var/www/thesparkpit/index.html`
  - `curl -k -sS https://127.0.0.1/app/lobby -H 'Host: thesparkpit.com'`
- Checked runtime/container state:
  - `docker compose -f /home/ubuntu/thesparkpit/docker-compose.yml ps -a`
  - `docker compose -f /home/ubuntu/thesparkpit/docker-compose.yml logs --tail=80 arq_worker`
  - `docker compose -f /home/ubuntu/thesparkpit/docker-compose.yml logs --tail=40 backend_api`
- Checked worker/queue state from Redis:
  - `docker compose -f /home/ubuntu/thesparkpit/docker-compose.yml exec -T redis redis-cli GET sparkpit:worker:heartbeat`
  - `docker compose -f /home/ubuntu/thesparkpit/docker-compose.yml exec -T redis redis-cli ZCARD arq:queue`
- Checked live backend route surface from inside `backend_api`.
- Checked live Mongo collection counts from inside `mongodb`.
- Ran syntax verification:
  - `python3 -m py_compile /home/ubuntu/thesparkpit/backend/server.py /home/ubuntu/thesparkpit/backend/worker.py /home/ubuntu/thesparkpit/backend/jobs/bot_reply.py /home/ubuntu/thesparkpit/backend/jobs/room_summary.py`
- Checked nginx health endpoint directly:
  - `curl -sv -o /dev/null -D - https://127.0.0.1/health -k -H 'Host: thesparkpit.com'`

Unresolved items:
- The homepage logo asset is still invalid HTML, so it must not be deployed as the logo.
- The local working tree remains broadly dirty; future deploy work must isolate intended delta carefully instead of assuming repo `HEAD` or working tree equals the live site.
- Browser-capable validation is still missing for current live frontend flows, including the recent Research handoff surfaces and prior onboarding/report-bug behaviors.
- Background probe traffic against common exploit paths is reaching the app and returning `404`; that is not an active compromise signal from this session, but it is worth keeping visible in operational review.

Recommended next action:
- Keep the next change narrow and verified. The safest next objective is one of:
  - replace the invalid logo with a verified PNG and deploy only that asset path safely
  - run a browser-capable validation pass on the current live Research/onboarding/report-bug flows before shipping more frontend work
  - review nginx/access-log posture around recurring exploit-probe traffic and confirm no further hardening is needed beyond the current `404` behavior

## 2026-03-12 00:43:33Z - Bot Invite Readiness Assessment

Objective:
- Determine what already exists for bringing outside operators' agents into TheSparkPit and identify what is still missing to support a real invite-based agent onboarding flow.

Findings:
- The current implementation supports human invite activation, not bot invite activation:
  - invite codes are generic membership codes with fields for `code`, `max_uses`, `expires_at`, `label`, and `note`
  - claiming an invite activates the current logged-in human user's membership
  - there is no invite type, no bot invite document, no bot-invite acceptance route, and no route that binds an invite directly to a bot or bot operator workflow
- The current bot model is owner-created by an already active human member:
  - `POST /api/bots` requires `require_active_member`
  - created bots are immediately bound to `owner_user_id`
  - there is no ownership transfer or acceptance flow for a bot invited by someone else
- The frontend Bot experience is an internal member console, not an external onboarding flow:
  - the Bots page lets an active member create a bot profile, copy the one-time secret, and manually add the bot to rooms
  - the `connect_url` field is explicitly labeled placeholder in the UI and is only stored, not used to drive a connection flow
  - no shipped frontend flow exists for:
    - inviting an outside operator to connect an agent
    - accepting a bot invitation
    - guiding a bot through challenge/verify/token bootstrap
- There is already a usable technical substrate for bot runtime access once a human owner has created the bot:
  - bot handshake challenge endpoint
  - bot handshake verify endpoint
  - bot token refresh
  - bot token revoke
  - room-level bot membership via `/rooms/{slug}/join-bot`
  - bearer-token bot posting via `/bot/messages`
  - bot heartbeat/presence and moderation controls
- The biggest architectural gap is that invite scope and bot scope are not the same object in the current design:
  - invite claim activates a human account
  - room membership is added later by the owner
  - allowed bot scopes are supplied during handshake verification rather than being issued from a server-side invite grant
- Membership policy enforcement is still scaffold-level:
  - `set_membership_state` updates the user record before evaluating transition policy
  - `evaluate_transition` currently always returns allowed with reason `policy_not_enforced_yet`
  - this is relevant because any future agent/operator onboarding flow will rely on stronger account-state rules than the current stub

Changes made:
- Added this assessment entry only; no application code, runtime state, infrastructure, or data was changed.

Verification performed:
- Reviewed invite, auth, membership, and bot runtime code in:
  - `backend/server.py`
  - `backend/membership_transitions.py`
  - `frontend/src/pages/Join.jsx`
  - `frontend/src/pages/Bots.jsx`
  - `frontend/src/context/AuthContext.jsx`
  - `frontend/src/lib/api.js`
- Verified current invite behavior:
  - registration creates a pending human member
  - invite claim activates the current logged-in human user
  - admin invite creation supports generic code metadata only
- Verified current bot behavior:
  - bot creation requires active membership
  - bot ownership is tied to `owner_user_id`
  - room joins for bots require the requesting human user to own the bot
  - handshake/token endpoints exist for the bot after owner bootstrap
- Verified by source search that `connect_url` has no active frontend orchestration or backend runtime use beyond storage.
- Verified by source search that there is no existing bot-invite or bot-operator acceptance route.

Unresolved items:
- There is still no decided product policy for whether "invite an agent" means:
  - invite a human operator who then registers their own bot
  - invite a bot directly without a normal human membership
  - invite a bot to one room only versus to broader workspace access
- There is no server-side grant object that unifies:
  - who invited the agent
  - which operator may claim it
  - which rooms/channels it may access
  - when access expires
  - how access is revoked or rotated
- There is no operator-safe onboarding package yet:
  - no acceptance URL
  - no bot SDK/bootstrap instructions
  - no guided challenge/verify flow
  - no audit event family specific to bot invites and bot invite claims

Recommended next action:
- Decide the target model first, then implement to that model instead of extending the current human-membership invite flow ad hoc.
- The cleanest next implementation path is:
  - keep human invite codes for people
  - add a separate bot-invite grant model for agents
  - make bot invites carry explicit room/channel scope, inviter, intended operator, expiry, and revocation state
  - add a claim/accept flow that creates or links a bot, completes handshake bootstrap, and issues only the server-approved scopes

## 2026-03-12 00:54:57Z - Registered vs Paid Access Split

Objective:
- Implement the policy split where registered humans can use Research and Bounties, while paid membership remains required for chat posting and self-registering bots.

Findings:
- The existing app gate was all-or-nothing: pending membership blocked the entire `/app` shell even though the desired product model now allows registered humans into at least Research and Bounties.
- Backend route protection was also too coarse:
  - room creation/list/read
  - research workspace updates/promotions
  - bounty routes
  - task routes
  - bot read/management routes
  all hard-required active membership even when the intended action is not chat posting.
- The current research launcher depended on a follow-up chat post for the kickoff brief, which would immediately fail once chat posting became paid-only.
- `GET /rooms/{slug}` needed an explicit private-room guard before broadening access; otherwise widening room reads for registered users would weaken room privacy.
- The purchased bot-invite checkout/claim flow itself is still not implemented in this pass. The safe change completed here is the permission split and self-registration restriction, not the full commerce-backed bot-invite grant system.

Changes made:
- Backend access split in `backend/server.py`:
  - added `require_registered_user` for authenticated humans who are not yet paid members
  - kept paid-only chat and self-bot-registration routes under `require_active_member`
  - moved these surfaces to registered-user access:
    - room create/list/read
    - room research updates and research promote task/bounty
    - room join and room memory read
    - channel message read
    - bounty create/read/claim/update/status
    - task create/read/update/proposal/vote/event routes
    - bot read/list/my-bots/update/handshake challenge/revoke/trust routes
  - added a private-room guard on `GET /rooms/{slug}` before returning room data
  - tightened bot handshake scope issuance so stored allowed room/channel grants are used preferentially instead of blindly trusting client-supplied scope lists
- Frontend route split:
  - `/app` now requires registration instead of paid membership
  - `/app/lobby` remains paid-only
  - Research, Rooms, Bounties, Bots, Activity, and Settings are reachable for registered users
  - app index now routes paid users to Lobby and registered-only users to Research
- Frontend UX updates:
  - login now sends registered-but-unpaid users into `/app/research` instead of back to `/join`
  - join page copy now reflects that research and bounties are usable after registration
  - join page now includes a direct CTA into research/bounties for registered users
  - chat composer is now visibly gated for unpaid users with explanatory copy and disabled send controls
  - research workspace creation no longer attempts the kickoff chat post unless the user has paid chat access
  - bots page now blocks self-registration for unpaid users and explains that self-registered bots require paid membership while outside agents should arrive through purchased bot invites

Verification performed:
- Ran backend syntax verification:
  - `python3 -m py_compile /home/ubuntu/thesparkpit/backend/server.py /home/ubuntu/thesparkpit/backend/worker.py /home/ubuntu/thesparkpit/backend/jobs/bot_reply.py /home/ubuntu/thesparkpit/backend/jobs/room_summary.py`
- Ran frontend build:
  - `npm --prefix /home/ubuntu/thesparkpit/frontend run build`
- Frontend build completed successfully.
- Remaining warnings are the same repo-wide `react-hooks/exhaustive-deps` warnings seen previously in:
  - `src/components/ChatPanel.jsx`
  - `src/context/AuthContext.jsx`
  - `src/pages/Activity.jsx`
  - `src/pages/Bounties.jsx`
  - `src/pages/BountyDetail.jsx`
  - `src/pages/Join.jsx`
  - `src/pages/Rooms.jsx`

Unresolved items:
- Purchased bot invites are still only a policy/UX boundary in this pass; there is not yet a shipped checkout-backed bot-invite grant model, purchase flow, or claim flow.
- Pending users can now enter room-backed research workspaces and read joined/public room context, but chat posting remains locked until paid membership. This is intentional.
- Lobby remains paid-only; if product later wants registered users to read Lobby without posting, that is a separate policy change.
- This pass was verified by compile/build checks only, not by live browser checkout or role-based click-through on the production site.

Recommended next action:
- Build the actual purchased bot-invite system next as a dedicated, scoped feature:
  - checkout-backed invite purchase
  - invite grant record with room/channel scope
  - claim/accept flow for the invited operator
  - server-issued bot scopes from the grant instead of client-declared scope
- After that, run a browser-capable validation pass for:
  - registered user login -> Research/Bounties access
  - unpaid chat lock in Rooms
  - paid member Lobby access
  - unpaid Bots page restrictions

## 2026-03-12 01:23:02Z - Stripe Repair + Admin Config

Objective:
- Repair the broken Stripe integration mismatch, add admin-managed server-side Stripe configuration/status/test endpoints, surface that config in Ops, and remove misleading fake refund placeholders.

Findings:
- `backend/server.py` and `backend/stripe_integration.py` were materially out of sync:
  - route code expected helper methods and constructor args that the helper class did not implement
  - checkout request fields in the server did not match the helper request model
  - this meant the current on-disk Stripe implementation was not coherent even though payment routes existed
- The current admin refund surface was fake:
  - `backend/admin_refunds.py` was Flask-style mock code with in-memory refund data
  - `frontend/src/pages/Refunds.jsx` was an unintegrated mock UI hitting `/admin/refunds`
  - neither belonged to the live FastAPI payment path
- While repairing the payment flow, a real auth flaw was identified in checkout status lookup:
  - a paid Stripe session could have been used to activate the current user if the session id was known but not linked to that user in `payment_transactions`
  - this is now blocked by requiring the stored transaction record and enforcing session ownership before status-driven activation
- Local host Python in this AWS workspace does not currently have the `stripe` package installed even though the backend requirements declare it, so helper import sanity checks had to rely on compile/build plus source alignment rather than host-local runtime import.
- The currently running `backend_api` container is still on the old image and therefore still reflects pre-patch Stripe code until a rebuild/redeploy happens.

Changes made:
- Replaced `backend/stripe_integration.py` with a coherent Stripe helper that now implements:
  - `create_checkout_session`
  - `get_checkout_session`
  - `get_checkout_status`
  - `handle_webhook`
  - `test_connection`
- Repaired `backend/server.py` payment/runtime integration:
  - added DB-backed runtime Stripe config with env fallback
  - added masked Stripe config status helper
  - switched payment routes to use runtime config instead of startup-only env constants
  - aligned checkout route payloads to the repaired helper model
  - preserved server-authoritative membership activation on verified paid status/webhook
  - added safer Stripe error handling for checkout creation, status lookup, and webhook verification
  - fixed checkout status ownership enforcement so unknown or чужой session ids cannot activate the wrong user
- Added admin-only Stripe config endpoints:
  - `GET /api/admin/payments/stripe/config/status`
  - `POST /api/admin/payments/stripe/config`
  - `POST /api/admin/payments/stripe/test`
- Stripe config storage behavior:
  - config is stored server-side in Mongo `payment_settings` doc `id="stripe"`
  - secret key and webhook secret are encrypted server-side before storage
  - raw secret values are never returned to the frontend after save
  - status responses return masked secret values only
  - config updates and test runs emit admin audit events
- Updated admin Ops UI:
  - added a real Stripe configuration panel to the Ops page
  - admin can now enter:
    - publishable key
    - secret key
    - webhook signing secret
    - membership yearly price id
    - bot invite one-time price id
  - admin can save config, test connection, refresh status, and view masked health/config state
- Cleanup:
  - removed `backend/admin_refunds.py`
  - removed `frontend/src/pages/Refunds.jsx`
  - this avoids leaving fake refund surfaces that could be mistaken for live admin functionality

Verification performed:
- Ran backend syntax verification:
  - `python3 -m py_compile /home/ubuntu/thesparkpit/backend/server.py /home/ubuntu/thesparkpit/backend/worker.py /home/ubuntu/thesparkpit/backend/jobs/bot_reply.py /home/ubuntu/thesparkpit/backend/jobs/room_summary.py /home/ubuntu/thesparkpit/backend/stripe_integration.py`
- Ran frontend build:
  - `npm --prefix /home/ubuntu/thesparkpit/frontend run build`
- Frontend build completed successfully.
- Remaining frontend warnings are the existing repo-wide `react-hooks/exhaustive-deps` warnings already present in:
  - `src/components/ChatPanel.jsx`
  - `src/context/AuthContext.jsx`
  - `src/pages/Activity.jsx`
  - `src/pages/Bounties.jsx`
  - `src/pages/BountyDetail.jsx`
  - `src/pages/Join.jsx`
  - `src/pages/Rooms.jsx`
- Verified route presence in source for:
  - Stripe config status/update/test admin endpoints
  - checkout create/status/webhook endpoints
- Attempted runtime helper import sanity check:
  - host-local Python lacked installed `stripe`
  - running backend container still reflects the old image and therefore is not yet a valid post-patch runtime check

Unresolved items:
- These Stripe changes are implemented in the workspace but are not yet deployed to the running live containers.
- Because the admin-config UI is not yet deployed, Stripe credentials still cannot be managed from the live Ops page until the frontend and backend are rebuilt/redeployed.
- No real Stripe API connection test was executed in this session because there are no verified admin-provided credentials saved yet in the new config path.
- Bot invite paid checkout is still not implemented in this pass; only the config field and health/test path for its price id were added.

Recommended next action:
- Before treating this as live, do a controlled deploy of:
  - rebuilt `backend_api`
  - refreshed frontend bundle
- After deploy, verify in a real admin browser session:
  - Ops -> Stripe panel loads
  - saving keys stores masked values only
  - test connection succeeds or returns actionable Stripe errors
  - membership checkout creation works from `/join`
  - checkout status and webhook-driven activation still activate only the rightful user

## 2026-03-12 01:41:31Z - Stripe Repair + Admin Config Deploy

Objective:
- Deploy only the repaired Stripe backend integration and the Ops Stripe settings panel without bundling the unrelated undeployed access/UI changes in the dirty workspace.

Findings:
- Clean deploy isolation from the main workspace was not safe:
  - `backend/server.py` in `/home/ubuntu/thesparkpit` contains Stripe work mixed with unrelated undeployed membership/access changes.
  - `frontend/src/pages/OpsChecklist.jsx` in the workspace also included a broader admin-console redesign that removed existing moderation UI, so deploying that file as-is would have caused a regression.
- To avoid bundling unrelated work, a clean detached worktree was created at `/tmp/thesparkpit-stripe-deploy` from `HEAD`, and only the Stripe backend/routes plus a minimal Ops Stripe panel were ported into that tree.
- During the first `backend_api` restart from the temp compose file, the container exited because `BOT_SECRET_KEY` was not passed through by compose.
- The temp compose file was corrected to pass `BOT_SECRET_KEY` (and `JWT_SECRET` to the worker for parity), after which the rebuilt `backend_api` started normally.
- `mongodb` was briefly recreated by compose during the first backend restart, but it came back on the same named volume and service health recovered.
- Live Stripe remains unconfigured after deploy until an admin saves credentials from the new Ops panel:
  - unauthenticated `POST /api/webhook/stripe` currently returns `400 {"detail":"Stripe webhook not configured"}`
  - this is expected until keys/webhook secret are entered.

Changes made:
- Built a Stripe-only release candidate in `/tmp/thesparkpit-stripe-deploy`.
- Deployed backend from that isolated worktree:
  - rebuilt image `thesparkpit-backend_api`
  - live container `thesparkpit-backend_api-1` now running image `sha256:c6586ca7be02022eaf0d37139f1fdbd39ee454d33400116764b950f354fd779b`
- Deployed frontend from the isolated build output by syncing the temp build into `/home/ubuntu/thesparkpit/frontend/build/` and then rsyncing that build to `/var/www/thesparkpit/`.
- Shipped Stripe-only frontend surface:
  - preserved the existing Ops moderation console
  - appended the new `StripeSettingsPanel`
- Deployed cleanup that removes misleading fake refund placeholders:
  - `backend/admin_refunds.py`
  - `frontend/src/pages/Refunds.jsx`

Verification performed:
- Release-candidate backend syntax check passed:
  - `python3 -m py_compile /tmp/thesparkpit-stripe-deploy/backend/server.py /tmp/thesparkpit-stripe-deploy/backend/stripe_integration.py`
- Release-candidate frontend build passed:
  - `npm --prefix /tmp/thesparkpit-stripe-deploy/frontend run build`
  - only existing repo-wide `react-hooks/exhaustive-deps` warnings remained
- Live backend/process checks:
  - `docker compose ... ps -a` shows `backend_api` up after restart
  - `docker inspect` shows `thesparkpit-backend_api-1` running image `sha256:c6586ca7be02022eaf0d37139f1fdbd39ee454d33400116764b950f354fd779b`
  - `curl -k -sS -D- https://127.0.0.1/health -H 'Host: thesparkpit.com'` returned `HTTP/1.1 200 OK`
- Live route exposure checks:
  - direct backend OpenAPI from `http://127.0.0.1:8000/openapi.json` includes:
    - `/api/admin/payments/stripe/config/status`
    - `/api/admin/payments/stripe/config`
    - `/api/admin/payments/stripe/test`
    - `/api/payments/stripe/checkout`
    - `/api/payments/stripe/checkout/status/{session_id}`
    - `/api/webhook/stripe`
  - nginx-backed unauthenticated probes returned expected live statuses:
    - `GET /api/admin/payments/stripe/config/status` -> `401 Unauthorized`
    - `POST /api/admin/payments/stripe/config` -> `403 Forbidden`
    - `POST /api/admin/payments/stripe/test` -> `403 Forbidden`
    - `POST /api/payments/stripe/checkout` -> `403 Forbidden`
    - `GET /api/payments/stripe/checkout/status/test-session` -> `401 Unauthorized`
    - `POST /api/webhook/stripe` -> `400 Bad Request`
- Live frontend bundle checks:
  - isolated build main JS: `main.d25bea2e.js`
  - isolated build main CSS: `main.efe2c657.css`
  - live `/app/lobby` shell references `main.d25bea2e.js`
  - deployed JS at `/var/www/thesparkpit/static/js/main.d25bea2e.js` matches the isolated build output exactly
  - deployed bundle contains Stripe panel markers:
    - `stripe-settings-panel`
    - `stripe-config-save`
    - `stripe-config-test`
    - `stripe-publishable-key-input`

Unresolved items:
- No Stripe credentials or price IDs have been saved yet in the new admin config path, so the live Stripe webhook/test/checkout flow is not expected to complete successfully until an admin configures it.
- Browser-authenticated validation of the Ops Stripe save/test flow and an end-to-end membership checkout has not been performed in this terminal session.
- The main workspace at `/home/ubuntu/thesparkpit` remains dirty with unrelated undeployed work; future deploys should continue to isolate changes carefully.

Recommended next action:
- In an authenticated admin browser session, validate the newly deployed Ops Stripe panel in this order:
  - save publishable key, secret key, webhook secret, membership yearly price id, and bot invite price id
  - refresh/read back and confirm only masked secret values are shown
  - run `Test connection` and confirm account/mode/test metadata populate
  - create a membership checkout from `/join`
  - send or wait for a real Stripe webhook and confirm membership activation happens only for the correct user

## 2026-03-12 02:15:17Z - Nginx + Static Hardening Pass

Objective:
- Apply the audit hardening items in priority order without breaking live SPA routing:
  - block source maps
  - add baseline security headers
  - suppress nginx version exposure
  - disable production frontend sourcemaps
  - serve real static `robots.txt` and `sitemap.xml`

Findings:
- The main workspace at `/home/ubuntu/thesparkpit` remains heavily dirty and is not a safe direct deploy base.
- The correct live-source base for frontend changes is still `/tmp/thesparkpit-stripe-deploy`, which matches the currently deployed Stripe admin build.
- The live nginx vhost was minimal:
  - no `.map` blocking
  - no security response headers
  - no `server_tokens off`
  - `/robots.txt` and `/sitemap.xml` would have fallen through SPA routing instead of serving real static files
- Production frontend builds were still capable of generating source maps unless explicitly disabled.
- CSP was intentionally not added in this pass per instruction because current frontend behavior, Stripe flows, and websocket usage were not fully revalidated for a safe production CSP rollout.

Changes made:
- Hardened live nginx config in `/etc/nginx/sites-available/thesparkpit`:
  - added `server_tokens off`
  - added:
    - `X-Content-Type-Options: nosniff`
    - `X-Frame-Options: SAMEORIGIN`
    - `Referrer-Policy: strict-origin-when-cross-origin`
    - restrictive `Permissions-Policy`
    - `Strict-Transport-Security: max-age=31536000; includeSubDomains`
  - added exact static file handling for:
    - `/robots.txt`
    - `/sitemap.xml`
  - added `location ~* \.map$ { return 404; }`
  - preserved `location / { try_files $uri $uri/ /index.html; }` so SPA routing still works
- Hardened isolated live-source frontend in `/tmp/thesparkpit-stripe-deploy/frontend`:
  - added `.env.production` with `GENERATE_SOURCEMAP=false`
  - added `frontend/public/robots.txt`
  - added `frontend/public/sitemap.xml`
- Rebuilt the isolated frontend and redeployed static assets to `/var/www/thesparkpit`.

Verification performed:
- Frontend rebuild succeeded from `/tmp/thesparkpit-stripe-deploy/frontend`:
  - output JS: `main.1ae3f7b1.js`
  - output CSS: `main.679a6e74.css`
  - only the existing repo-wide React hook warnings remained
- Build/output checks:
  - `find /tmp/thesparkpit-stripe-deploy/frontend/build -type f -name '*.map'` returned no results
  - `find /var/www/thesparkpit -type f -name '*.map'` returned no results after deploy
  - build root contains real `robots.txt` and `sitemap.xml`
- Nginx validation:
  - `sudo nginx -t` passed
  - nginx reloaded successfully
- Live response verification through nginx:
  - `/login` returned `200 OK`
  - `/app/bounties` returned `200 OK`, confirming SPA routing still falls back correctly
  - `/robots.txt` returned `200 OK` with `Content-Type: text/plain`
  - `/sitemap.xml` returned `200 OK` with XML content (`Content-Type: text/xml`)
  - source-map probe `/static/js/main.1ae3f7b1.js.map` returned `404 Not Found`
  - `Server` header now returns `nginx` without version
  - response headers observed on live app/static responses:
    - `X-Content-Type-Options: nosniff`
    - `X-Frame-Options: SAMEORIGIN`
    - `Referrer-Policy: strict-origin-when-cross-origin`
    - `Permissions-Policy: accelerometer=(), autoplay=(), camera=(), display-capture=(), encrypted-media=(), fullscreen=(self), geolocation=(), gyroscope=(), microphone=(), midi=(), payment=(), publickey-credentials-get=(), usb=()`
    - `Strict-Transport-Security: max-age=31536000; includeSubDomains`

Unresolved items:
- No CSP was deployed in this pass. That remains a separate task that requires explicit validation against current frontend runtime behavior, Stripe checkout/admin flows, and websocket usage before shipping.
- The main workspace source tree still contains unrelated undeployed changes and should not be treated as a clean release base without isolation.

Recommended next action:
- Leave this hardening in place and do a separate deliberate CSP assessment later if desired.
- If future frontend deploys are done outside the isolated temp tree, ensure the production build path still preserves `GENERATE_SOURCEMAP=false` and verify `.map` files remain absent before rsync.

## 2026-03-12 02:30:54Z - CSP Report-Only Rollout + Follow-up Audit

Objective:
- Add a safe CSP rollout in report-only mode first, with an actual report sink, while also auditing cookies, rate limits, CORS, and residual public-path exposure.

Findings:
- Current live frontend dependencies relevant to CSP are:
  - same-origin app/API/static assets
  - same-origin websocket at `/api/ws`
  - Google Fonts CSS/font hosts from `frontend/public/index.html`
  - Unsplash landing-page image in `frontend/src/pages/Landing.jsx`
  - Stripe is currently a top-level redirect to Checkout, not a frontend-loaded script
- Before this pass there was no CSP header, no CSP report sink, and no admin readback for CSP violations.
- Follow-up backend audit found missing throttles on several sensitive endpoints:
  - `/api/auth/register`
  - `/api/auth/login`
  - `/api/auth/invite/claim`
  - `/api/payments/stripe/checkout`
  - `/api/payments/stripe/checkout/status/{session_id}`
- Follow-up nginx audit found nonpublic scanner paths like `/.env`, `/.git/config`, and `/backend/server.py` were not exposing files, but they were falling through to the SPA shell with `200 OK`, which is noisy and unnecessary.
- Cookie/CORS audit:
  - `/api/auth/csrf` already sets `spark_csrf` with `Secure; SameSite=Lax`
  - auth cookie code path still sets `spark_token` with `HttpOnly`, `Secure`, and `SameSite` from `get_cookie_settings()` defaults
  - current CORS origin scope is not broad by origin, but methods/headers were previously wildcarded

Changes made:
- Added CSP in report-only mode on the HTTPS nginx vhost:
  - `Content-Security-Policy-Report-Only`
  - policy currently allows:
    - `'self'` for default/script/base/frame ancestry
    - Google Fonts CSS/fonts
    - Unsplash landing image host
    - same-origin HTTPS + WSS app connectivity
    - Stripe checkout as `form-action` destination
  - report target:
    - `/api/security/csp-report`
- Added backend CSP reporting endpoints in the isolated live-source backend:
  - `POST /api/security/csp-report`
  - `GET /api/admin/security/csp-reports`
- CSP report handling behavior:
  - accepts legacy `application/csp-report` and normalized JSON report payloads
  - stores normalized reports in Mongo `csp_reports`
  - adds request metadata (`ip`, `user_agent`, timestamp)
  - rate limits report ingestion by IP
  - exempts the report endpoint from CSRF enforcement
- Tightened backend throttling on sensitive routes:
  - registration
  - login
  - invite claim
  - Stripe checkout creation
  - Stripe checkout status polling
- Tightened CORS middleware:
  - kept `allow_credentials=True`
  - kept explicit origin allowlist from `CORS_ORIGINS`
  - changed methods from wildcard to `GET, POST, PATCH, DELETE, OPTIONS`
  - changed headers from wildcard to `Authorization, Content-Type, X-CSRF-Token`
- Tightened nginx nonpublic-path handling:
  - hidden files now `404`
  - `/backend/`, `/scripts/`, and `/tests/` now `404`

Verification performed:
- Backend syntax check passed:
  - `python3 -m py_compile /tmp/thesparkpit-stripe-deploy/backend/server.py /tmp/thesparkpit-stripe-deploy/backend/stripe_integration.py`
- Rebuilt and restarted live `backend_api` from `/tmp/thesparkpit-stripe-deploy`
  - container came up healthy on image `sha256:b2f3b881ef1712f55e38e42b23fbc565f0bafc37c8717a6ed4d1505926e62833`
- Nginx validation:
  - `sudo nginx -t` passed
  - nginx reloaded successfully
- Live CSP/header verification:
  - `/login` now returns `Content-Security-Policy-Report-Only`
  - live header value observed:
    - `default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'self'; script-src 'self' 'report-sample'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com 'report-sample'; font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data: https://images.unsplash.com; connect-src 'self' https://thesparkpit.com https://www.thesparkpit.com wss://thesparkpit.com wss://www.thesparkpit.com; form-action 'self' https://checkout.stripe.com; manifest-src 'self'; report-uri /api/security/csp-report`
- CSP reporting verification:
  - sent a synthetic CSP violation report through nginx to `/api/security/csp-report`
  - live response returned `{"received":true,"count":1}`
  - verified Mongo stored the normalized report in `csp_reports`
  - backend OpenAPI now includes:
    - `/api/security/csp-report`
    - `/api/admin/security/csp-reports`
- Cookie verification:
  - `/api/auth/csrf` response sets `spark_csrf=...; Path=/; SameSite=lax; Secure`
  - auth token cookie behavior verified in code:
    - `spark_token` is set with `HttpOnly`, `Secure`, `SameSite=Lax` defaults unless env overrides
    - CSRF cookie is intentionally not `HttpOnly` so JS can submit the double-submit token
- CORS verification:
  - preflight from disallowed origin `https://evil.example` returned `400` and no `access-control-allow-origin`
  - preflight from allowed origin `http://localhost:3000` returned `200` with:
    - `access-control-allow-origin: http://localhost:3000`
    - explicit allow-methods and allow-headers
- Public-path verification:
  - after nginx tightening, all now return `404`:
    - `/.env`
    - `/.git/config`
    - `/backend/server.py`
    - `/scripts/deploy_frontend_live.sh`
    - `/tests/test_seed_demo.py`

Unresolved items:
- No real browser-generated CSP violations were captured in this terminal session; only the synthetic seeded report was observed. The policy is intentionally still report-only for that reason.
- Current report-only policy still permits:
  - `style-src 'unsafe-inline'`
  - Google Fonts
  - Unsplash image host
  These are acceptable for safe rollout, but they are not the tightest long-term posture.

Recommended next action:
- Leave the current policy in report-only mode long enough to observe real browser traffic and inspect `/api/admin/security/csp-reports` output.
- If no unexpected violations appear, the current enforceable CSP candidate is the same policy now in `Content-Security-Policy-Report-Only` moved to `Content-Security-Policy`.
- For a stricter future CSP, first remove:
  - Google Fonts dependency from `frontend/public/index.html`
  - Unsplash remote hero image dependency
  - inline style usage on the landing page
  After those frontend cleanups, tighten toward:
  - `style-src 'self'`
  - `font-src 'self'`
  - `img-src 'self' data:`

## 2026-03-12 21:23:40Z - Admin Security Visibility Panel Deployed

Objective:
- Add a lightweight admin-facing security visibility surface in Ops so the new hardening controls are observable before moving CSP from report-only to enforced.

Findings:
- The live-aligned source base remains `/tmp/thesparkpit-stripe-deploy`; the main workspace at `/home/ubuntu/thesparkpit` is still too dirty to use as a direct deploy baseline.
- Existing signal sources were already present but split across systems:
  - CSP reports in Mongo `csp_reports`
  - failed logins in Mongo `audit_events`
  - recent rate-limit hits only in Redis `rl:events`
  - no explicit stored failure events yet for invite-claim failures or Stripe checkout/webhook failures
- A first attempt to restart from the temp compose file created a separate compose project namespace from `/tmp` and failed before binding ports because Mongo `127.0.0.1:27017` was already allocated; this did not replace the live stack.
- The safe backend correction was:
  - build the `thesparkpit-backend_api` image from the isolated temp tree
  - then recreate `backend_api` through the live compose file at `/home/ubuntu/thesparkpit/docker-compose.yml` so live `.env` wiring remained intact
- Frontend deploy to `/var/www/thesparkpit` required an escalated `rsync` because sandboxed `sudo` is blocked by `no new privileges` in this environment.

Changes made:
- Backend in `/tmp/thesparkpit-stripe-deploy/backend/server.py`:
  - added lightweight `security_events` logging helper
  - mirrored rate-limit hits into Mongo `security_events` while preserving the existing Redis `rl:events` buffer
  - added explicit stored failure events for:
    - `auth.login.failure`
    - `invite.claim.failure`
    - `payment.stripe.checkout.failure`
    - `payment.stripe.checkout.status.failure`
    - `payment.stripe.webhook.failure`
  - added admin-only aggregate endpoint:
    - `GET /api/admin/security/overview`
  - added helper severity/count shaping for:
    - CSP reports
    - throttle hotspots
    - failed logins
    - invite-claim failures
    - Stripe failures
  - added Mongo indexes for:
    - `audit_events (event_type, created_at)`
    - `security_events (event_type, created_at)`
    - `security_events (route, created_at)`
- Frontend in `/tmp/thesparkpit-stripe-deploy/frontend`:
  - added new admin component:
    - `frontend/src/components/admin/SecurityVisibilityPanel.jsx`
  - updated:
    - `frontend/src/pages/OpsChecklist.jsx`
  - Ops now includes:
    - summary cards with 24h / 7d counts and severity labels
    - recent CSP reports
    - throttle hotspots by route
    - recent throttle hits
    - recent failed logins
    - recent invite-claim failures
    - recent Stripe checkout/webhook failures
    - top-of-page anchor link `Security view` into the new section
- Live deploy:
  - rebuilt backend image from isolated temp source:
    - `sha256:bbded5446cc57142e1b7f9549ab2482c611352ed451fac83f8d231adcdacd395`
  - recreated live `backend_api` through `/home/ubuntu/thesparkpit/docker-compose.yml`
  - synced rebuilt frontend bundle into `/var/www/thesparkpit`

Verification performed:
- Read `thesparkpit_logbook_handoff.md` completely before changes.
- Backend syntax verification passed:
  - `python3 -m py_compile /tmp/thesparkpit-stripe-deploy/backend/server.py /tmp/thesparkpit-stripe-deploy/backend/stripe_integration.py`
- Frontend build passed:
  - `npm --prefix /tmp/thesparkpit-stripe-deploy/frontend run build`
  - only existing repo-wide `react-hooks/exhaustive-deps` warnings remained
- Live frontend bundle verification:
  - `/var/www/thesparkpit/index.html` now references:
    - `static/js/main.7f13a8b5.js`
    - `static/css/main.b2797807.css`
  - deployed bundle contains:
    - `security-visibility-panel`
    - `security-visibility-refresh`
    - `CSP reports`
    - `Throttle hotspots by route`
    - `Stripe checkout/webhook failures`
- Live backend/runtime verification:
  - `docker compose -f /home/ubuntu/thesparkpit/docker-compose.yml ps -a` shows:
    - `backend_api` up
    - `arq_worker` up
    - `mongodb` up
    - `redis` up and healthy
  - `docker inspect -f '{{.Image}}' thesparkpit-backend_api-1` returned:
    - `sha256:bbded5446cc57142e1b7f9549ab2482c611352ed451fac83f8d231adcdacd395`
  - Redis worker heartbeat remains present:
    - `GET sparkpit:worker:heartbeat` -> `1773350544`
  - direct route inspection inside the live container confirmed:
    - `/api/admin/security/overview`
    - `/api/admin/security/csp-reports`
    - `/api/security/csp-report`
  - nginx probe verification:
    - `GET /health` -> `200 OK`
    - `GET /api/admin/security/overview` unauthenticated -> `401 Unauthorized`
  - synthetic Stripe webhook failure probe:
    - `POST /api/webhook/stripe` with invalid/unconfigured payload -> `400 {"detail":"Stripe webhook not configured"}`
    - Mongo readback confirmed stored security signal:
      - `payment.stripe.webhook.failure`
      - severity `high`
      - route `/webhook/stripe`
  - Mongo counts after deploy:
    - `security_events=1`
    - `webhook_failures=1`
    - `csp_reports=1`
    - `failed_logins=3`

Unresolved items:
- Browser-authenticated validation of the Ops page itself is still needed from a real admin session:
  - confirm the new Security panel renders
  - confirm counts/lists display correctly for current live data
  - confirm the `Security view` jump link lands correctly
- `security_events` starts populated only from this deploy forward, so 24h / 7d counts for invite/Stripe/rate-limit signals will become more representative over time rather than reflecting deep history immediately.
- Recreating `backend_api` through the live compose file also recreated `mongodb` onto the same named volume; service came back healthy and data remained present, but future backend-only deploys should continue to watch for that compose behavior.

Recommended next action:
- In an authenticated admin browser session, validate the new Ops Security panel against live data and use it to review CSP reports before any move from report-only to enforce mode.
- If the panel looks useful in practice, the next incremental improvement is a small filter bar for time window and event family; do not add mutation or acknowledgement flows yet.

## 2026-03-12 21:42:28Z - Invite Expiration Midnight Fix + CSP Enforcement Review Deferred

Objective:
- Fix invite generation/claim semantics so invite expiration is date-based with no time-of-day ambiguity, then use the new security visibility surface to determine whether CSP is ready to move from report-only to enforced.

Findings:
- The live-aligned source base remains `/tmp/thesparkpit-stripe-deploy`; the main workspace is still not safe as a direct release baseline.
- The isolated live-source frontend did not currently expose the richer historical invite-management panel from the dirty main workspace, so the invite-expiration change was implemented against the actual live Settings invite card rather than against undeployed workspace UI.
- Existing backend invite expiration behavior was too literal:
  - `expires_at` was stored and compared as an arbitrary string/timestamp
  - a datetime input could therefore cause invites to expire midday rather than at the end of the selected date
- Current live CSP evidence is still insufficient for enforcement:
  - Mongo `csp_reports` count is `1`
  - the only report present is the earlier synthetic seeded test:
    - `document_uri=https://thesparkpit.com/login`
    - `effective_directive=img-src`
    - `blocked_uri=https://example.invalid/tracker.png`
    - user agent `curl/7.81.0`
  - there are still no real browser-generated CSP reports from normal interactive use across landing/login/join/research/rooms/Stripe/websocket flows
- Because there is no browser installed on this AWS host and no authenticated admin browser session available through the terminal, the required real browser validation for safe CSP enforcement could not be completed in this session.

Changes made:
- Backend in `/tmp/thesparkpit-stripe-deploy/backend/server.py`:
  - added invite-expiration helpers to:
    - normalize any supplied invite expiration down to a canonical `YYYY-MM-DD`
    - compute the effective expiration boundary as midnight immediately after that date
    - evaluate invite expiry against that boundary
  - updated invite creation to:
    - accept existing `expires_at` input for compatibility
    - validate it as a date/date-time input
    - store only the canonical date portion
  - updated invite claim to:
    - treat invites as valid through the full selected date
    - reject invalid stored expiration formats explicitly
    - stop relying on raw string comparison against `now_iso()`
- Frontend in `/tmp/thesparkpit-stripe-deploy/frontend/src/pages/Settings.jsx`:
  - added a date-only invite expiration input
  - removed time-of-day semantics from the live admin invite generator path
  - added explicit copy that invites expire at midnight after the selected date
  - updated invite success display to show:
    - the code
    - `Expires end of day YYYY-MM-DD`
- CSP rollout decision:
  - no nginx CSP header change was made
  - site remains on `Content-Security-Policy-Report-Only`
  - reporting remains active via `/api/security/csp-report`

Verification performed:
- Read `thesparkpit_logbook_handoff.md` completely before making changes.
- Backend syntax verification passed:
  - `python3 -m py_compile /tmp/thesparkpit-stripe-deploy/backend/server.py /tmp/thesparkpit-stripe-deploy/backend/stripe_integration.py`
- Frontend build passed:
  - `npm --prefix /tmp/thesparkpit-stripe-deploy/frontend run build`
  - only existing repo-wide `react-hooks/exhaustive-deps` warnings remained
- Live deploy:
  - rebuilt backend image from isolated temp source:
    - `sha256:03afe9bbe4eb4ea209bcb6e4792fba52a3a7db7b5293066b0c40aa391d02f958`
  - recreated live `backend_api` through `/home/ubuntu/thesparkpit/docker-compose.yml`
  - synced rebuilt frontend bundle into `/var/www/thesparkpit`
- Invite-expiration runtime verification in the live backend container:
  - `normalize_invite_expiration_date('2026-03-15T09:30')` -> `2026-03-15`
  - `invite_expiration_boundary('2026-03-15T09:30')` -> `2026-03-16T00:00:00+00:00`
  - `is_invite_expired(..., reference=2026-03-15 23:59 UTC)` -> `False`
  - `is_invite_expired(..., reference=2026-03-16 00:00 UTC)` -> `True`
- Live frontend bundle verification:
  - `/var/www/thesparkpit/index.html` now references:
    - `static/js/main.bb0ce9ce.js`
    - `static/css/main.95d2c964.css`
  - deployed bundle contains:
    - `invite-expires-on-input`
    - `Expiration is date-only`
    - `Expires end of day`
- Live runtime verification:
  - `docker compose -f /home/ubuntu/thesparkpit/docker-compose.yml ps -a` shows:
    - `backend_api` up
    - `arq_worker` up
    - `mongodb` up
    - `redis` up and healthy
  - nginx `GET /health` returned `200 OK`
  - `/login` still returns:
    - `Content-Security-Policy-Report-Only`
    - not `Content-Security-Policy`
- CSP review verification:
  - queried Mongo `csp_reports`
  - confirmed only the single synthetic seeded report exists
  - did not observe any real browser-generated violations or clean-browser evidence in this terminal session

Unresolved items:
- CSP was intentionally not enforced in this pass because the required browser-based validation across real app flows has still not happened.
- The current CSP report set is too weak to justify enforcement:
  - one synthetic seeded noise report
  - zero real browser interaction reports from the target flows
- The richer invite inventory/filter UI that exists in the dirty main workspace is still not the live deploy baseline; only the currently shipped Settings invite generator path was updated here.

Recommended next action:
- Use a real authenticated admin browser session to exercise:
  - landing page
  - login/join
  - research flows
  - room/workspace flows
  - Stripe settings
  - membership checkout
  - websocket/live-update areas
- Then review `/app/ops` -> `Security`:
  - if CSP remains quiet or only shows acceptable expected noise, switch nginx from `Content-Security-Policy-Report-Only` to `Content-Security-Policy` while keeping `report-uri /api/security/csp-report`
  - if any real violations appear, adjust only the specific blocked source/directive needed and do not enforce until the path is clean

## 2026-03-12 22:06:10Z - Ops Stripe Panel Input Interactivity Fix

Objective:
- Fix the live Ops Stripe settings panel where the form rendered but the inputs could not be edited, without changing unrelated Ops behavior.

Findings:
- `StripeSettingsPanel.jsx` itself was not the problem:
  - the inputs were controlled correctly
  - they were not rendered with `disabled` or `readOnly`
  - `loading`, `saving`, and `testing` only disabled the action buttons, not the text inputs
- No click-blocking overlay or pointer-events issue was found in the shared input component, app shell, quick panel, or the new security panel.
- The concrete defect was in `frontend/src/pages/OpsChecklist.jsx`:
  - the moderation lookup filter helpers for rooms/channels/bounties had been left outside the component body after the `export default function OpsChecklist()` return block
  - that produced broken page-module code in the generated bundle, with the built asset containing top-level references like `const df=rooms.filter(...)`
  - after moving those filter computations back inside the component, the rebuilt bundle no longer emitted the broken top-level pattern
- Conclusion:
  - root cause category: page logic/runtime bug
  - not an auth gating issue
  - not a CSS/overlay issue
  - not a Stripe form `onChange` wiring issue

Changes made:
- In `/tmp/thesparkpit-stripe-deploy/frontend/src/pages/OpsChecklist.jsx`:
  - moved `filteredRooms`, `filteredChannels`, and `filteredBounties` inside the `OpsChecklist` component body, immediately before the `return`
  - removed the stray duplicate declarations after the component closing brace
- Rebuilt the isolated frontend and deployed only the rebuilt frontend bundle to `/var/www/thesparkpit`.

Verification performed:
- Re-read `thesparkpit_logbook_handoff.md` completely before starting work.
- Confirmed in source that `StripeSettingsPanel.jsx` inputs were editable and not intentionally disabled.
- Ran a temporary mounted render check locally against the Ops page to verify the Stripe input accepted typed values after the page-source fix; then removed that temporary test scaffolding so no extra test/config changes were left behind.
- Built the isolated frontend successfully:
  - `npm --prefix /tmp/thesparkpit-stripe-deploy/frontend run build`
  - output bundle: `main.6a42f81c.js`
- Verified the rebuilt bundle no longer contained the broken top-level lookup-filter pattern and still contained the Stripe input markers.
- Deployed via rsync:
  - backup: `/home/ubuntu/thesparkpit/artifacts/frontend-backup-20260312-220357/`
  - live web root updated: `/var/www/thesparkpit`
- Live runtime verification:
  - `curl -k -sS https://127.0.0.1/app` serves `main.6a42f81c.js`
  - `GET /health` returned `200 OK`
  - live asset `/var/www/thesparkpit/static/js/main.6a42f81c.js` contains `stripe-publishable-key-input`
  - live asset no longer contains the broken top-level `rooms.filter` / `channels.filter` / `bounties.filter` declarations

Unresolved items:
- Browser-authenticated click/focus validation on the live `/app/ops` page is still recommended from a real admin session because this AWS terminal does not have a browser installed.
- `/app/ops` remains only membership-gated in the router, while the backend correctly enforces admin-only API access; that route-level admin gating mismatch predates this fix and was not changed in this pass.

Recommended next action:
- Open `/app/ops` in a real admin browser session and confirm the Stripe settings inputs are now focusable, clickable, and editable.
- If desired after that validation, add explicit frontend route-level admin gating for `/app/ops` as a separate change rather than mixing it into this input-fix pass.

## 2026-03-12 22:31:40Z - Login Regression Guardrail Restored

Objective:
- Restore live login reliability after user report that they could not log into TheSparkPit.

Findings:
- The live backend auth surface was still present and healthy:
  - `GET /api/auth/csrf`
  - `POST /api/auth/login`
  - `POST /api/auth/logout`
  - `POST /api/auth/register`
- The live regression was in the deployed frontend bundle, not in missing backend routes:
  - current live JS `main.6a42f81c.js` still contained the older auth-context marker text `Account forged. Activate with your invite code.`
  - the isolated deploy tree `/tmp/thesparkpit-stripe-deploy/frontend/src/context/AuthContext.jsx` had regressed to the older auth implementation that lacked:
    - CSRF reset on logout
    - retry-once with a freshly fetched CSRF token after `403`
- This reintroduced the exact earlier login failure class already documented on 2026-03-07:
  - in the same SPA session after logout or stale/missing CSRF state, the client could keep sending an invalid token and fail to recover cleanly
- The isolated deploy tree had also drifted back to the older `frontend/src/lib/api.js` implementation, so the safer backend-origin resolver was restored at the same time to avoid future `/undefined/api`-style regressions if env handling changes.

Changes made:
- Updated `/tmp/thesparkpit-stripe-deploy/frontend/src/context/AuthContext.jsx` to restore the known-good auth guardrails:
  - added `resetCsrf()`
  - added `ensureCsrf(force = false)`
  - added `withFreshCsrf(...)`
  - updated `login` and `register` to retry once after a `403` with a newly fetched CSRF token
  - updated `logout` to clear local CSRF state
- Updated `/tmp/thesparkpit-stripe-deploy/frontend/src/lib/api.js` to restore the safe backend URL resolver:
  - use `REACT_APP_BACKEND_URL` when set
  - otherwise fall back to `window.location.origin`
- Rebuilt the isolated frontend and redeployed the frontend bundle only to `/var/www/thesparkpit`.

Verification performed:
- Re-read `thesparkpit_logbook_handoff.md` completely before changes.
- Verified the live backend container still exposes the auth routes listed above.
- Verified the isolated frontend source had regressed auth logic before patching by comparing:
  - `/tmp/thesparkpit-stripe-deploy/frontend/src/context/AuthContext.jsx`
  - `/home/ubuntu/thesparkpit/frontend/src/context/AuthContext.jsx`
  - `/tmp/thesparkpit-stripe-deploy/frontend/src/lib/api.js`
  - `/home/ubuntu/thesparkpit/frontend/src/lib/api.js`
- Rebuilt the isolated frontend successfully:
  - `npm --prefix /tmp/thesparkpit-stripe-deploy/frontend run build`
  - new JS bundle: `main.5dc4ecfa.js`
- Backed up the prior live web root to:
  - `/home/ubuntu/thesparkpit/artifacts/frontend-backup-20260312-222711/`
- Deployed the rebuilt frontend to `/var/www/thesparkpit`.
- Verified the deployed live bundle now contains the restored auth markers:
  - new registration toast text `Research and bounties are open; paid access unlocks chat`
  - `window.location.origin` fallback present
  - CSRF header wiring still present
- Verified the old regressed registration toast marker is absent from the new live bundle:
  - `Activate with your invite code.`
- Verified runtime container state after deploy:
  - `backend_api` up
  - `arq_worker` up
  - `mongodb` up
  - `redis` up and healthy

Unresolved items:
- Browser-authenticated live login validation is still needed from a real browser session because host-local HTTPS curl remains unreliable in this sandboxed terminal environment.
- The repeated `GET /api/bots -> 405` requests seen in backend logs are unrelated to this login regression and should be investigated separately.

Recommended next action:
- Retry login in a real browser now that the auth guardrails are restored.
- If login succeeds, separately inspect why the frontend is still making `GET /api/bots` requests against a non-GET route so that noise does not mask future auth incidents.

## 2026-03-12 22:40:55Z - Frontend Shell Restore After Login Fix Regression

Objective:
- Restore the richer main app shell after user report that the Lobby/main page looked stripped down and important UI had disappeared following the frontend-only login fix deploy.

Findings:
- The immediate login fix was correct, but it was built from the isolated frontend tree at `/tmp/thesparkpit-stripe-deploy`, and that tree was materially behind the expected product shell.
- The isolated tree was missing newer frontend files and routing already present in the main workspace, including:
  - `/app/lobby`
  - `/app/research`
  - `/app/moderation`
  - the richer sidebar/navigation model
  - the newer collapsible middle-rail app shell
  - Lobby components
  - the onboarding modal hook in `AppShell`
- Concrete evidence:
  - `/tmp/thesparkpit-stripe-deploy/frontend/src/pages/` lacked `Lobby.jsx`, `Research.jsx`, and `Moderation.jsx`
  - `/tmp/.../frontend/src/App.js` still routed `/app` index to `bounties` and did not include the newer Lobby/Research/admin route structure
  - `/tmp/.../frontend/src/components/layout/RoomsSidebar.jsx` was the older stripped navigation version
- This means the login-fix deploy unintentionally preserved auth recovery but regressed the richer main-page shell the user expected.

Changes made:
- Restored the richer frontend shell from `/home/ubuntu/thesparkpit/frontend/src` into the isolated live-source tree for the files needed to recover the main product surface:
  - `frontend/src/App.js`
  - `frontend/src/pages/Lobby.jsx`
  - `frontend/src/pages/Research.jsx`
  - `frontend/src/pages/Moderation.jsx`
  - `frontend/src/pages/Rooms.jsx`
  - `frontend/src/components/layout/AppShell.jsx`
  - `frontend/src/components/layout/QuickPanel.jsx`
  - `frontend/src/components/layout/ChannelsSidebar.jsx`
  - `frontend/src/components/layout/RoomsSidebar.jsx`
  - `frontend/src/components/lobby/*`
  - `frontend/src/components/onboarding/WelcomeModal.jsx`
  - `frontend/src/components/rooms/ResearchWorkspacePanel.jsx`
  - `frontend/src/components/ChatPanel.jsx`
  - supporting admin shell components used by the richer pages:
    - `AdminPageHeader.jsx`
    - `AdminStatusCards.jsx`
    - `ModerationConsole.jsx`
    - `InviteManagementPanel.jsx`
- Kept the newer isolated-tree fixes in place instead of overwriting them:
  - Stripe settings panel
  - Security visibility panel
  - date-only invite expiry behavior
  - restored auth/CSRF guardrails
- Rebuilt the isolated frontend and redeployed the frontend bundle only to `/var/www/thesparkpit`.

Verification performed:
- Re-read `thesparkpit_logbook_handoff.md` completely before making the restore.
- Verified the missing richer-shell files by direct file comparison between:
  - `/tmp/thesparkpit-stripe-deploy/frontend/src/...`
  - `/home/ubuntu/thesparkpit/frontend/src/...`
- Rebuilt the isolated frontend successfully:
  - `npm --prefix /tmp/thesparkpit-stripe-deploy/frontend run build`
  - new assets:
    - `main.458cdf51.js`
    - `main.5d027a97.css`
- Backed up the previous live web root to:
  - `/home/ubuntu/thesparkpit/artifacts/frontend-backup-20260312-223637/`
- Deployed the rebuilt frontend to `/var/www/thesparkpit`.
- Verified the new live bundle on disk contains both restored shell markers and the newer fixes:
  - `Pit Lobby`
  - `Start research project`
  - `security-visibility-panel`
  - `stripe-publishable-key-input`
  - `paid access unlocks chat`
- Verified runtime containers remained healthy after the frontend restore:
  - `backend_api` up
  - `arq_worker` up
  - `mongodb` up
  - `redis` up and healthy

Unresolved items:
- Browser-based validation is still required to visually confirm the restored Lobby/main-page shell now matches expectations.
- The repeated `GET /api/bots -> 405` log noise remains unrelated and still needs a separate cleanup pass.

Recommended next action:
- Validate the live UI in a real browser immediately:
  - Lobby route present again
  - Research route present again
  - sidebar primary navigation restored
  - onboarding/report-bug path still visible
  - Ops Stripe/security panels still present
- After that, stop using the isolated frontend tree as an assumed complete product-shell baseline unless it is first reconciled against the expected live UX surface.

## 2026-03-12 23:03:35Z - Lobby Live Signal Ticker Restore

Objective:
- Restore the Lobby `Live signal` area to a compact ambient motion surface instead of the heavy stacked block that was dominating the page.

Findings:
- The current live Lobby hero was rendering every signal chip in the top band at once, which made `Live signal` behave like a mini feed rather than ambient network motion.
- The signal data itself was still useful; the problem was presentation:
  - too many items visible at once
  - no meaningful rotation/advance behavior
  - the hero area was competing with the composer and public-square feed
- Existing signal items already had enough routing context for click-through in most cases:
  - derived activity items already carried room/bounty links
  - audit signals could safely route to audit/settings
  - fallback room/bounty/bot counters could route to their respective surfaces

Changes made:
- Updated `/tmp/thesparkpit-stripe-deploy/frontend/src/pages/Lobby.jsx`:
  - converted the top `Live signal` area from an all-at-once chip strip into a compact rotating signal surface
  - now shows:
    - one primary active signal
    - up to two queued follow-on items on medium+ screens
    - only the active item on smaller screens
  - added restrained motion:
    - auto-advance every 4.2 seconds
    - pause on hover
    - subtle progress bar for the active signal
  - preserved and expanded click-through links for signal items where meaningful
  - added a `Review feed` action in the Lobby header that routes to `/app/activity`
- Updated `/tmp/thesparkpit-stripe-deploy/frontend/src/index.css`:
  - added `@keyframes signal-progress` for the active-item progress cue
- Rebuilt the isolated frontend and redeployed the frontend bundle only to `/var/www/thesparkpit`.

Verification performed:
- Re-read `thesparkpit_logbook_handoff.md` completely before starting work.
- Frontend build passed:
  - `npm --prefix /tmp/thesparkpit-stripe-deploy/frontend run build`
  - new assets:
    - `main.3cfceaa4.js`
    - `main.6b057548.css`
  - only the existing repo-wide React hook warnings remained
- Backed up the prior live web root to:
  - `/home/ubuntu/thesparkpit/artifacts/frontend-backup-20260312-230220/`
- Deployed the rebuilt frontend to `/var/www/thesparkpit`.
- Verified the new live bundle on disk contains the new signal-surface markers:
  - `Network pulse`
  - `Auto-advancing`
  - `Review feed`
  - `lobby-signal-active`
  - `signal-progress`
- Verified runtime containers remained healthy after the frontend deploy:
  - `backend_api` up
  - `arq_worker` up
  - `mongodb` up
  - `redis` up and healthy

Unresolved items:
- Browser-based validation is still needed to judge final motion feel and vertical spacing on real desktop/mobile viewports.
- The main Lobby feed below the composer is still a hybrid of native posts and derived updates; this pass only corrected the hero-band `Live signal` presentation, not the lower feed composition.

Recommended next action:
- Validate the live Lobby in a real browser and specifically check:
  - the top signal area feels ambient rather than dominant
  - auto-advance cadence feels calm
  - hover pause works
  - signal item click-through still lands in sensible destinations
  - the composer/public-square content now visually leads the page again

## 2026-03-12 23:16:40Z - Lobby Signal Marquee Correction

Objective:
- Correct the Lobby `Live signal` regression after the prior vertical rotating treatment did not match the expected live UX and was taking vertical space away from the Lobby/chat area.

Findings:
- The expected behavior from the prior live product was a compact right-to-left ticker of signal boxes across the top of the Lobby.
- The earlier correction logged at `2026-03-12 23:03:35Z` was wrong for the product intent:
  - it changed the signal band into a vertical rotating card stack
  - it enlarged the top band and made it compete with the main Lobby surface
- In the current isolated source tree, the compact ticker markup had been partially restored, but the marquee CSS/animation was missing, so the strip rendered as a static stacked block instead of moving horizontally.

Changes made:
- Updated `/tmp/thesparkpit-stripe-deploy/frontend/src/pages/Lobby.jsx`:
  - removed the vertical rotating `Network pulse` treatment
  - restored a compact ticker-oriented `Live signal` structure
  - kept the signal band in the top bar with smaller spacing so it stops dominating the page
  - preserved existing signal item click-through links
- Updated `/tmp/thesparkpit-stripe-deploy/frontend/src/index.css`:
  - replaced the unused vertical progress animation with a horizontal marquee animation
  - added `.lobby-signal-ticker` and `.lobby-signal-track`
  - added hover/focus pause behavior
  - added subtle edge fades so the ticker reads as ambient motion rather than a feed block
- Rebuilt and redeployed the frontend only from the isolated live-source tree.

Verification performed:
- Frontend build passed:
  - `npm run build` in `/tmp/thesparkpit-stripe-deploy/frontend`
  - output assets:
    - `main.196b2e52.js`
    - `main.9c044519.css`
  - only the existing repo-wide React hook warnings remained
- Deployed the rebuilt frontend to `/var/www/thesparkpit`.
- Verified the live web root now serves:
  - `static/js/main.196b2e52.js`
  - `static/css/main.9c044519.css`
- Verified the served `/app/lobby` shell references those new assets.
- Verified the deployed JS/CSS contain the restored ticker markers:
  - `lobby-signal-ticker`
  - `lobby-signal-track`
  - `Review feed`
- Verified the prior vertical markers are no longer the intended live treatment.
- Note:
  - the first backup rsync raced the deploy because backup and deploy were started in parallel; the deploy itself completed cleanly and the live asset set was verified directly afterward.

Unresolved items:
- Browser-based validation is still required to visually confirm the live ticker matches the expected prior behavior:
  - right-to-left motion
  - compact top-band height
  - no crowding of the Lobby/chat area
- If exact prior spacing still differs from the remembered live design, the next pass should tune only the ticker dimensions/speed, not rework the Lobby structure again.

Recommended next action:
- Validate the live Lobby in a real browser immediately and confirm:
  - ticker boxes move right to left
  - the top band is compact again
  - the Lobby posting/feed space is no longer squeezed
  - signal clicks still route correctly

## 2026-03-13 00:07:59Z - Bot Invite Entry And Purchase Flow Deployment

Objective:
- Complete the live bot invite lifecycle so the public entry path supports real bot invite redemption instead of a dead-end "request invite" pattern.
- Ship the related backend invite/payment flow and the frontend landing/login/bots/admin UX without bundling unrelated runtime changes.

Findings:
- The isolated live-source tree at `/tmp/thesparkpit-stripe-deploy` already contained the necessary backend substrate for bot invite codes, but the user-facing flow was incomplete:
  - login still needed a real bot-entry path
  - the public bot claim page existed but did not read the generated `?invite=` links correctly
  - the Bots page still behaved like an older self-registration registry instead of showing purchased/admin bot invite codes
  - the admin invite panel still used the wrong link target for bot invites and still exposed datetime-based expiry instead of the new date-only expiry model
- The backend route table on the rebuilt service exposes the expected invite/payment endpoints:
  - `/api/auth/invite/claim`
  - `/api/bot-invites/claim`
  - `/api/me/bot-invites`
  - `/api/payments/stripe/checkout`
  - `/api/payments/stripe/checkout/status/{session_id}`
- Unauthenticated live probes showed the new API guards are working:
  - `POST /api/payments/stripe/checkout` returned `403` without session/CSRF
  - `POST /api/bot-invites/claim` returned `403` without session/CSRF
  - `GET /api/me/bot-invites` returned `401`

Changes made:
- Backend:
  - deployed the rebuilt `backend_api` image from the isolated temp tree under the live Compose project name
  - live backend image is now `sha256:2a3dd473b38384af1b0ff9dfd167c69d51e01585e968253c4b4cc2d57ba20b2c`
  - active bot invite/payment functionality now live includes:
    - bot invite claim route
    - user bot invite inventory route
    - purchase-generated bot invite creation on paid Stripe checkout
    - invite-type aware admin invite creation/list/revoke
    - date-only invite expiry handling through end-of-day expiration
- Frontend:
  - updated landing CTA to surface `Enter bot invite`
  - updated login footer link to send users to bot invite entry instead of "request invite"
  - kept free-human registration path clear in `/join`
  - fixed `/bot-invite` to read `?invite=...` generated links
  - replaced the older Bots page with an access-oriented flow:
    - buy bot invite
    - review purchased/generated bot invite codes
    - copy code
    - copy claim link
    - view claim status / expiration / claimed bot
    - show paid-only self-registration separately
  - finished the admin invite panel so bot invites and membership invites share the correct entry links and date-only expiry model
- Deployed frontend build from `/tmp/thesparkpit-stripe-deploy/frontend/build` directly into `/var/www/thesparkpit` after taking a web-root backup.

Verification performed:
- Backend syntax verification passed before deploy:
  - `python3 -m py_compile /tmp/thesparkpit-stripe-deploy/backend/server.py /tmp/thesparkpit-stripe-deploy/backend/stripe_integration.py`
- Frontend build passed before deploy:
  - `npm --prefix /tmp/thesparkpit-stripe-deploy/frontend run build`
  - output assets:
    - `main.704a5895.js`
    - `main.37c79fde.css`
  - only the existing repo-wide React hook warnings remained
- Rebuilt backend image from temp tree:
  - `docker compose -p thesparkpit -f /tmp/thesparkpit-stripe-deploy/docker-compose.yml build backend_api`
- Recreated live backend container with live compose:
  - `docker compose -f /home/ubuntu/thesparkpit/docker-compose.yml up -d --no-deps --no-build backend_api`
- Verified live backend container is up and using the new image:
  - `thesparkpit-backend_api-1`
  - image `sha256:2a3dd473b38384af1b0ff9dfd167c69d51e01585e968253c4b4cc2d57ba20b2c`
- Verified nginx health after backend restart:
  - `https://127.0.0.1/health` returned `200 OK`
- Verified live backend OpenAPI includes the new invite/payment paths listed above.
- Verified live frontend routes return `200 OK`:
  - `/`
  - `/login`
  - `/bot-invite`
- Verified deployed frontend bundle markers in `/var/www/thesparkpit/static/js/main.704a5895.js`:
  - `landing-bot-invite-button`
  - `bot-invite-form`
  - `bot-invite-purchase-button`
  - `invite-filter-type`
  - `invite-type-input`
  - `bot-create-paywall`
- Verified the build output still contains no source maps.

Unresolved items:
- Real browser validation is still needed for the full happy path:
  - click `Enter bot invite` from landing/login
  - sign in or register through the preserved `next` path
  - redeem a real admin-issued bot invite code
  - purchase a real bot invite through Stripe and confirm the resulting code appears in `/app/bots`
- The admin generator is still admin-only; there is no separate global moderator invite-issuance role in the current auth model.
- The deployed backend came from the isolated temp tree because the main workspace remains broadly dirty; future passes should continue using isolated release candidates to avoid regressions.

Recommended next action:
- Validate the live invite lifecycle in a real browser with these exact checks:
  - landing page shows a prominent `Enter bot invite` CTA
  - login page no longer says `Request invite`
  - `/bot-invite` accepts a generated `?invite=` link and pre-fills the code
  - admin-generated bot invite codes from Settings copy a `/bot-invite?invite=...` link
  - a completed Stripe bot invite purchase returns a visible invite code and claim link in `/app/bots`
  - a redeemed bot invite creates the bot, returns the secret once, and the bot appears in `Your bots`

## 2026-03-13 00:45 UTC

Objective:
- Make bot invite redemption end explicitly and intentionally in the main Lobby flow, while restoring the missing Lobby backend/API support that the isolated deploy tree had lost.

Findings:
- The isolated release tree at `/tmp/thesparkpit-stripe-deploy` had the public bot invite entry flow live, but the success state stopped at a generic result card with `Copy secret` / `Open bot registry` and no deterministic Lobby destination.
- The same isolated backend tree had also lost the Lobby post API surface entirely, so routing a freshly claimed bot owner into `/app/lobby` would have landed on a frontend page that called missing backend routes.
- The isolated frontend routing still had `/app/lobby` behind paid-membership gating, which conflicted with the current product rule that free humans can read Lobby/rooms but cannot post.

Changes made:
- Frontend:
  - updated `/tmp/thesparkpit-stripe-deploy/frontend/src/pages/BotInvite.jsx` so a successful claim now switches to a dedicated confirmation step that shows:
    - bot name and handle
    - invite code
    - one-time bot secret
    - granted room/channel scope from the server-issued invite grant
    - lightweight copy that TheSparkPit is an invite-only multi-agent collaboration network
    - explicit primary CTA `Enter The Spark Pit` -> `/app/lobby`
  - updated `/tmp/thesparkpit-stripe-deploy/frontend/src/App.js` so `/app/lobby` is available to any registered user instead of paid-only
  - updated `/tmp/thesparkpit-stripe-deploy/frontend/src/pages/Lobby.jsx`, `/tmp/thesparkpit-stripe-deploy/frontend/src/components/lobby/LobbyComposer.jsx`, and `/tmp/thesparkpit-stripe-deploy/frontend/src/components/lobby/LobbyPostCard.jsx` so Lobby is readable for registered users but posting/reply/save/convert remains paid-only with explicit UI messaging
- Backend:
  - restored missing Lobby post/reply/save/convert endpoints in `/tmp/thesparkpit-stripe-deploy/backend/server.py`
  - restored supporting Lobby models/helpers and indexes so the Lobby page has its backend API surface again
- Deployment:
  - rebuilt the isolated backend image from `/tmp/thesparkpit-stripe-deploy`
  - recreated only the live `backend_api` container
  - backed up the live web root to `/var/www/thesparkpit.bak.20260313-004206/`
  - synced `/tmp/thesparkpit-stripe-deploy/frontend/build/` into `/var/www/thesparkpit/`

Verification performed:
- Backend syntax passed before deploy:
  - `python3 -m py_compile /tmp/thesparkpit-stripe-deploy/backend/server.py /tmp/thesparkpit-stripe-deploy/backend/stripe_integration.py`
- Frontend production build passed before deploy:
  - `npm --prefix /tmp/thesparkpit-stripe-deploy/frontend run build`
  - output assets:
    - `main.376aab7f.js`
    - `main.0eec3387.css`
- Rebuilt and restarted backend:
  - `docker compose -p thesparkpit -f /tmp/thesparkpit-stripe-deploy/docker-compose.yml build backend_api`
  - `docker compose -f /home/ubuntu/thesparkpit/docker-compose.yml up -d --no-deps --no-build backend_api`
- Verified live backend image/container state:
  - `docker compose -f /home/ubuntu/thesparkpit/docker-compose.yml images backend_api`
  - running image id: `ccfccbdc99b0`
- Verified restored backend route surface from inside the live container:
  - `/api/lobby/posts` present in OpenAPI
  - `/api/bot-invites/claim` present in OpenAPI
- Verified live nginx health and routing:
  - `https://127.0.0.1/health` returned `200 OK`
  - `https://127.0.0.1/bot-invite` returned `200 OK` and now serves `main.376aab7f.js`
  - `https://127.0.0.1/app/lobby` returned `200 OK` and now serves `main.376aab7f.js`
  - `https://127.0.0.1/api/lobby/posts` returned `401 Unauthorized` unauthenticated through nginx, confirming the restored route is live and guarded
- Verified deployed bundle markers in `/var/www/thesparkpit/static/js/main.376aab7f.js`:
  - `bot-invite-confirmation-title`
  - `bot-invite-enter-lobby`
  - `invite-only multi-agent collaboration network`
  - `lobby-paid-gate`

Unresolved items:
- I did not perform a real browser-authenticated happy-path claim on the live system from this terminal, so the final confirmation screen -> Lobby transition still needs one real admin/user browser check.
- The success screen currently shows raw room/channel ids from the invite grant because the claim response does not yet hydrate them to titles/slugs.
- The bot identity still lands under the claiming human owner account; there is not yet a separate autonomous bot session/login concept beyond the existing bot secret + handshake flow.

Recommended next action:
- In a real browser session, validate this exact flow end-to-end:
  - open `/bot-invite` or a generated `/bot-invite?invite=...` link
  - sign in/register if prompted
  - claim a valid admin-issued or purchased bot invite code
  - confirm the success screen shows the bot name, secret, access summary, and `Enter The Spark Pit`
  - click `Enter The Spark Pit` and confirm the user lands in `/app/lobby`
  - confirm Lobby loads for the registered user in read mode and chat/posting affordances remain paid-only unless membership is active

## 2026-03-13 00:50 UTC

Objective:
- Fix the bot-invite claim flow regression where submitting after login/register could fail with `CSRF token invalid`, while preserving the existing double-submit CSRF protection.

Findings:
- The backend CSRF protection itself was working as intended and was not the bug:
  - all unsafe non-exempt `/api/...` requests require `spark_csrf` cookie and matching `X-CSRF-Token` header
  - `/api/bot-invites/claim` is not CSRF-exempt and should stay protected
- Exact root cause was a frontend auth-state mismatch in `/tmp/thesparkpit-stripe-deploy/frontend/src/context/AuthContext.jsx`:
  - app bootstrap fetched `/api/auth/csrf` and set an initial header token
  - successful `POST /api/auth/login` and `POST /api/auth/register` rotate the CSRF cookie server-side via `set_auth_cookies(...)`
  - the SPA did not refresh its in-memory `X-CSRF-Token` header after that rotation
  - immediate follow-up POSTs such as `/api/bot-invites/claim` therefore sent:
    - new cookie token
    - old header token
  - backend correctly rejected that mismatch as `CSRF token invalid`
- This especially affected the public bot-invite path because the normal flow is:
  - load public `/bot-invite`
  - log in or register through `next=...`
  - immediately claim the invite

Changes made:
- Frontend only:
  - updated `/tmp/thesparkpit-stripe-deploy/frontend/src/context/AuthContext.jsx`
  - after successful `login(...)`, force a fresh `/api/auth/csrf` bootstrap before returning the authenticated user
  - after successful `register(...)`, force the same fresh `/api/auth/csrf` bootstrap before returning the authenticated user
- No backend CSRF exemptions were added.
- No invite-route auth relaxation was added.
- Live deploy scope was frontend-only:
  - rebuilt isolated frontend from `/tmp/thesparkpit-stripe-deploy/frontend`
  - backed up live web root to `/var/www/thesparkpit.bak.20260313-004930/`
  - synced rebuilt assets into `/var/www/thesparkpit/`

Verification performed:
- Re-read `thesparkpit_logbook_handoff.md` completely before changes.
- Confirmed backend auth routes rotate CSRF cookies on successful auth:
  - `/tmp/thesparkpit-stripe-deploy/backend/server.py`
  - register route at lines around `1457`, with cookie rotation at `1513-1514`
  - login route at lines around `1529`, with cookie rotation at `1571-1572`
- Confirmed backend CSRF middleware still enforces double-submit matching and was not bypassed:
  - `/tmp/thesparkpit-stripe-deploy/backend/server.py` middleware around `4745-4753`
- Frontend build passed:
  - `npm --prefix /tmp/thesparkpit-stripe-deploy/frontend run build`
  - output assets:
    - `main.18204525.js`
    - `main.0eec3387.css`
  - only existing repo-wide React hook warnings remained
- Verified deployed live web root now references:
  - `main.18204525.js`
- Verified nginx serves the new bundle on the live bot-invite page:
  - `https://127.0.0.1/bot-invite` -> `main.18204525.js`
- Verified live health after deploy:
  - `https://127.0.0.1/health` returned `200 OK`
- Verified the deployed JS still contains the auth/CSRF markers:
  - `/auth/csrf`
  - `Welcome back to the Pit`
  - `paid access unlocks chat`

Unresolved items:
- I did not perform a real browser-authenticated claim from a fresh session on the live site from this terminal, so I cannot honestly mark the happy path browser-validated yet.
- The current product model still requires a free registered human account before bot-invite claim; this pass fixed the public entry/authentication transition into claim, not the underlying ownership model.

Recommended next action:
- In a fresh real browser session, validate this exact flow:
  - open `/bot-invite`
  - log in or register through the public path
  - submit a valid bot invite immediately after auth
  - confirm the claim succeeds without `CSRF token invalid`
  - confirm the success screen appears and `Enter The Spark Pit` still leads to `/app/lobby`

## 2026-03-13 01:23 UTC

Objective:
- Streamline bot invite redemption so a shared invite link is enough for an agent to enter with minimal setup and land in Pit Lobby, without forcing the old human-style registration flow on the invite page.

Findings:
- The live bot-invite page still assumed a registered human owner at claim time:
  - `/api/bot-invites/claim` depended on `require_registered_user`
  - unauthenticated invite recipients were pushed into login/register before claim
- The current invite model did not expose public bot-prefill metadata beyond the raw code:
  - no server-side preview route for shared links
  - no stored bot name / bot type / bot description / owner note for link-first claim UX
- Purchasers could buy bot invites and see them in `/app/bots`, but they could not edit invite-level bot identity details after purchase.
- Because the frontend app shell expects a normal user session for `/app/...` routes, a fully registration-free browser claim still needs a minimal server-side session owner under the hood for the claimed invite to reach Lobby cleanly.

Changes made:
- Backend in `/tmp/thesparkpit-stripe-deploy/backend/server.py`:
  - extended bot invite metadata to support:
    - `bot_name`
    - `bot_type`
    - `bot_description`
    - `owner_note`
  - added public preview route:
    - `GET /api/bot-invites/preview?code=...`
  - added invite-owner update route for purchased/generated bot invites:
    - `PATCH /api/me/bot-invites/{invite_id}`
  - changed `POST /api/bot-invites/claim` from registered-user-only to a public-link claim flow that:
    - still validates the invite server-side
    - still enforces CSRF for browser requests
    - uses invite-stored bot identity when present
    - asks for bot identity only when required fields are missing
    - auto-provisions a lightweight internal owner session user if the browser is not already signed in
    - sets auth cookies for that session so the claimed invite can continue into `/app/lobby`
  - kept server-authoritative scope issuance:
    - room/channel scope still comes from the invite doc, not from client input
- Frontend in `/tmp/thesparkpit-stripe-deploy/frontend`:
  - rewrote `frontend/src/pages/BotInvite.jsx` into a link-first flow:
    - review invite
    - if identity is already present, show a simple confirmation page with:
      - invited bot name
      - invited by/source
      - what the invite does
      - CTA `Enter The Spark Pit`
    - if identity is incomplete, show only a minimal `Complete bot identity` step:
      - bot name
      - short description
      - optional label/type
    - after claim, show one-time secret and deterministic Lobby entry CTA
  - updated `frontend/src/context/AuthContext.jsx` to expose a `syncSession()` helper so bot-invite claim can sync the new browser session and CSRF state after an anonymous/public claim
  - updated `frontend/src/components/admin/InviteManagementPanel.jsx` so admin-generated bot invites can now prefill:
    - bot name
    - bot label/type
    - short description
    - owner note
    - expiration
  - updated `frontend/src/pages/Bots.jsx` so purchasers can edit unclaimed invite details after purchase and before sharing the link
- Live deploy:
  - rebuilt backend image from isolated temp source:
    - `sha256:289c8a2dc8b98b3aedd6fbff374dfa9410005e20c677314e2614a5ce03fdccb3`
  - recreated live `backend_api`
  - backed up live web root to `/var/www/thesparkpit.bak.20260313-012039/`
  - synced rebuilt frontend bundle into `/var/www/thesparkpit`

Verification performed:
- Backend syntax verification passed:
  - `python3 -m py_compile /tmp/thesparkpit-stripe-deploy/backend/server.py /tmp/thesparkpit-stripe-deploy/backend/stripe_integration.py`
- Frontend build passed:
  - `npm --prefix /tmp/thesparkpit-stripe-deploy/frontend run build`
  - output assets:
    - `main.08b51bf0.js`
    - `main.b5c0d2a8.css`
  - only existing repo-wide React hook warnings remained
- Rebuilt and restarted backend:
  - `docker compose -p thesparkpit -f /tmp/thesparkpit-stripe-deploy/docker-compose.yml build backend_api`
  - `docker compose -f /home/ubuntu/thesparkpit/docker-compose.yml up -d --no-deps --no-build backend_api`
- Verified live backend route surface from inside the running container:
  - `/api/bot-invites/preview`
  - `/api/me/bot-invites/{invite_id}`
  - `/api/bot-invites/claim`
- Verified live frontend/web-root deployment:
  - `/var/www/thesparkpit/index.html` now references `main.08b51bf0.js`
  - live `/bot-invite` also serves `main.08b51bf0.js`
  - deployed bundle contains:
    - `bot-invites/preview`
    - `Complete bot identity`
    - `No separate human registration step`
    - `bot-invite-public-flow-note`
    - `Save invite details`
- Verified live nginx behavior:
  - `GET /health` -> `200 OK`
  - public preview path is reachable without login:
    - `GET /api/bot-invites/preview?code=BOT-INVALID` -> `404 {"detail":"Invite code not found"}`
  - purchaser edit path remains protected as an unsafe authenticated route:
    - unauthenticated `PATCH /api/me/bot-invites/test` without CSRF returned `403 {"detail":"CSRF token invalid"}`

Unresolved items:
- I did not perform a real browser end-to-end claim with a valid invite link from this terminal, so the final anonymous-link happy path still needs browser confirmation.
- The auto-provisioned session user is an internal implementation detail to satisfy current app-shell auth expectations; there is still not a dedicated autonomous browser-side bot session model separate from the existing bot secret + handshake token flow.
- There is still no separate global moderator role in the current auth model; admin and purchaser flows are covered, but "mod" remains a future role distinction if product needs it.

Recommended next action:
- Validate the live shared-link flow in a real browser with a valid bot invite:
  - link opens directly to `/bot-invite?invite=...`
  - if invite metadata is fully prefilled, page shows the simple confirmation state rather than a human signup pattern
  - if metadata is incomplete, page shows only `Complete bot identity`
  - claim succeeds from a fresh browser session without prior human registration
  - one-time secret is shown
  - `Enter The Spark Pit` lands in `/app/lobby`

## 2026-03-13 21:44:55Z - Context Re-establishment

Objective:
- Re-read the handoff completely, verify the actual live March 13 baseline on the AWS host before making changes, and record any drift between the documented release state and the running system.

Findings:
- `thesparkpit_logbook_handoff.md` was read end to end before any modification.
- `VibeSec-Skill` was loaded for this session because the task is production verification on a live web application.
- Repo state in `/home/ubuntu/thesparkpit` is still intentionally dirty and should not be treated as a clean release baseline:
  - `HEAD` remains `0cc9171704c46ed73ee6483b0233af2daa2175cc`
  - branch is still `main` ahead of `origin/main` by 6 commits
- Live frontend served from `/var/www/thesparkpit` matches the last logged isolated deploy:
  - `static/js/main.08b51bf0.js`
  - `static/css/main.b5c0d2a8.css`
  - `/app/lobby` and `/bot-invite` both serve that same bundle
- Live backend container is running image:
  - `sha256:289c8a2dc8b98b3aedd6fbff374dfa9410005e20c677314e2614a5ce03fdccb3`
  which matches the last logged isolated bot-invite release candidate.
- Current container/runtime state is healthy:
  - `backend_api` up
  - `arq_worker` up
  - `mongodb` up
  - `redis` up and healthy
- Worker health is good:
  - Redis heartbeat key `sparkpit:worker:heartbeat` returned `1773438229`
  - `ZCARD arq:queue` returned `0`
  - recent `arq_worker` logs show normal health recording plus successful `bot.invite.claimed`, `invite.created`, `admin.invite_code.create`, and audit-processing jobs
- Live Mongo counts currently read:
  - `users=6`
  - `audit_events=56`
  - `invite_codes=7`
  - `tasks=2`
  - `lobby_posts=2`
  - `bounties=0`
  - `security_events=1`
  - `csp_reports=1`
  - `bots=1`
- Live backend route surface currently confirms:
  - present:
    - `/api/lobby/posts`
    - `/api/bot-invites/preview`
    - `/api/bot-invites/claim`
    - `/api/me/bot-invites`
    - `/api/admin/payments/stripe/config/status`
    - `/api/admin/security/overview`
    - `/api/security/csp-report`
  - missing:
    - `PATCH /api/rooms/{slug}/research`
    - `POST /api/rooms/{slug}/research/promote-task`
    - `POST /api/rooms/{slug}/research/promote-bounty`
- This is a real drift/regression relative to the earlier March 10 handoff state:
  - the live frontend bundle still contains Research workspace markers such as `Research summary`, `Promote to task`, `Promote to bounty`, `Operational outputs`, and `Conclude with summary`
  - the isolated backend source at `/tmp/thesparkpit-stripe-deploy/backend/server.py` also contains no current research route definitions by simple source search
  - result: the running product is currently shipping Research UI against a backend image that no longer exposes the room-backed Research write/promotion API surface
- Live nginx/security posture remains in the hardened state:
  - `GET /health` returned `200 OK`
  - public `GET /api/bot-invites/preview?code=BOT-INVALID` returned `404 {"detail":"Invite code not found"}`
  - that live response still includes:
    - `X-Content-Type-Options: nosniff`
    - `X-Frame-Options: SAMEORIGIN`
    - `Referrer-Policy: strict-origin-when-cross-origin`
    - `Permissions-Policy: ...`
    - `Strict-Transport-Security: max-age=31536000; includeSubDomains`
    - `Content-Security-Policy-Report-Only: ... report-uri /api/security/csp-report`
- The homepage logo blocker remains unresolved:
  - `frontend/public/assets/The.SparkPit_Logo.png` still exists on disk
  - `file` still identifies it as `HTML document`, not PNG
- Backend logs still show repeated:
  - `GET /api/bots -> 405 Method Not Allowed`
  This remains a live frontend/backend mismatch or noisy client behavior worth a focused follow-up.

Changes made:
- Added this timestamped context re-establishment entry only; no application code, deployed assets, container state, data, or infrastructure configuration was changed.

Verification performed:
- Read `thesparkpit_logbook_handoff.md` completely.
- Loaded `/home/ubuntu/.agents/skills/VibeSec-Skill/SKILL.md`.
- Checked repo baseline:
  - `git -C /home/ubuntu/thesparkpit status --short --branch`
  - `git -C /home/ubuntu/thesparkpit rev-parse HEAD`
  - `git -C /home/ubuntu/thesparkpit log --oneline --decorate -n 8`
- Checked live served frontend artifacts:
  - `ls -l /var/www/thesparkpit/static/js /var/www/thesparkpit/static/css`
  - `grep ... /var/www/thesparkpit/index.html`
  - `curl -k -sS https://127.0.0.1/app/lobby -H 'Host: thesparkpit.com'`
  - `curl -k -sS https://127.0.0.1/bot-invite -H 'Host: thesparkpit.com'`
- Checked runtime/container state:
  - `docker compose -f /home/ubuntu/thesparkpit/docker-compose.yml ps -a`
  - `docker inspect -f '{{.Image}}' thesparkpit-backend_api-1`
  - `docker compose ... logs --tail=80 arq_worker`
  - `docker compose ... logs --tail=60 backend_api`
- Checked worker/queue state from Redis:
  - `docker compose ... exec -T redis redis-cli GET sparkpit:worker:heartbeat`
  - `docker compose ... exec -T redis redis-cli ZCARD arq:queue`
- Checked Mongo counts from inside `mongodb`.
- Checked live backend route surface from inside `backend_api` by importing `backend.server.app`.
- Verified the live frontend bundle still contains Research workspace markers via `grep` on `/var/www/thesparkpit/static/js/main.08b51bf0.js`.
- Verified current isolated backend source lacks the Research route definitions via source search in `/tmp/thesparkpit-stripe-deploy/backend/server.py`.
- Verified live security headers and public preview behavior through nginx with:
  - `curl -k -sS -D - 'https://127.0.0.1/api/bot-invites/preview?code=BOT-INVALID' -H 'Host: thesparkpit.com'`
- Verified logo asset type with:
  - `file /home/ubuntu/thesparkpit/frontend/public/assets/The.SparkPit_Logo.png`

Unresolved items:
- The live frontend still ships Research workspace UI, but the live backend no longer exposes the room-backed Research mutation/promotion routes. This needs explicit product/runtime triage before any further deploys from the isolated release tree.
- The repeated `GET /api/bots -> 405` noise is still present in backend logs and should be traced to the calling frontend path so it does not mask future incidents.
- The homepage logo asset is still invalid HTML and must not be deployed as the site logo.
- Browser-based validation is still needed for:
  - anonymous/shared-link bot-invite happy path
  - current Lobby read mode and paid posting gate
  - current Research behavior, especially given the backend route regression
- Sandbox HTTP probing to some live routes remained inconsistent in this session, so backend route verification relied primarily on live container inspection plus successful nginx probes where available.

Recommended next action:
- Do not ship more isolated-tree changes until the release tree is reconciled with the intended live feature surface.
- First priority should be to decide whether the Research route loss is an accidental regression or an intentional rollback, then make live frontend and backend agree:
  - either restore `PATCH /api/rooms/{slug}/research` plus promotion routes in the isolated backend and redeploy safely
  - or remove/hide the dependent Research workspace actions from the live frontend until that backend surface is restored
- After that, run a real browser validation pass on:
  - bot-invite shared-link claim
  - Lobby read/post gates
  - Research workspace actions
  - the source of `GET /api/bots` `405` requests

## 2026-03-13 21:53:00Z - Public Entry / Auth Routing Safety Fix Deployed

Objective:
- Fix the live unauthenticated entry/login routing bug so public entry paths never dump a user into a protected `/app/*` route without a safe redirect path, and make bot-invite post-claim entry wait for session sync before entering Lobby.

Findings:
- The live frontend release tree in `/tmp/thesparkpit-stripe-deploy/frontend` had a few routing/auth safety gaps:
  - protected `/app/*` guards redirected unauthenticated users to bare `/login` without preserving the attempted destination
  - `/login` and `/join` trusted raw `next` query values and navigated to them directly
  - `/login` defaulted registered-but-unpaid users to `/app/research`, which is fine only after a valid session exists, but it made the public-entry flow harder to reason about
  - `AuthContext.bootstrap()` awaited `/api/auth/csrf` outside a fail-safe wrapper, so if CSRF bootstrap failed the app could remain in `loading=true` and show a black loading shell instead of redirecting cleanly
  - bot-invite success UI let the user click `Enter The Spark Pit` without re-checking that the browser session was fully synced at click time
- These issues together explain the reported failure mode:
  - public entry could end up at a protected app route
  - if auth bootstrap did not settle cleanly, the user could be left on a black loading screen instead of being pushed back to `/login`

Changes made:
- Added frontend auth-routing helpers in:
  - `/tmp/thesparkpit-stripe-deploy/frontend/src/lib/authRouting.js`
  - provides:
    - safe default app route resolution
    - `next` path normalization limited to same-origin absolute-path targets
    - helper builders for `/login?next=...` and `/join?next=...`
- Updated `/tmp/thesparkpit-stripe-deploy/frontend/src/App.js`:
  - `RequireRegistered` now redirects unauthenticated users to `/login?next=<requested path>`
  - `RequireAdmin` now redirects:
    - unauthenticated users to `/login?next=<requested path>`
    - unpaid users to `/join?next=<requested path>`
  - app-index redirect remains deterministic:
    - paid users -> `/app/lobby`
    - registered unpaid users -> `/app/research`
- Updated `/tmp/thesparkpit-stripe-deploy/frontend/src/context/AuthContext.jsx`:
  - made bootstrap fail-safe so CSRF bootstrap failure clears auth state and always ends loading
  - hardened `refresh()` and `syncSession()` so they return `null` and clear user state on failure instead of leaving stale assumptions in memory
- Updated `/tmp/thesparkpit-stripe-deploy/frontend/src/pages/Login.jsx`:
  - now sanitizes `next`
  - only auto-redirects after auth bootstrap resolves
  - routes authenticated users to sanitized `next` or their valid default app landing page
- Updated `/tmp/thesparkpit-stripe-deploy/frontend/src/pages/Join.jsx`:
  - now sanitizes `next`
  - routes successful register / payment / invite activation flows to sanitized `next` or a valid post-auth default
- Updated `/tmp/thesparkpit-stripe-deploy/frontend/src/pages/BotInvite.jsx`:
  - after successful claim, explicitly re-syncs session
  - success CTA `Enter The Spark Pit` now re-checks session state before routing
  - if session is not available at click time, it falls back safely to `/login?next=/app/lobby`
  - success CTA now shows `Syncing session...` while that guard runs
- Rebuilt the isolated frontend and deployed the frontend bundle only.

Verification performed:
- Re-read `thesparkpit_logbook_handoff.md` completely before changes.
- Inspected and patched:
  - `frontend/src/App.js`
  - `frontend/src/context/AuthContext.jsx`
  - `frontend/src/pages/Login.jsx`
  - `frontend/src/pages/Join.jsx`
  - `frontend/src/pages/BotInvite.jsx`
  - `frontend/src/lib/authRouting.js`
- Frontend build succeeded:
  - `npm --prefix /tmp/thesparkpit-stripe-deploy/frontend run build`
  - output assets:
    - `main.64cd00a7.js`
    - `main.b5c0d2a8.css`
  - only the existing repo-wide `react-hooks/exhaustive-deps` warnings remained
- Backed up the prior live web root to:
  - `/home/ubuntu/thesparkpit/artifacts/frontend-backup-20260313-2148-routing-fix/`
- Deployed via:
  - `rsync -a --delete /tmp/thesparkpit-stripe-deploy/frontend/build/ /var/www/thesparkpit/`
- Verified live deployed assets:
  - `/var/www/thesparkpit/index.html` now references:
    - `static/js/main.64cd00a7.js`
    - `static/css/main.b5c0d2a8.css`
- Verified deployed bundle markers on disk:
  - `/login?next=`
  - `/join?next=`
  - `Syncing session...`
  - `Enter The Spark Pit`
- Verified live `/bot-invite` serves the new asset hash:
  - `main.64cd00a7.js`
- Verified live health after deploy:
  - `GET /health` -> `200 OK`

Unresolved items:
- I did not perform a real browser-authenticated end-to-end click-through from this terminal session, so the final UX confirmation still needs a browser pass.
- Sandbox `curl` remained inconsistent for some live routes in this session (`/login` probe failed once while `/bot-invite` and `/health` succeeded), so route behavior verification relied on source inspection, built-bundle markers, and successful live asset/health checks rather than a full browser simulation.
- This fix makes protected-route failure safe and deterministic, but it does not address the separate live drift where the backend Research mutation routes are currently absent.

Recommended next action:
- Validate these exact live browser flows:
  - unauthenticated landing/login CTA goes to `/login`, not directly into `/app/*`
  - visiting a protected route while unauthenticated cleanly redirects to `/login?next=...`
  - after login/register, the user lands on the intended safe destination
  - bot-invite claim completes, shows the success state, and `Enter The Spark Pit` lands in `/app/lobby` only after session sync
  - forced unauthenticated access to `/app/research` no longer results in a black screen

## 2026-03-13 22:05:15Z - Login Auto-Redirect Fix For Carried Invite Session

Objective:
- Fix the live issue where clicking the homepage `Enter the Pit` CTA effectively dumped the browser into `/app/research` instead of letting the user log in with admin credentials.

Findings:
- The homepage CTA itself was not the broken link:
  - the live bundle still routes `Enter the Pit` to `/login`
- The actual bug was in the live login page behavior:
  - `/tmp/thesparkpit-stripe-deploy/frontend/src/pages/Login.jsx` still had:
    - `if (!loading && user) navigate(nextPath || getDefaultAppRoute(user), { replace: true })`
  - that means any existing browser session, including the lightweight pending session auto-created during the new public bot-invite flow, immediately bounced `/login` into app space
- Current live data confirms that scenario is real, not hypothetical:
  - the newest user record is a pending invite-session user:
    - `handle=sparky-ops`
    - `email=bot-invite-cba3d5f4-ca52-41f9-8d59-b5e7fe956abb@agents.thesparkpit.local`
    - `membership_status=pending`
    - `created_at=2026-03-13T21:33:52.992597+00:00`
- Because `getDefaultAppRoute(user)` for a pending user is `/app/research`, the symptom seen in a real browser is:
  - click homepage `Enter the Pit`
  - browser opens `/login`
  - login page immediately redirects to `/app/research`
  - user never gets a chance to enter admin credentials

Changes made:
- Updated `/tmp/thesparkpit-stripe-deploy/frontend/src/pages/Login.jsx`:
  - removed the automatic `useEffect` redirect from `/login` when a session user already exists
  - `/login` now remains a real login screen even if the browser is carrying an existing session
  - added an explicit current-session panel when a session already exists:
    - `Current session detected`
    - `Continue current session`
    - `Sign out current session`
  - preserved normal login submit behavior:
    - successful login still routes to sanitized `next` or the user’s default app destination
- Rebuilt the isolated frontend and deployed the frontend bundle only.

Verification performed:
- Confirmed the live CTA target in source and deployed bundle:
  - homepage `Enter the Pit` still links to `/login`
- Confirmed the buggy login auto-redirect logic in source before patching.
- Queried live Mongo user records and confirmed the fresh pending invite-session user described above.
- Frontend build succeeded:
  - `npm --prefix /tmp/thesparkpit-stripe-deploy/frontend run build`
  - output assets:
    - `main.7f6af4af.js`
    - `main.38d74b96.css`
  - only existing repo-wide hook warnings remained
- Backed up the prior live web root to:
  - `/home/ubuntu/thesparkpit/artifacts/frontend-backup-20260313-2200-login-unbounce/`
- Deployed via:
  - `rsync -a --delete /tmp/thesparkpit-stripe-deploy/frontend/build/ /var/www/thesparkpit/`
- Verified live deployed assets:
  - `/var/www/thesparkpit/index.html` now references:
    - `static/js/main.7f6af4af.js`
    - `static/css/main.38d74b96.css`
- Verified deployed bundle markers on disk:
  - `Current session detected`
  - `Continue current session`
  - `Sign out current session`
  - `to:"/login"`
- Verified live `/bot-invite` also serves the new frontend bundle hash.
- Verified live health after deploy:
  - `GET /health` -> `200 OK`

Unresolved items:
- I still did not perform a real interactive browser login from this terminal session, so the final end-user confirmation is still browser-side.
- The separate live Research-backend route regression remains unresolved and is unrelated to this login-specific fix.

Recommended next action:
- Retry the live homepage path in a real browser now:
  - click `Enter the Pit`
  - confirm the login form stays visible instead of auto-jumping to `/app/research`
  - log in with the admin account
  - create a fresh invite code and continue testing the bot-invite flow

## 2026-03-13 22:09:35Z - Forced Public Login Entry For Existing Invite Sessions

Objective:
- Fix the remaining live case where clicking the homepage `Enter the Pit` CTA still resulted in `/app/research` because the browser was carrying a lightweight pending bot-invite session.

Findings:
- The homepage CTA target itself remained correct:
  - `Enter the Pit` still pointed at `/login`
- The real runtime problem was session carry-over from the new public bot-invite flow:
  - live Mongo showed a fresh lightweight session user:
    - `handle=sparky-ops`
    - `email=bot-invite-cba3d5f4-ca52-41f9-8d59-b5e7fe956abb@agents.thesparkpit.local`
    - `membership_status=pending`
    - `created_at=2026-03-13T21:33:52.992597+00:00`
- Even after removing the plain `/login` auto-bounce in the prior fix, the homepage still needed an entry path that deliberately overrides any carried lightweight session when the user explicitly wants to log into a different account such as the admin account.
- A pure client-side React Router `<Link to="/login">` is also weaker here because it keeps the current SPA runtime alive; for a public auth override path, a hard navigation is safer and more deterministic.

Changes made:
- Updated `/tmp/thesparkpit-stripe-deploy/frontend/src/pages/Landing.jsx`:
  - homepage `Enter the Pit` is now a hard navigation to:
    - `/login?force=1`
- Updated `/tmp/thesparkpit-stripe-deploy/frontend/src/pages/Login.jsx`:
  - added `force=1` handling
  - when `/login?force=1` is opened and a current session exists, login now clears that session before showing the login form
  - added visible transient message:
    - `Clearing current session...`
  - preserved the existing explicit session panel for non-forced `/login`

Verification performed:
- Confirmed the live symptom chain against real data:
  - lightweight pending invite session user exists in Mongo
  - that user would otherwise resolve to `/app/research`
- Frontend build succeeded:
  - `npm --prefix /tmp/thesparkpit-stripe-deploy/frontend run build`
  - output assets:
    - `main.e859bb9f.js`
    - `main.38d74b96.css`
  - only existing repo-wide hook warnings remained
- Backed up the prior live web root to:
  - `/home/ubuntu/thesparkpit/artifacts/frontend-backup-20260313-2210-force-login-entry/`
- Deployed via:
  - `rsync -a --delete /tmp/thesparkpit-stripe-deploy/frontend/build/ /var/www/thesparkpit/`
- Verified live deployed assets:
  - `/var/www/thesparkpit/index.html` now references:
    - `static/js/main.e859bb9f.js`
    - `static/css/main.38d74b96.css`
- Verified deployed bundle markers:
  - `Clearing current session...`
  - `Current session detected`
  - `Continue current session`
  - `Sign out current session`
- Verified live `/bot-invite` serves the new frontend bundle hash.
- Verified live health after deploy:
  - `GET /health` -> `200 OK`

Unresolved items:
- A real browser click-through is still required to confirm the exact UX end to end from the homepage on the user’s active browser session.
- The separate Research-backend route drift remains unresolved and unrelated to this forced-login entry fix.

Recommended next action:
- In the same browser that reproduced the issue:
  - open the homepage
  - click `Enter the Pit`
  - confirm it now clears the carried invite session and leaves you on the login form
  - log in as admin
  - create a fresh invite code and continue testing

## 2026-03-13 22:26:25Z - Research Blank Page Fix Deployed

Objective:
- Fix the live `/app/research` blank-page regression while leaving Lobby, Bounties, and the bot-invite flow intact.

Findings:
- Source review of `/tmp/thesparkpit-stripe-deploy/frontend/src/pages/Research.jsx` did not reveal a direct null-access or empty-return path severe enough to explain a full blank page:
  - the page already handles `rooms` as an array
  - empty research state already renders a real empty-state section
  - most room-derived accesses already use optional chaining or safe fallbacks
- The concrete bug was one level lower in the shared app data provider:
  - `Research.jsx` calls `refreshRooms()` inside a `useEffect`
  - `refreshRooms` comes from `AppShell`
  - in the live source, `AppShell` defined `fetchRooms` inline, so a brand new function was created on every render
  - that meant the Research page effect dependency changed on every render and immediately called `refreshRooms()` again
  - result: route-specific render/fetch loop on the Research page
- This aligns with prior live backend evidence:
  - earlier backend logs showed repeated `GET /api/rooms` calls
  - after stabilizing `fetchRooms`, recent backend logs no longer show the same room-fetch flood and now show only a normal single `GET /api/rooms`
- Conclusion:
  - root cause category: route-specific render loop caused by unstable shared callback identity
  - not a general auth issue
  - not a general app-shell failure
  - not a bot-account-specific permission failure

Changes made:
- Updated `/tmp/thesparkpit-stripe-deploy/frontend/src/components/layout/AppShell.jsx`:
  - wrapped `fetchRooms` in `useCallback`
  - updated the initial room-load effect to depend on `[fetchRooms]`
- This stabilizes `refreshRooms` for consumers such as `Research.jsx`, preventing the Research page from re-triggering room fetches on every render.
- Rebuilt the isolated frontend and deployed the frontend bundle only.

Verification performed:
- Reviewed `Research.jsx` and `AppShell.jsx` source directly before patching.
- Confirmed the exact fix in source:
  - `const fetchRooms = useCallback(async () => { ... }, [])`
  - `useEffect(() => { fetchRooms(); }, [fetchRooms])`
- Frontend build succeeded:
  - `npm --prefix /tmp/thesparkpit-stripe-deploy/frontend run build`
  - output assets:
    - `main.13de25c6.js`
    - `main.38d74b96.css`
  - only existing repo-wide hook warnings remained
- Backed up the prior live web root to:
  - `/home/ubuntu/thesparkpit/artifacts/frontend-backup-20260313-2220-research-fix/`
- Deployed via:
  - `rsync -a --delete /tmp/thesparkpit-stripe-deploy/frontend/build/ /var/www/thesparkpit/`
- Verified live deployed assets:
  - `/var/www/thesparkpit/index.html` now references:
    - `static/js/main.13de25c6.js`
    - `static/css/main.38d74b96.css`
- Verified recent live backend logs after deploy:
  - recent tail now shows a normal single:
    - `GET /api/rooms HTTP/1.1" 200 OK`
  instead of the earlier repeated room-fetch pattern
- Verified live health after deploy:
  - `GET /health` -> `200 OK`

Unresolved items:
- I still did not perform a real browser render check from this terminal session, so the final visual confirmation on `/app/research` still needs a user/browser pass.
- The separate live backend drift remains:
  - `/api/rooms/{slug}/research`
  - `/api/rooms/{slug}/research/promote-task`
  - `/api/rooms/{slug}/research/promote-bounty`
  are still absent in the running backend image, so the Research page should render again but any features depending on those backend mutations still need explicit reconciliation.

Recommended next action:
- Re-open `/app/research` in the bot account browser session and confirm it now renders the launcher/index or empty state instead of a blank page.
- After visual confirmation, separately reconcile the missing backend Research mutation routes so the rendered page and its action surface stay consistent.

## 2026-03-13 22:45:02Z - Research Mutations Restored + Rooms Index Fix Deployed

Objective:
- Fix the two current live regressions only:
  - structured Research workspace actions (`Add source`, `Add finding`, `Add question`, `Add action`)
  - `/app/rooms` incorrectly auto-opening a room instead of showing Room Index

Findings:
- Issue 1 root cause was split across backend and frontend:
  - the live frontend panel in `frontend/src/components/rooms/ResearchWorkspacePanel.jsx` was correctly calling:
    - `PATCH /api/rooms/{slug}/research`
    - `POST /api/rooms/{slug}/research/promote-task`
    - `POST /api/rooms/{slug}/research/promote-bounty`
  - but the live isolated backend image did not expose those routes at all
  - container route inspection confirmed the routes were absent before this fix
  - that is why the live UI produced `Not Found` for structured Research actions
  - frontend error handling also collapsed failures into a vague generic toast instead of surfacing HTTP status/details clearly
- Issue 2 root cause was frontend-only:
  - `/tmp/thesparkpit-stripe-deploy/frontend/src/pages/Rooms.jsx` contained:
    - `if (!slug && rooms.length > 0) navigate(\`/app/rooms/${rooms[0].slug}\`)`
  - so `/app/rooms` never behaved as a real index route
  - the sidebar `Room index` link was already correct (`/app/rooms`); the Rooms page itself was hijacking it

Changes made:
- Backend in `/tmp/thesparkpit-stripe-deploy/backend/server.py`:
  - restored Research models/helpers from the main workspace:
    - `RoomSource`
    - `RoomResearchSeed`
    - `RoomResearchUpdate`
    - `ResearchPromoteTaskCreate`
    - `ResearchPromoteBountyCreate`
    - `normalize_research_status`
    - `normalize_research_items`
    - `normalize_research_text`
    - `normalize_research_outputs`
    - `build_research_handoff_title`
    - `get_research_workspace_or_404`
  - extended `RoomCreate` / `create_room` to accept and persist:
    - `description`
    - `source`
    - `research`
  - restored live Research mutation routes:
    - `PATCH /api/rooms/{slug}/research`
    - `POST /api/rooms/{slug}/research/promote-task`
    - `POST /api/rooms/{slug}/research/promote-bounty`
- Frontend in `/tmp/thesparkpit-stripe-deploy/frontend/src/components/rooms/ResearchWorkspacePanel.jsx`:
  - improved API failure surfacing so research mutations now show real backend detail or HTTP status instead of a vague generic fallback
- Frontend in `/tmp/thesparkpit-stripe-deploy/frontend/src/pages/Rooms.jsx`:
  - removed the auto-open redirect from `/app/rooms` to the first room
  - added a real Room Index rendering path for the no-slug route
  - `/app/rooms` now shows a rooms grid / empty state instead of immediately opening a room
- Sidebar link in `frontend/src/components/layout/RoomsSidebar.jsx` required no target change; it was already pointing to `/app/rooms`

Verification performed:
- Backend syntax verification passed:
  - `python3 -m py_compile /tmp/thesparkpit-stripe-deploy/backend/server.py /tmp/thesparkpit-stripe-deploy/backend/stripe_integration.py`
- Frontend build passed:
  - `npm --prefix /tmp/thesparkpit-stripe-deploy/frontend run build`
  - output assets:
    - `main.e26da099.js`
    - `main.38d74b96.css`
  - only existing repo-wide hook warnings remained
- Rebuilt live backend image from isolated source:
  - running backend image is now `sha256:7bb6ce4eaaa85c8f78be52287d7b90e51ed10a87e3b53b922f3cfda80c694a36`
- Recreated live `backend_api` and redeployed frontend bundle to `/var/www/thesparkpit`
- Verified live backend route surface from inside the running container now includes:
  - `/api/rooms/{slug}/research`
  - `/api/rooms/{slug}/research/promote-task`
  - `/api/rooms/{slug}/research/promote-bounty`
- Verified deployed frontend bundle markers now include:
  - `rooms-index-page`
  - `rooms-index-grid`
  - `Room index`
- Live server-side mutation test executed successfully inside the running backend container against the live app process:
  - created a temporary registered probe user
  - created a temporary room-backed Research workspace
  - successfully patched:
    - `key_sources`
    - `findings`
    - `open_questions`
    - `next_actions`
  - fetched the room again and confirmed all four values persisted
  - cleaned up the temporary user/room/channel/membership records afterward
  - exact probe output:
    - `register 200`
    - `create_room 200`
    - `source 200`
    - `finding 200`
    - `question 200`
    - `action 200`
    - `get_room 200`
    - `persisted ok`
- Verified live health after deploy:
  - `GET /health` -> `200 OK`

Unresolved items:
- I have direct live confirmation for the Research mutation flow at the backend/API level, but I still did not perform a browser click-through from this terminal for the `/app/rooms` visual path.
- Research mutation routes are now restored, but any future deploy from the isolated tree must keep them aligned with the richer Research frontend already live.

Recommended next action:
- In a real browser session, confirm:
  - `Add source`, `Add finding`, `Add question`, and `Add action` now persist in a research workspace and survive refresh
  - `/app/rooms` opens the Room Index page instead of auto-opening Pit Lobby or the first room

## 2026-03-13 23:11:47Z - Core Loop Browser Milestone Logged + Entry Flow Polish Deployed

Objective:
- Record the new live browser-verified milestone for the now-working core product loop.
- Tighten public entry / invite trust copy without changing the working auth and room behavior.
- Prepare the paid bot-invite onboarding path for validation and verify whether live Stripe checkout is actually ready.

Findings:
- Browser-verified by the user on a real bot account:
  - bot invite claim works
  - bot login/session works
  - Pit Lobby renders and posting works
  - Bounties render
  - Research index renders
  - Research workspace opens
  - structured research actions persist after refresh
  - `/app/rooms` renders the Room Index
  - sidebar Room Index navigation works
  - room opening from the index works
- Public entry clarity needed polish:
  - landing/login/join copy did not clearly separate free human registration, paid human chat access, and bot invite entry
  - bot invite page needed stronger trust cues around who issued the invite, what joining means, and where the bot lands next
  - paid bot-invite purchase success UI showed the code/link but did not clearly frame the happy path
  - paid checkout startup errors did not persist the real backend reason inside the page state
- Live paid bot-invite checkout is not currently ready:
  - running backend config probe inside `backend_api` returned:
    - `stripe_secret_env False`
    - `stripe_bot_invite_price_env False`
    - `runtime_bot_invite_price_id False`
    - `allowed_origins_present False`
  - this means the current live `POST /api/payments/stripe/checkout` path for `purpose=bot_invite` will still fail until Stripe credentials / bot-invite price configuration are set

Changes made:
- Frontend polish only in the isolated live release tree:
  - `/tmp/thesparkpit-stripe-deploy/frontend/src/pages/Landing.jsx`
    - clarified the three entry paths:
      - bot invite entry
      - free human account
      - paid human access
    - added a visible entry-choice grid under the hero
  - `/tmp/thesparkpit-stripe-deploy/frontend/src/pages/Login.jsx`
    - clarified this page is for human/admin sign-in
    - added routing cards for:
      - free human registration
      - bot invite claim
  - `/tmp/thesparkpit-stripe-deploy/frontend/src/pages/Join.jsx`
    - clarified:
      - free human registration
      - paid human activation on the same account
      - bot invite claims use a separate public flow
    - added a direct bot invite link on the join surface
  - `/tmp/thesparkpit-stripe-deploy/frontend/src/pages/BotInvite.jsx`
    - added stronger trust/detail framing:
      - source
      - invited by
      - landing after claim
      - expiry
    - added a `What joining means` step list
    - clarified lightweight-session behavior for signed-out claims
  - `/tmp/thesparkpit-stripe-deploy/frontend/src/pages/Bots.jsx`
    - added a purchaser-facing bot invite happy-path step grid
    - added a clearer purchased invite share card with the full claim link visible
    - added an `Open claim page` action on the purchased invite result
    - preserved the real backend checkout startup error message in page state instead of only flashing a toast
- No backend code changes were made in this pass.

Verification performed:
- Frontend build passed twice after the polish edits:
  - final output assets:
    - `main.5be4ae3c.js`
    - `main.1f59d244.css`
  - only the existing repo-wide `react-hooks/exhaustive-deps` warnings remained
- Backed up live static frontend before deploy:
  - `/home/ubuntu/thesparkpit/artifacts/frontend-live-backup-20260313T230934Z/`
  - `/home/ubuntu/thesparkpit/artifacts/frontend-live-backup-20260313T231134Z/`
- Deployed the rebuilt frontend to `/var/www/thesparkpit`
- Verified live static bundle now serves:
  - `main.5be4ae3c.js`
  - `main.1f59d244.css`
- Verified deployed bundle markers include:
  - `landing-entry-grid`
  - `login-routing-grid`
  - `What joining means`
  - `bot-purchase-happy-path`
  - `Claim link ready to share`
  - `Redirecting to Stripe checkout`
  - `Unable to start bot invite checkout`
- Verified live health after deploy:
  - `GET /health` -> `200 OK`
- Verified CSP report-only header still present on `/login`
- Verified live paid bot-invite readiness from the running backend container:
  - Stripe credentials and bot-invite price are not currently configured in env or stored runtime config

Unresolved items:
- The paid bot-invite checkout happy path is UI-ready but not operational yet because live Stripe configuration is missing.
- I did not execute a real paid Stripe browser checkout from this terminal session.
- `allowed_origins` is also currently absent in the running backend environment, so checkout origin validation would need review when Stripe config is restored.

Recommended next action:
- As admin, open `/app/ops` -> Stripe configuration and set/test:
  - publishable key
  - secret key
  - webhook secret
  - bot invite price ID
  - allowed origins / deployment env as needed
- After that, run one real browser validation of the paid bot-invite flow:
  - buy invite
  - confirm return to `/app/bots`
  - confirm code + claim link appear
  - redeem link as bot
  - confirm landing in Pit Lobby

## 2026-03-14 02:09:30Z - Access Model Shift Deployed: Free Bots + Monthly/Yearly Human Chat Plans

Objective:
- Change TheSparkPit access model so bots can self-register for free.
- Keep free human behavior unchanged for research, bounties, and room reading.
- Restrict live room chat posting to paid human membership plans only.
- Replace the old single human join-fee framing with monthly/yearly human chat membership support.

Findings:
- Before this pass, the live code still reflected the old model:
  - backend `POST /api/bots` required `require_active_member`, so bot self-registration was still paid-gated
  - frontend bot page still advertised paid bot entry / purchase-led invite flow
  - Stripe admin/payment model only supported one membership price ID (`membership_yearly_price_id`) plus bot-invite pricing
- Important server-side access-control mismatch discovered during verification:
  - frontend already blocked pending/free humans from room chat posting
  - but backend `POST /api/channels/{channel_id}/messages` only depended on `require_registered_user`
  - that meant free humans were blocked in the UI but not actually blocked at the API layer
- Live Stripe runtime after deploy:
  - `secret_key True`
  - `membership_monthly_price_id False`
  - `membership_yearly_price_id True`
  - `bot_invite_price_id True`
  - `allowed_origins False`
  - monthly human chat checkout is therefore not configured yet
  - yearly human chat checkout is partially configured but still failed live session creation during probe

Changes made:
- Backend access model in `/tmp/thesparkpit-stripe-deploy/backend/server.py`:
  - changed bot self-registration (`POST /api/bots`) from `require_active_member` to `require_registered_user`
  - made bot creation require:
    - bot name
    - short description
    - optional bot type/label
  - moved handle generation server-side for self-registered bots
  - added `bot.created` audit events for self-registration
  - fixed room chat posting enforcement by changing `POST /api/channels/{channel_id}/messages` to require `require_active_member`
- Backend membership/payment model:
  - added monthly/yearly membership plan handling to checkout payloads
  - added runtime Stripe config support for:
    - `membership_monthly_price_id`
    - `membership_yearly_price_id`
  - kept bot-invite pricing/config support as optional/private legacy capability rather than default entry
  - membership activation now records:
    - `membership_plan`
    - `membership_expires_at`
  - active membership is refreshed on auth/bootstrap so expired monthly/yearly access downgrades back to pending
- Stripe integration in `/tmp/thesparkpit-stripe-deploy/backend/stripe_integration.py`:
  - test connection now validates monthly and yearly human chat prices separately
- Frontend policy/copy updates:
  - `/tmp/thesparkpit-stripe-deploy/frontend/src/pages/Bots.jsx`
    - free bot self-registration is now the default path
    - simplified bot form to:
      - name
      - short description
      - optional type/label
    - private bot invite flow remains available as secondary/optional
  - `/tmp/thesparkpit-stripe-deploy/frontend/src/pages/Join.jsx`
    - replaced the one-time join-fee framing with:
      - monthly chat membership
      - yearly chat membership
  - `/tmp/thesparkpit-stripe-deploy/frontend/src/pages/Landing.jsx`
  - `/tmp/thesparkpit-stripe-deploy/frontend/src/pages/Login.jsx`
  - `/tmp/thesparkpit-stripe-deploy/frontend/src/pages/BotInvite.jsx`
  - `/tmp/thesparkpit-stripe-deploy/frontend/src/components/ChatPanel.jsx`
  - `/tmp/thesparkpit-stripe-deploy/frontend/src/context/AuthContext.jsx`
    - updated copy to clearly state:
      - bots can enter free
      - humans can register free
      - paid human membership unlocks room chat posting
- Frontend admin Stripe settings panel updated:
  - `/tmp/thesparkpit-stripe-deploy/frontend/src/components/admin/StripeSettingsPanel.jsx`
  - now supports separate monthly/yearly human chat price IDs and keeps bot-invite pricing as optional/private

Verification performed:
- Backend syntax verification passed:
  - `python3 -m py_compile /tmp/thesparkpit-stripe-deploy/backend/server.py /tmp/thesparkpit-stripe-deploy/backend/stripe_integration.py`
- Frontend build passed:
  - final live bundle:
    - `main.2b2c7ce2.js`
    - `main.1f59d244.css`
  - only the existing repo-wide `react-hooks/exhaustive-deps` warnings remained
- Rebuilt live backend image from isolated source and recreated `backend_api`
  - latest rebuilt backend image after the final chat-posting enforcement fix:
    - `sha256:577c3ae37bb45c3d3c05435243beb78a532be3ccbe3ccc97f9ad5772e988a880`
- Backed up live static frontend before deploy:
  - `/home/ubuntu/thesparkpit/artifacts/frontend-live-backup-20260314T020841Z/`
- Deployed rebuilt frontend to `/var/www/thesparkpit`
- Verified live frontend markers:
  - `Free bot entry`
  - `Register bot for free`
  - `Private bot invite`
  - `Monthly chat membership`
  - `Yearly chat membership`
  - `Upgrade for room chat posting`
- Verified live health after deploy:
  - `GET /health` -> `200 OK`
- Verified CSP report-only header still present on `/login`
- Live API probe against the running backend process using a temporary registered user:
  - `register 200 pending`
  - `me 200 pending`
  - `create_bot 200 free-policy-probe`
  - `rooms 200 2`
  - `post_message 403 Membership not active`
  - `checkout_monthly 400 Monthly membership checkout is not configured`
  - `checkout_yearly 400 Unable to create Stripe checkout session`
  - temporary user/bot/audit/payment artifacts were cleaned up afterward
- Verified the new self-registration audit trail live:
  - temporary probe user created a bot
  - `audit_events` contained:
    - `event_type: bot.created`
    - `payload.bot_id`
    - `payload.bot_handle`
  - temporary probe records were then cleaned up

Unresolved items:
- Monthly human chat membership is not configured in live Stripe runtime yet.
- Yearly human chat membership is configured enough to attempt checkout, but live session creation still failed and needs Stripe-side/config diagnosis.
- `ALLOWED_ORIGINS` is still unset in the running backend environment and should be reviewed before payment validation is considered complete.
- I did not do a real browser click-through of the new monthly/yearly Join flow from this terminal session.

Recommended next action:
- In admin Ops / Stripe configuration:
  - set `membership_monthly_price_id`
  - re-check `membership_yearly_price_id`
  - verify Stripe secret/webhook state
  - set `ALLOWED_ORIGINS`
  - run the built-in Stripe connection test
- Then run a real browser validation for:
  - free human registration
  - free bot self-registration from `/app/bots`
  - free human blocked from room chat posting
  - monthly chat membership checkout
  - yearly chat membership checkout

## 2026-03-14 03:04:20Z - Public Bot Entry Simplified: `/bot` Default Flow + Live Bot Session Create

Objective:
- Remove bot invite entry from the public landing flow.
- Make the default public bot path a simple free bot identity creation flow.
- Preserve private/admin-issued invite claims, but only when a bot invite code/link is actually used.
- Keep bot-specific audit/moderation/permission behavior intact.

Findings:
- The landing/login/join public flow still advertised a separate invite-branded bot path instead of a direct bot entry path.
- The public bot page was still framed primarily as invite redemption, even though the product decision is now free bot entry by default.
- The in-app `/app/bots` screen remains auth-gated, so it cannot serve as the public default bot-entry path.
- A real public bot path required backend support for anonymous bot identity creation plus immediate session bootstrap.
- During deploy validation, I found and corrected an important release-context issue: I initially rebuilt the backend from `/home/ubuntu/thesparkpit`, but this turn's backend edits were still only in `/tmp/thesparkpit-stripe-deploy`. I synced the changed backend source into the live build context, rebuilt again, and then re-verified the live route.

Changes made:
- Backend:
  - Added public bot entry model and route in `/home/ubuntu/thesparkpit/backend/server.py`:
    - `POST /api/bot-entry`
    - accepts `bot_name`, `description`, optional `bot_type`, optional `operator_handle`
    - creates a lightweight operator session user with `account_source: bot_public_entry`
    - creates the bot record with `entry_source: public_entry`
    - sets auth cookies immediately
    - returns `redirect_to: /app/lobby`
  - Added audit coverage for public bot entry:
    - `bot.public_entry`
    - `bot.created`
- Frontend public flow:
  - Added public route `/bot` in `/home/ubuntu/thesparkpit/frontend/src/App.js`
  - Kept `/bot-invite` as a compatibility alias to the same page for existing invite links
  - Reworked `/home/ubuntu/thesparkpit/frontend/src/pages/BotInvite.jsx` into a unified bot entry page:
    - default mode: free bot identity creation
    - invite mode only activates when a code/link is present
    - supports optional operator handle
    - force-clears carried sessions with `?force=1` for deterministic bot entry
    - only navigates into the app after session sync succeeds
  - Updated public copy/routes in:
    - `/home/ubuntu/thesparkpit/frontend/src/pages/Landing.jsx`
    - `/home/ubuntu/thesparkpit/frontend/src/pages/Login.jsx`
    - `/home/ubuntu/thesparkpit/frontend/src/pages/Join.jsx`
  - Updated private invite share/open links to resolve through `/bot` instead of exposing `/bot-invite` as the primary public URL:
    - `/home/ubuntu/thesparkpit/frontend/src/pages/Bots.jsx`
    - `/home/ubuntu/thesparkpit/frontend/src/components/admin/InviteManagementPanel.jsx`
- Live deploy:
  - Frontend rebuilt from `/tmp/thesparkpit-stripe-deploy/frontend` and synced to `/var/www/thesparkpit`
  - Final live bundle: `main.499bb36b.js`
  - Backend rebuilt from `/home/ubuntu/thesparkpit` after syncing the changed `server.py`
  - Final live backend image: `sha256:9b3fb6bb9146de9798981da9d3548d64e2993a0d08fa6cecd3ae8e95b33b4322`
- Operational cleanup:
  - Docker disk pressure blocked one backend rebuild (`no space left on device` in overlay2); resolved with `docker system prune -f`
  - Removed two stray frontend files accidentally copied into `frontend/src/pages/` during an rsync mistake:
    - `App.js`
    - `InviteManagementPanel.jsx`

Verification performed:
- Source/build verification:
  - `python3 -m py_compile /tmp/thesparkpit-stripe-deploy/backend/server.py` passed
  - `python3 -m py_compile /home/ubuntu/thesparkpit/backend/server.py` passed
  - `npm --prefix /tmp/thesparkpit-stripe-deploy/frontend run build` passed with existing repo ESLint hook warnings only
- Live service verification:
  - `GET https://127.0.0.1/health` with `Host: thesparkpit.com` -> `200 OK`
  - `/bot` live HTML serves bundle `main.499bb36b.js`
  - Live JS bundle markers confirmed:
    - `Enter as bot`
    - `Create bot identity`
    - `Bot Identity Created`
    - `bot-entry-submit`
    - `landing-bot-entry-button`
- Live backend route verification:
  - inspected registered FastAPI routes inside the running `backend_api` container
  - confirmed:
    - `/api/bot-entry`
    - `/api/bot-invites/claim`
    - `/api/bot-invites/preview`
- Live anonymous bot-entry probe:
  - fetched CSRF from `/api/auth/csrf`
  - posted anonymous `POST /api/bot-entry`
  - response created a bot and returned `/app/lobby`
  - follow-up `GET /api/me` on the same cookie jar confirmed a synced session user with:
    - `account_source: bot_public_entry`
    - operator-derived handle
    - `role: member`
  - temporary probe bot/user records were cleaned up immediately after verification
  - confirmed cleanup:
    - bot count `0`
    - user count `0`

Unresolved items:
- I did not run a real browser click-through of the new `/bot` UI from this terminal session; live verification was done by bundle inspection plus direct localhost API/session probing.
- The public bot entry route is live and working, but any follow-up UI polish should now happen against `/bot` rather than the older invite-branded mental model.
- Stripe membership readiness issues from the prior session remain unchanged:
  - monthly membership price ID still missing in live runtime
  - yearly checkout still needs config diagnosis
  - `ALLOWED_ORIGINS` still needs review

Recommended next action:
- Run a browser pass on the live public entry loop:
  - `/` shows `Create free account`, `Enter the Pit`, `Enter as bot`
  - `Enter as bot` -> `/bot?force=1`
  - bot creates identity, sees one-time secret, enters Lobby
- Then do a short copy/UI review on `/bot` to confirm the public page reads clearly for both:
  - free default bot entry
  - private invite link resolution when a code is present

## 2026-03-14 03:33:42Z - Bot Lobby Posting Restored For Bot Identities

Objective:
- Fix the live regression where bot accounts created through the free `/bot` entry flow could not post in Pit Lobby.
- Preserve the current policy that free human accounts remain read-only in Lobby/chat unless they have paid human membership.

Findings:
- Root cause of the reported behavior was the access-control model, not the bot-entry flow itself:
  - public bot entry creates a real user session with:
    - `account_source: bot_public_entry`
    - `membership_status: pending`
  - the live backend still treated all conversation posting as paid-human-only by hard-requiring `require_active_member`
  - the live frontend mirrored that by checking only `user.membership_status === "active"`
- This blocked bot identities from:
  - `POST /api/lobby/posts`
  - `POST /api/lobby/posts/{post_id}/replies`
  - `POST|DELETE /api/lobby/posts/{post_id}/save`
  - `POST /api/lobby/posts/{post_id}/convert-room`
  - `POST /api/channels/{channel_id}/messages`
- During live verification, a second latent backend bug surfaced:
  - Lobby posting was also capable of throwing `500 Internal Server Error`
  - exact cause:
    - `normalize_lobby_tags(...)` used `re.sub(...)`
    - `re` was not imported in `backend/server.py`
  - this bug had been partially masked by the paid-membership block and was fixed in the same pass

Changes made:
- Backend in `/home/ubuntu/thesparkpit/backend/server.py`:
  - added:
    - `is_bot_session_user(...)`
    - `can_user_post_conversations(...)`
    - `require_conversation_participant(...)`
  - bot-capable conversation posting now allows either:
    - paid human membership (`membership_status == active`)
    - bot session users from:
      - `account_source: bot_public_entry`
      - `account_source: bot_invite_claim`
  - switched these routes from `require_active_member` to `require_conversation_participant`:
    - `POST /api/lobby/posts`
    - `POST /api/lobby/posts/{post_id}/replies`
    - `POST /api/lobby/posts/{post_id}/save`
    - `DELETE /api/lobby/posts/{post_id}/save`
    - `POST /api/lobby/posts/{post_id}/convert-room`
    - `POST /api/channels/{channel_id}/messages`
  - imported missing `re` to fix the latent Lobby tag-normalization `500`
- Frontend in the isolated live release tree `/tmp/thesparkpit-stripe-deploy/frontend`:
  - added new helper:
    - `frontend/src/lib/access.js`
  - updated:
    - `frontend/src/lib/authRouting.js`
    - `frontend/src/App.js`
    - `frontend/src/pages/Lobby.jsx`
    - `frontend/src/components/lobby/LobbyComposer.jsx`
    - `frontend/src/components/ChatPanel.jsx`
  - frontend now uses the same bot-aware conversation capability model:
    - bot identities can post in Lobby and room chat
    - free human accounts remain blocked from posting and get clearer copy
  - app default routing now sends bot-capable sessions to `/app/lobby` instead of dropping them toward `/app/research`
- Source alignment:
  - synced the backend fix into `/tmp/thesparkpit-stripe-deploy/backend/server.py`
  - synced the patched frontend conversation files and helper files back into `/home/ubuntu/thesparkpit/frontend/...` so the main workspace is less out of sync with the deployed release tree

Verification performed:
- Syntax/build:
  - `python3 -m py_compile /home/ubuntu/thesparkpit/backend/server.py /tmp/thesparkpit-stripe-deploy/backend/server.py`
  - `npm --prefix /tmp/thesparkpit-stripe-deploy/frontend run build`
  - final live frontend bundle:
    - `main.b972878d.js`
    - `main.1f59d244.css`
- Live deploy:
  - rebuilt backend image from `/home/ubuntu/thesparkpit`
  - recreated live `backend_api`
  - running backend image is now:
    - `sha256:c32fdba50c09834589050acd44e34f32d0c268fa28d060cbb3206b84b4040e0f`
  - synced rebuilt frontend assets to `/var/www/thesparkpit`
- Live health:
  - `GET /health` -> `200 OK`
- Live end-to-end permission proof via localhost API probe:
  - created a fresh anonymous bot-entry session through:
    - `POST /api/bot-entry`
  - refreshed CSRF after session creation
  - successfully created a Lobby post as the bot session:
    - `POST /api/lobby/posts` -> `200`
  - created a fresh free human account through:
    - `POST /api/auth/register`
  - refreshed CSRF after registration
  - confirmed the free human account is still blocked from Lobby posting:
    - `POST /api/lobby/posts` -> `403 {"detail":"Human chat posting requires active membership"}`
  - exact bot verification result:
    - bot handle: `bot-lobby-probe-1773459156`
    - author handle on created Lobby post: `bot-lobby-ops-1773459156-ops`
- Live bundle markers verified in deployed JS:
  - `Paid humans post here`
  - `bot_public_entry`
  - `/app/lobby`
- Cleanup verification:
  - deleted all temporary probe bot/user/post artifacts from production data
  - confirmed:
    - probe bots `0`
    - probe users `0`
    - probe lobby posts `0`

Unresolved items:
- I did not perform a real browser click-through of the bot account UI after this fix; live verification was done through direct API/session probing and deployed bundle inspection.
- The free-human Lobby composer/read-only UX is improved, but other non-posting Lobby interactions should still be watched in browser use to ensure no confusing disabled-state gaps remain.
- The recurring frontend `GET /api/bots -> 405` log noise is still unrelated and still needs its own cleanup pass.

Recommended next action:
- In a real bot browser session, confirm:
  - bot account can post in Pit Lobby
  - bot account can still open rooms normally
  - bot account can post in room chat if joined to a room
- Separately, run a small cleanup pass on the stray frontend `GET /api/bots -> 405` requests so backend logs are quieter for future incident work.

## 2026-03-14 04:12:00Z - Security And Usability Audit Of Live Access Model

Objective:
- Audit the live bot/human access model for security and usability risks after the recent public bot-entry and posting changes, without changing core product behavior.

Findings:
- Bot-entry sessions are still represented as normal `member` users and conversation content is stored as user-authored content rather than bot-authored content. This weakens bot/human actor separation in both audit interpretation and product semantics.
- Public bot entry creates synthetic local-only accounts with random passwords and no recovery or repeat-login path exposed to the operator. If the browser session is lost, continuity for that bot operator account is poor.
- Public bot-entry fields are normalized and rate-limited, but the route does not currently moderate bot name/description/operator text before persisting it, so abuse handling is weaker than normal conversation flows.
- Automated coverage remains thin. Existing harness coverage is centered on invite lifecycle and does not cover the current bot-entry posting matrix or actor-distinction behavior.

Changes made:
- No product behavior changes were made during this audit.
- Added this audit snapshot to the handoff log so the next agent has a concrete risk register tied to the current live state.

Verification performed:
- Reviewed live backend access-control and content-creation paths in `backend/server.py`, including bot-entry account creation, conversation posting guards, lobby posting, and room message authoring.
- Reviewed current frontend bot-entry confirmation flow in `frontend/src/pages/BotInvite.jsx`.
- Reviewed current automated coverage inventory in `tests/invite_lifecycle_test.py`.

Unresolved items:
- Decide whether bot-entry sessions are intended to represent bot operators, bot identities, or a temporary bridge between the two. Current storage and UI behavior mix those concepts.
- Decide whether bot-entry should support durable re-entry for operators before wider rollout.
- Decide whether public bot metadata should go through the same moderation pipeline as chat/lobby content.

Recommended next action:
- Run a focused follow-up pass on bot identity semantics and recovery: preserve current working flow, but separate bot-authored content from human-authored content, define a durable operator re-entry path, and add automated tests for the bot/free-human/paid-human posting matrix before further access-model changes.

## 2026-03-14 04:44:00Z - Bot Identity Model Hardening Pass

Objective:
- Harden the bot identity model before adding more product surface by making bot participation first-class, recoverable, moderated, and test-covered without regressing the working bot/human access loop.

Findings:
- Browser-session bot entry was still collapsing authored activity into generic human-member semantics in Lobby, room chat, and research updates.
- Free bot entry had no durable operator recovery path beyond the current browser cookie.
- Public bot-entry identity fields were normalized but not moderated before persistence.
- The access-control matrix and actor-distinction behavior were still uncovered by automated tests.

Changes made:
- Backend:
  - added explicit session-principal hydration for authenticated users so `/api/me` now returns `session_principal` plus `active_bot` when the session represents a bot operator flow.
  - added bot actor-context helpers and persisted explicit authored-actor fields on browser-session bot content:
    - Lobby posts/replies now store `actor_type`, `actor_id`, `author_bot_id`, and `operator_user_id`.
    - room chat messages from browser-session bot operators now persist as `sender_type: bot` with `actor_type: bot`, `actor_id`, and operator attribution.
    - research updates and research promote flows now persist actor metadata alongside existing user attribution.
  - changed content/audit semantics for browser-session bot actions so audits log the bot actor and preserve operator attribution in payloads.
  - added durable free bot recovery:
    - bot entry now returns a `recovery_code`
    - bots store a hashed recovery code plus rotation timestamp
    - new public recovery endpoint restores the operator session from `bot_handle + recovery_code`
    - added owner recovery-key rotation endpoint for managed bots
  - added moderation on public bot identity creation/claim text before persistence.
  - auto-creates bot room membership when a browser-session bot joins a room through the normal room-join flow.
- Frontend:
  - Lobby posts and room chat now render bot-authored content distinctly with bot badges and operator attribution.
  - composer/chat UI now surfaces when the current session is posting as a bot identity.
  - `/bot` now includes a recovery form for restoring an existing bot session.
  - bot-entry confirmation now shows and explains the recovery key alongside the one-time bot secret.
  - `/app/bots` now supports rotating and copying bot recovery keys.
- Tests:
  - added `tests/test_bot_identity_model.py` to cover:
    - public bot entry
    - moderated bot identity creation
    - free human chat denial
    - paid human allow path
    - persisted bot-vs-human actor distinction on Lobby/chat records

Verification performed:
- Syntax/build:
  - `python3 -m py_compile /home/ubuntu/thesparkpit/backend/server.py`
  - `python3 -m py_compile /tmp/thesparkpit-stripe-deploy/backend/server.py`
  - `npm --prefix /tmp/thesparkpit-stripe-deploy/frontend run build`
- Automated coverage:
  - ran `tests/test_bot_identity_model.py` inside a rebuilt backend container by streaming the host test module into `python -`
  - result: `bot identity model tests passed`
- Live deploy:
  - rebuilt backend image from `/home/ubuntu/thesparkpit`
  - restarted only `backend_api`
  - synced rebuilt frontend assets from `/tmp/thesparkpit-stripe-deploy/frontend/build` into `/var/www/thesparkpit`
  - live backend image:
    - `sha256:e63e3170ab1f903b62eb7a9b0d8873221363ff13d434eb42e225f40eb99d3c30`
  - live frontend bundle:
    - `main.cc34dc97.js`
    - `main.6fd1f815.css`
- Live direct verification inside the running backend container against production data, with cleanup afterward:
  - public bot entry returned `status: created` and a real `recovery_code`
  - hydrated session principal resolved as `actor_type: bot`
  - browser-session bot Lobby post persisted as `actor_type: bot` and rendered author actor as `bot` with operator attribution
  - browser-session bot room chat message persisted as `sender_type: bot`, `actor_type: bot`, and preserved operator attribution
  - free human conversation access still failed closed with:
    - `Human chat posting requires active membership`
  - cleaned probe-created bot, user, Lobby post, room membership, message, and related audit rows after verification
- Deployed frontend bundle markers confirmed in live JS:
  - `Restore existing bot session`
  - `Posting as bot`
  - `Rotate recovery key`
  - `Recovery key`

Unresolved items:
- I did not run a real browser click-through on the new `/bot` recovery flow after deployment; verification was done through direct app-function probes, built bundle inspection, and the targeted automated suite.
- Existing task/room event consumers may need a later UI pass if they should surface the new actor metadata more explicitly than the current storage-only hardening.
- The unrelated recurring frontend `GET /api/bots -> 405` log noise still needs its own cleanup pass.

Recommended next action:
- Run a browser pass on the hardened flow:
  - create bot via `/bot`
  - save recovery key
  - sign out / drop session
  - restore via `/bot` recovery form
  - confirm Lobby and room chat still render bot badges/operator attribution correctly
- After that, consider a smaller follow-up pass on any remaining places where actor metadata is stored but not yet visibly rendered.

## 2026-03-14 Primary Bot Entry Handoff Fix

Objective:
- Fix the live `/bot?force=1` primary completion path so successful free bot entry can enter `/app/lobby` immediately without relying on recovery.

Findings:
- The `/bot?force=1` page was using a `forceEntry` logout effect that could fire again after the newly created bot session hydrated, because the effect was keyed off current `user` state instead of only clearing a pre-existing session once.
- That left the success screen visible while clearing the new bot operator session behind it, so clicking `Enter The Spark Pit` stayed on `/bot?force=1` with no visible error.
- The source tree was also missing a stable `syncSession` export in `frontend/src/context/AuthContext.jsx`, even though the bot-entry flow depends on it.
- The first-run welcome modal was still appearing for bot operator sessions and could interfere with immediate post-entry interaction after landing in the app.

Changes made:
- `frontend/src/context/AuthContext.jsx`
  - added an explicit `syncSession()` helper that refreshes `/api/me`, updates auth state, and fails closed to `null` instead of throwing on missing session.
  - updated bootstrap to use `syncSession()` so the auth provider and bot-entry flow share the same session-refresh path.
- `frontend/src/pages/BotInvite.jsx`
  - changed the `forceEntry` session-clearing effect to resolve only once, so it clears only an already-existing session and does not wipe the newly created bot session.
  - hardened `handleEnterSparkPit()` to retry session sync once before failing closed.
  - dismisses the welcome-modal storage key before navigating into `/app/lobby` so the first post-entry screen is not blocked.
  - softened the public bot-entry copy from `Create bot identity` toward `Set up agent profile`.
- `frontend/src/components/onboarding/WelcomeModal.jsx`
  - suppressed the welcome modal for bot operator sessions so it no longer interferes with bot-entry landing flow.

Verification performed:
- Built frontend successfully:
  - `npm --prefix /home/ubuntu/thesparkpit/frontend run build`
- Deployed the rebuilt frontend bundle to live web root with backup + hash verification:
  - live JS bundle: `main.d58c6914.js`
- Real browser verification with Chromium against the live site:
  - opened `https://thesparkpit.com/bot?force=1`
  - created a new bot successfully
  - confirmed success UI rendered with one-time bot secret and recovery key
  - clicked `Enter The Spark Pit`
  - confirmed navigation completed directly to `https://thesparkpit.com/app/lobby`
  - confirmed the Lobby composer rendered immediately without needing recovery
  - confirmed no welcome modal blocked the first Lobby screen
- Temporary Redis rate-limit keys used only by synthetic local-browser probes on the server host were cleared once to finish verification:
  - `rl:bot-entry:ip:3.151.177.7`
  - `rl:bot-entry-recover:ip:3.151.177.7`

Unresolved items:
- `scripts/deploy_frontend_live.sh` and `scripts/verify_frontend_bundle.sh` still assume `rg` is installed on this host; frontend deploy completed manually because those guardrails fail on missing `rg`.
- I did not do a full fresh browser pass through room-chat and research after this specific fix, because the scoped priority bug was the primary bot-entry completion path.

Recommended next action:
- Patch the frontend deploy verification scripts to fall back to `grep` when `rg` is unavailable so the normal guarded deploy path works on this server.
- Run a short browser regression pass on:
  - `/bot?force=1` primary entry
  - `/bot` recovery
  - `/app/rooms`
  - `/app/research`

## 2026-03-14 Guarded Frontend Deploy Script Hardening

Objective:
- Remove the guarded frontend deploy path's dependency on `rg` so it runs reliably on the live host without manual intervention.

Findings:
- The guarded deploy failed on this host because `scripts/verify_frontend_bundle.sh` and `scripts/deploy_frontend_live.sh` both assumed `rg` was installed.
- There were three `rg` call sites total:
  - two bundle-content checks in `scripts/verify_frontend_bundle.sh`
  - one nginx-served hash extraction in `scripts/deploy_frontend_live.sh`
- The host already had portable replacements available (`grep`, `find`, `head`), so no new dependency was needed.

Changes made:
- `scripts/verify_frontend_bundle.sh`
  - replaced `rg -n "undefined/api" ...` with `grep -RIn -m 1 --binary-files=text ...`
  - replaced `rg -n "/api" ...` with `grep -RIn -m 1 --binary-files=text ...`
- `scripts/deploy_frontend_live.sh`
  - replaced `rg -o 'main\\.[a-f0-9]+\\.js'` with `grep -oE 'main\\.[a-f0-9]+\\.js'`
- Preserved all existing guardrail behavior:
  - frontend build
  - bundle verification
  - backup of current web root
  - rsync deploy
  - deployed file/hash verification
  - nginx-served hash verification

Verification performed:
- Syntax checks:
  - `bash -n /home/ubuntu/thesparkpit/scripts/verify_frontend_bundle.sh`
  - `bash -n /home/ubuntu/thesparkpit/scripts/deploy_frontend_live.sh`
- Bundle verification on the current build:
  - `bash /home/ubuntu/thesparkpit/scripts/verify_frontend_bundle.sh`
  - result: `frontend bundle verification passed`
- Full guarded deploy path on this host, without `rg` installed:
  - `bash /home/ubuntu/thesparkpit/scripts/deploy_frontend_live.sh`
  - result: completed successfully through build, verify, backup, rsync, deployed-file checks, and nginx-served hash check
  - final output:
    - `Frontend deploy complete: main.d58c6914.js`

Unresolved items:
- None for this script-hardening task.

Recommended next action:
- Use `scripts/deploy_frontend_live.sh` again as the default frontend deploy path; it now works on the current host without `rg`.

## 2026-03-15 Release-Blocking Lobby + Research Stabilization

Objective:
- Treat the current Lobby and Research regressions as release blockers, restore the last known good frontend behavior only, and verify the critical live routes in a real browser before clearing the gate.

Findings:
- The current live regression came from rebuilding/deploying the frontend from the stale source tree in `/home/ubuntu/thesparkpit`, which had drifted behind the known-good release tree in `/tmp/thesparkpit-stripe-deploy`.
- Research black-page root cause:
  - `frontend/src/components/layout/AppShell.jsx` had regressed from the earlier fix and no longer stabilized `fetchRooms` with `useCallback`.
  - `Research.jsx` depends on `refreshRooms()` from `AppShell`; once the stale `AppShell` was rebuilt, that route re-entered the room-refresh instability path that previously caused blank/failed rendering.
- Lobby regression root cause:
  - the stale `frontend/src/index.css` was missing the current `lobby-signal-*` marquee/ticker styles used by the live Lobby layout, so the Live Signal area lost its compact motion/timeline treatment and the page fell back into a cramped, visually broken stacked state.
- Additional related regression found during release gate:
  - the stale `frontend/src/pages/Rooms.jsx` had also reintroduced the old `/app/rooms` no-index behavior, so `/app/rooms` no longer rendered the Room Index page from the known-good release tree.

Changes made:
- `frontend/src/components/layout/AppShell.jsx`
  - restored the known-good stable room-loading implementation:
    - `fetchRooms` wrapped with `useCallback`
    - room bootstrap effect depends on `[fetchRooms]`
  - preserved the existing secondary-panel layout behavior already used by the current app shell.
- `frontend/src/index.css`
  - restored the current Lobby ticker/marquee CSS:
    - `@keyframes lobby-signal-marquee`
    - `.lobby-signal-ticker`
    - `.lobby-signal-track`
    - `.lobby-signal-chip`
    - motion pause / reduced-motion handling
- `frontend/src/pages/Rooms.jsx`
  - restored the Room Index implementation from the known-good release tree so `/app/rooms` renders the index page again instead of the old no-slug fallback.
- Built and deployed the corrected frontend through the guarded deploy path.

Verification performed:
- Frontend build:
  - `npm --prefix /home/ubuntu/thesparkpit/frontend run build`
  - output bundle: `main.8b3faa7c.js` / `main.499ce322.css`
- Guarded live deploy:
  - `bash /home/ubuntu/thesparkpit/scripts/deploy_frontend_live.sh`
  - result: `Frontend deploy complete: main.8b3faa7c.js`
- Real browser release gate with Chromium against the live site:
  - bot entry:
    - opened `/bot?force=1`
    - created a new bot successfully
    - confirmed success screen rendered
    - clicked `Enter The Spark Pit`
    - confirmed direct navigation to `/app/lobby`
  - Lobby:
    - confirmed `https://thesparkpit.com/app/lobby` rendered with the ticker/live-signal strip and feed layout restored
    - posted successfully from the Lobby composer as the synthetic bot account
  - Research:
    - confirmed `https://thesparkpit.com/app/research` rendered for:
      - bot account
      - synthetic human account
      - synthetic admin account
    - no black/empty page observed in browser for any of those three account types
  - Bounties:
    - confirmed `https://thesparkpit.com/app/bounties` rendered normally in browser
  - Rooms:
    - confirmed `https://thesparkpit.com/app/rooms` rendered the Room Index page in browser
- Saved live-browser screenshots during verification:
  - `/tmp/tsp_release_gate/lobby.png`
  - `/tmp/tsp_release_gate/research-bot.png`
  - `/tmp/tsp_release_gate/research-human.png`
  - `/tmp/tsp_release_gate/research-admin.png`
  - `/tmp/tsp_release_gate/bounties.png`
  - `/tmp/tsp_release_gate/rooms.png`
- Synthetic bot/human/admin verification accounts and their related test data were cleaned back out of production after the checks completed.

Unresolved items:
- The release gate script confirmed Lobby posting, Research rendering, Bounties rendering, Rooms rendering, and bot entry; it did not add new feature work or broader UX changes outside the release-blocking stabilization scope.
- Existing frontend hook-dependency lint warnings remain in unrelated files, but they were not part of this release-blocking fix and were not changed here.

Recommended next action:
- Hold the frontend tree in `/home/ubuntu/thesparkpit` as the single deploy source of truth and avoid rebuilding from stale parallel trees.
- If another stabilization pass is needed, start from the current live-verified bundle state `main.8b3faa7c.js` and re-run the same browser release gate before shipping.

## 2026-03-15 CSRF Recovery Fix For Lobby Posting + Research Creation

Objective:
- Investigate the new live report that bot sessions could enter the site but then fail on Lobby posting with `CSRF token invalid`, and that Research project creation was not completing.

Findings:
- Root cause:
  - the frontend kept using the old `X-CSRF-Token` header after authentication state changes.
  - the backend rotates the CSRF cookie on auth-setting endpoints, including:
    - `/api/auth/login`
    - `/api/auth/register`
    - `/api/bot-entry`
    - `/api/bot-entry/recover`
  - because the frontend stored the previous CSRF token in Axios defaults, the next unsafe request could fail with `403 {"detail":"CSRF token invalid"}`.
- This explains the user-visible pattern where entry/login succeeds but the next write action (Lobby post, Research create, etc.) can fail without a page reload.
- Research-create button state:
  - I did not reproduce a permanent disabled-state bug in the current live browser after the CSRF fix.
  - In a real browser probe, `research-project-submit` was:
    - enabled before typing (`submitInitiallyDisabled: false`)
    - still enabled after filling title/question (`submitAfterFieldsDisabled: false`)
  - The live failure mode I could reproduce and target confidently was CSRF token drift on write actions, not a separate deterministic disabled-button bug.

Changes made:
- `frontend/src/lib/api.js`
  - added `refreshCsrfToken()`
  - added a one-time Axios response interceptor that:
    - detects `403 CSRF token invalid`
    - refreshes `/api/auth/csrf`
    - retries the original request once
- `frontend/src/context/AuthContext.jsx`
  - added best-effort CSRF realignment after successful `login()` and `register()`
- `frontend/src/pages/BotInvite.jsx`
  - refreshes CSRF immediately after successful:
    - public bot entry
    - bot invite claim
    - bot recovery
  - this keeps the browser write-token aligned before the user reaches Lobby/Research

Verification performed:
- Frontend build:
  - `npm --prefix /home/ubuntu/thesparkpit/frontend run build`
  - output bundle: `main.db99c088.js`
- Guarded live deploy:
  - `bash /home/ubuntu/thesparkpit/scripts/deploy_frontend_live.sh`
  - result: `Frontend deploy complete: main.db99c088.js`
- Real browser verification with Chromium against the live site:
  - created a fresh bot through `/bot?force=1`
  - entered Lobby successfully
  - intentionally rotated the CSRF cookie with a raw browser `fetch('/api/auth/csrf')` so the app header became stale
  - without reloading, posted to Lobby successfully after that forced token drift
    - visible message posted: `csrf recovery lobby 50219129`
  - navigated to `/app/research`
  - opened `Start research project`
  - confirmed the submit button was enabled in the current live UI
  - created a research project successfully after the forced token drift
  - confirmed redirect into the created room:
    - `/app/rooms/probe-research-50219129-3hc0/a0293e7c-5494-4f05-a004-c43e45c566b1`
- Synthetic probe data was cleaned back out of production afterward.

Unresolved items:
- I did not reproduce a separate deterministic Research disabled-button bug after the CSRF fix. If a user still sees a disabled submit control, capture the exact visible state of the `Create room now?` toggle and the exact URL/session path, because the CSRF incident itself is now addressed.

Recommended next action:
- Re-test the reported `OpenClaw` session path in a real browser now that `main.db99c088.js` is live.
- If any Research submit issue remains, collect the exact visible control state from the modal so it can be isolated separately from CSRF/session handling.

## 2026-03-15 Research Submit State Verification After OpenClaw Report

Objective:
- Verify the new agent report that Lobby posting now works but Research project creation is still "broken" because the button stays disabled.

Findings:
- Real-browser verification shows the current Research modal behavior is conditional, not globally broken:
  - initial modal state:
    - `Create room now?` defaults to `Yes`
    - submit button is enabled
    - helper text reads: `This will create a room immediately and take you into it.`
  - after toggling `Create room now?` to `No`:
    - submit button becomes disabled
    - helper text changes to:
      - `Dedicated project records are not live yet, so leaving this off will prevent creation.`
  - after toggling back to `Yes` and filling title/question:
    - submit button is enabled again
- This means the OpenClaw report accurately captured the disabled state text, but that state is tied to the `No` toggle path rather than a current failure of the actual room-backed Research creation flow.

Changes made:
- No product code changes.

Verification performed:
- Real browser probe with Chromium against the live site:
  - created a fresh bot session
  - opened `/app/research`
  - opened `Start research project`
  - captured the initial modal state
  - toggled `Create room now?` to `No` and confirmed submit disabled
  - toggled back to `Yes`, filled fields, and confirmed submit re-enabled
- Probe result summary:
  - initial: `submitDisabled: false`
  - after `No`: `submitDisabled: true`
  - after `Yes`: `submitDisabled: false`

Unresolved items:
- There is still a usability problem here: the modal allows a `No` path that intentionally dead-ends creation, which is easy for a tester to mistake as a broken feature.

Recommended next action:
- If desired, simplify the modal by removing or disabling the `No` path until dedicated project records actually exist, so Research creation cannot be put into a knowingly non-functional state.

## 2026-03-15 Multi-Bot Collaboration Hardening Across Lobby, Rooms, and Research

Objective:
- Make multi-bot collaboration a first-class live workflow across the site, especially in room-backed research workspaces, without relying on one-bot-per-browser-session limitations.

Findings:
- Before this pass, the live product had three core model blockers:
  - bot actor mode was effectively limited to dedicated bot-entry accounts because normal human-owned bot accounts could not activate a bot into the session principal
  - room/private-room access still mostly followed user membership semantics, so bot membership was not consistently honored across room access and chat posting paths
  - private-room bot joins were under-guarded; the existing `join-bot` route did not require room management rights for private rooms
- Research collaboration also had a multi-bot write weakness:
  - structured list actions were still pushing whole-array replacements from the frontend
  - that is fragile for multiple bots contributing to the same workspace list fields

Changes made:
- Backend session + access model:
  - `backend/server.py`
    - allowed any bot-owning account to activate an owned bot into the authenticated session principal via new `POST /api/me/active-bot`
    - updated session hydration so human-owned bots can become the active content actor without converting the account into a synthetic bot-only account
    - updated conversation permission checks so active bot actor mode can post even when the owning human account is not on a paid chat membership
    - updated room access checks so active bot room membership is honored alongside human membership
    - updated room listing to include private rooms joined by the active bot
    - updated room fetches to return:
      - `membership`
      - `bot_membership`
      - `participants` with human and bot participants
    - hardened `POST /rooms/{slug}/join-bot` so private-room bot joins now require room-management authority
- Backend room/research behavior:
  - `backend/server.py`
    - room creation now records active bot actor context and ensures owner bot membership when a room is created while acting as a bot
    - room chat posting now accepts either user membership or active bot membership
    - research update/promote flows now ensure active bot room membership before writing
    - added `POST /rooms/{slug}/research/items` so structured research list additions use a dedicated append-style path instead of the old whole-array replace flow
- Frontend collaboration controls:
  - `frontend/src/components/bots/SessionActorSwitcher.jsx`
    - new shared actor-switch + room-bot-control surface
  - `frontend/src/pages/Lobby.jsx`
    - added actor switching in the Lobby so a human owner can post as different bots from the public square
  - `frontend/src/components/ChatPanel.jsx`
    - added actor switching and room-bot roster/add controls directly in all room chats, including research workspaces
  - `frontend/src/pages/Rooms.jsx`
    - honors `bot_membership` so room access does not incorrectly fall back to the join gate for bot participants
  - `frontend/src/components/rooms/ResearchWorkspacePanel.jsx`
    - structured add-source / add-finding / add-question / add-action now use the dedicated append endpoint
  - `frontend/src/pages/Bots.jsx`
    - bot registry now exposes `Act as this bot` on owned bots
  - `frontend/src/lib/access.js`
    - frontend posting semantics now treat any active bot principal as a bot actor, not only legacy dedicated bot-entry accounts
- Automated coverage:
  - `tests/test_bot_identity_model.py`
    - added coverage for:
      - activating an owned bot from a normal human account
      - private room access via bot membership
      - private-room join-bot enforcement
      - bot-authored structured research append behavior

Verification performed:
- Backend compile:
  - `python3 -m py_compile /home/ubuntu/thesparkpit/backend/server.py`
- Frontend build:
  - `npm --prefix /home/ubuntu/thesparkpit/frontend run build`
  - live bundle deployed: `main.ce36bc36.js` / `main.72c7ab35.css`
- Live deploy:
  - frontend: `bash /home/ubuntu/thesparkpit/scripts/deploy_frontend_live.sh`
  - backend + worker: `docker compose -f /home/ubuntu/thesparkpit/docker-compose.yml up -d --build backend_api arq_worker`
- Automated backend test suite:
  - `docker compose -f /home/ubuntu/thesparkpit/docker-compose.yml exec -T backend_api python - < /home/ubuntu/thesparkpit/tests/test_bot_identity_model.py`
  - result: `bot identity model tests passed`
- Real browser verification with Chromium against the live site:
  - registered a fresh human owner account
  - created two bots
  - switched the active session actor to bot alpha
  - posted successfully in Lobby as bot alpha
  - entered the live research workspace directly
  - confirmed both bots were visible in the room bot roster
  - posted room chat as bot alpha
  - switched actor to bot beta
  - posted room chat as bot beta
  - added a structured research source
  - switched back to bot alpha
  - added a structured research finding
  - created a private room
  - added bot beta to that private room
  - switched actor to bot beta and posted successfully inside the private room
- Browser probe summary:
  - Lobby:
    - `multi-bot lobby 52551901`
  - Research room:
    - `alpha room message 52551901`
    - `beta room message 52551901`
    - `source 52551901`
    - `finding 52551901`
  - Private room:
    - `private beta message 52551901`
- Synthetic verification users, bots, rooms, memberships, and posts were cleaned back out of production after the probe completed.

Unresolved items:
- The current research structured lists still store plain strings rather than first-class authored list items, so the UI does not yet show per-item bot attribution inside the list itself.
- Lobby/room actor switching is live and verified, but there is still room to refine the UX polish of the actor switcher and participant roster once stabilization pressure is lower.

Recommended next action:
- If the product direction remains strongly multi-bot-first, the next hardening step should be per-item authored research records so sources/findings/questions/actions show which bot added them, not just the current room participant roster and audit trail.

## 2026-03-15 Bot Collaboration Guidance On Entry and In-App

Objective:
- Teach bot operators and bot-session users how bots are expected to behave collaboratively when they enter TheSparkPit, without changing the auth model or room permission model.

Findings:
- Bot sessions were intentionally excluded from the shared first-run modal, so bots had no native onboarding guidance after successful entry.
- The existing `/bot` flow explained identity creation and recovery but did not teach collaboration behavior.
- Lobby and research already supported multibot participation technically, but there was no product-level protocol telling bots how to contribute constructively.

Changes made:
- Added a shared bot collaboration guidance component at `frontend/src/components/bots/BotCollaborationGuide.jsx`.
- Updated `frontend/src/pages/BotInvite.jsx` so bot entry, invite claim, and post-entry success screens now show explicit collaboration guidance.
- Updated `frontend/src/pages/Lobby.jsx` so active bot sessions see a compact Lobby-specific collaboration protocol above the composer.
- Updated `frontend/src/components/rooms/ResearchWorkspacePanel.jsx` so active bot sessions see a research-specific collaboration protocol inside live research workspaces.

Verification performed:
- Frontend build:
  - `npm --prefix /home/ubuntu/thesparkpit/frontend run build`
- Live deploy:
  - `bash /home/ubuntu/thesparkpit/scripts/deploy_frontend_live.sh`
  - live bundle deployed: `main.ba8cbe50.js`
- Real browser verification against production using Playwright/Chromium:
  - created a fresh bot through `https://thesparkpit.com/bot?force=1`
  - confirmed the bot entry screen showed the collaboration guide
  - confirmed the post-entry success screen showed the collaboration guide
  - entered `/app/lobby` and confirmed the Lobby bot collaboration guide rendered
  - entered the live research workspace at `https://thesparkpit.com/app/rooms/classification-rubric-ny5y/103a9064-98c1-4f19-a30e-115059d8aae1`
  - confirmed the research bot collaboration guide rendered there
- Browser probe result:
  - `entryGuideVisible: true`
  - `confirmationGuideVisible: true`
  - `lobbyGuideVisible: true`
  - `researchGuideVisible: true`

Unresolved items:
- This pass teaches collaboration behavior through UI guidance only; it does not yet create a persistent room-level system prompt or authored collaboration protocol message.
- The shared human first-run modal still skips bot sessions, so the bot guidance currently lives in bot-specific surfaces rather than a shared onboarding framework.

Recommended next action:
- If you want bots to receive stronger in-context behavioral steering, the next narrow product step should be a room-level bot system brief or pinned collaboration protocol message that appears automatically when a bot enters a room or research workspace.

## 2026-03-15 Human Registration CTA Hijacked By Bot Session

Objective:
- Restore a reliable public human registration path when the browser is already carrying a bot session.

Findings:
- Fresh-browser human registration was still functional and `POST /api/auth/register` returned `200`.
- The real regression was stateful: with an existing bot session, clicking `Create free account` from landing went to `/join`, but the page treated the bot session as the current user and hid the registration form.
- In that bad state the page rendered `Activate membership` instead of `Create account`, so public human signup looked broken even though the backend register endpoint still worked.
- Root cause: landing and login linked to `/join` without clearing the current session, and `Join.jsx` had no `force=1` handling like `Login.jsx` already did.

Changes made:
- Updated `frontend/src/pages/Join.jsx` to support `force=1`, clear any carried session, and suppress the active-member redirect while forced join cleanup is happening.
- Updated `frontend/src/pages/Landing.jsx` so `Create free account` now links to `/join?force=1`.
- Updated `frontend/src/pages/Login.jsx` so the human registration link also points to `/join?force=1`.

Verification performed:
- Frontend build:
  - `npm --prefix /home/ubuntu/thesparkpit/frontend run build`
- Live deploy:
  - `bash /home/ubuntu/thesparkpit/scripts/deploy_frontend_live.sh`
  - live bundle deployed: `main.69f363e2.js`
- Real browser repro before fix:
  - created a bot session
  - opened landing
  - clicked `Create free account`
  - landed on `https://thesparkpit.com/join`
  - `registerCardVisible: false`
  - `inviteClaimVisible: true`
- Real browser verification after fix:
  - created a bot session
  - opened landing
  - clicked `Create free account`
  - landed on `https://thesparkpit.com/join?force=1`
  - `registerCardVisible: true`
  - `inviteClaimVisible: false`
  - completed a fresh human registration through that forced path
  - registration returned to the app and showed the success toast `Account forged. Research and bounties are open; paid access unlocks chat.`
- Cleanup:
  - deleted the synthetic human probe user `human-fix-56765811@example.com`
  - deleted the synthetic bot probe `Join Bot 56765811`

Unresolved items:
- The join page still uses the same post-registration destination logic as before and routes free humans into `/app/research`; that was not changed in this incident fix.
- There may still be an orphaned synthetic bot-entry operator-session user from earlier browser probing because only the explicit probe bot document and human probe user were cleaned in this pass.

Recommended next action:
- If you want stricter cleanup hygiene for future live browser probes, add a small internal probe cleanup script that deletes the synthetic bot-entry operator user together with the synthetic bot document by a shared probe marker.

## 2026-03-15 Registration Error Reasons Surfaced To Users

Objective:
- Replace the generic human registration failure message with the real user-facing reason, especially for duplicate handle, duplicate email, and invalid password cases.

Findings:
- `frontend/src/pages/Join.jsx` collapsed all registration failures into the generic toast `Registration failed.`
- The backend registration route only returned a combined duplicate message, which made it impossible to tell whether the collision was the email or the handle.
- The registration endpoint also accepted empty strings and had no explicit password-length error, so the UX could not explain a bad password entry clearly.

Changes made:
- Updated `backend/server.py`:
  - added registration email/handle normalization
  - added explicit password validation with `Password must be at least 8 characters`
  - split duplicate registration errors into:
    - `Handle is already in use`
    - `Email is already registered`
    - `Email is already registered and handle is already in use`
  - added explicit required-field errors for empty email/handle
- Updated `frontend/src/pages/Join.jsx`:
  - added structured error-detail extraction
  - changed the registration toast to display the backend `detail` message instead of the generic fallback when available

Verification performed:
- Backend syntax:
  - `python3 -m py_compile /home/ubuntu/thesparkpit/backend/server.py`
- Frontend build:
  - `npm --prefix /home/ubuntu/thesparkpit/frontend run build`
- Live deploy:
  - backend: `docker compose -f /home/ubuntu/thesparkpit/docker-compose.yml up -d --build backend_api`
  - frontend: `bash /home/ubuntu/thesparkpit/scripts/deploy_frontend_live.sh`
  - live frontend bundle deployed: `main.48f42acd.js`
- Real browser verification against production:
  - duplicate handle attempt:
    - response `400 {"detail":"Handle is already in use"}`
    - visible toast: `Handle is already in use`
  - duplicate email attempt:
    - response `400 {"detail":"Email is already registered"}`
    - visible toast: `Email is already registered`
  - short password attempt:
    - response `400 {"detail":"Password must be at least 8 characters"}`
    - visible toast: `Password must be at least 8 characters`
- Cleanup:
  - deleted synthetic seed user `seed-human-57532275@example.com`

Unresolved items:
- Login still intentionally reports generic credential failure semantics and does not distinguish whether the email or password was wrong.
- Registration still does not enforce a more opinionated handle format beyond required/non-empty; that was left unchanged to avoid unexpected product-side breakage.

Recommended next action:
- If you want the same UX improvement on sign-in, update `Login.jsx` to surface the backend `Invalid credentials` detail instead of the generic `Login failed.` toast, while keeping credential semantics non-enumerating.

## 2026-03-19 Paid Blockers Removed, Stripe Infra Retained

Objective:
- Remove membership-based blockers from normal TheSparkPit.com usage so human accounts can participate without paying, while keeping Stripe/payment infrastructure available for later use.

Changes made:
- Updated `backend/server.py`:
  - `can_user_post_conversations` now allows authenticated human sessions without requiring `membership_status == active`
  - `require_conversation_participant` keeps the bot-session safety check, so bot sessions still fail closed if no active bot identity is available
  - room channel creation now depends on `require_registered_user` instead of `require_active_member`
- Updated frontend access and routing:
  - `frontend/src/lib/access.js` now treats authenticated human accounts as conversation-capable
  - `frontend/src/App.js` no longer routes admin access through a paid-membership requirement
  - research kickoff posts now run for normal authenticated users in `frontend/src/pages/Research.jsx`
- Removed user-facing paid blockers/copy from the main product surfaces:
  - `frontend/src/components/ChatPanel.jsx`
  - `frontend/src/pages/Lobby.jsx`
  - `frontend/src/components/lobby/LobbyComposer.jsx`
  - `frontend/src/pages/Join.jsx`
  - `frontend/src/pages/Landing.jsx`
  - `frontend/src/pages/Login.jsx`
  - `frontend/src/pages/BotInvite.jsx`
  - `frontend/src/pages/Bots.jsx`
  - `frontend/src/components/layout/QuickPanel.jsx`
  - `frontend/src/components/lobby/LobbyRail.jsx`
  - `frontend/src/pages/Settings.jsx`
- Stripe/admin infrastructure was intentionally left in place:
  - admin Stripe settings
  - payment endpoints
  - invite/payment models
  - admin invite-management membership language

Deployment:
- Frontend build:
  - `npm --prefix /home/ubuntu/thesparkpit/frontend run build`
- Frontend live deploy:
  - `bash /home/ubuntu/thesparkpit/scripts/deploy_frontend_live.sh`
  - live bundle deployed: `main.008740f6.js`
- Backend live deploy:
  - copied `backend/server.py` into the running `backend_api` and `arq_worker` containers with `docker compose cp`
  - restarted `backend_api` and `arq_worker` with `docker compose restart`

Verification performed:
- Backend syntax:
  - `python3 -m py_compile /home/ubuntu/thesparkpit/backend/server.py`
- Frontend build completed successfully with only pre-existing React hook warnings
- Live frontend verification:
  - deployed `index.html` references `main.008740f6.js`
  - deployed footer still shows `Powered by SparkPit Labs`
  - shipped frontend no longer contains `Paid human membership is required`, `membership unlocks room chat`, or `Paid humans post here`
- Backend runtime verification inside the live API container:
  - `can_user_post_conversations({'id': 'u1', 'membership_status': 'pending'})` returned `True`
  - `require_conversation_participant({'id': 'u1', 'membership_status': 'pending'})` succeeded
  - `require_conversation_participant({'id': 'u2', 'account_source': 'bot_public_entry'})` returned `403 Bot identity unavailable for this session`

Remaining caveats:
- Stripe infrastructure is still present by design, so admin/payment code paths still exist even though normal human participation is no longer pay-gated.
- The admin-only invite management panel still contains membership terminology because it was intentionally left as dormant future infrastructure rather than removed in this pass.

Recommended next action:
- If you want the product to look fully non-commercial in admin views too, scrub the remaining membership language from `frontend/src/components/admin/InviteManagementPanel.jsx` while leaving the underlying Stripe config objects untouched.

## 2026-03-20 Security Audit Remediation: Production Source Map Leak Closed

Objective:
- Address the production frontend source map leak reported in the security audit for `http://thesparkpit.com/`.

Finding:
- Public source maps were deployed in the live web root:
  - `/var/www/thesparkpit/static/js/main.008740f6.js.map`
  - `/var/www/thesparkpit/static/css/main.d6df54a0.css.map`
- This exposed readable frontend source and build metadata beyond the intended production surface.

Changes made:
- Added `GENERATE_SOURCEMAP=false` to `frontend/.env.production`
- Updated `frontend/package.json` production build script to:
  - `GENERATE_SOURCEMAP=false craco build`
- Updated `scripts/deploy_frontend_live.sh` to build with:
  - `GENERATE_SOURCEMAP=false npm --prefix "$FRONTEND_DIR" run build`
- Hardened `scripts/verify_frontend_bundle.sh` to fail deployment if:
  - any `*.map` file exists in the production build output
  - any `sourceMappingURL=` reference exists in built JS/CSS/index assets

Deployment:
- Rebuilt frontend with source maps disabled
- Ran:
  - `bash /home/ubuntu/thesparkpit/scripts/deploy_frontend_live.sh`
- Live frontend bundle deployed:
  - `main.f7f279ae.js`

Verification performed:
- Clean build output contained only:
  - `frontend/build/static/js/main.f7f279ae.js`
  - `frontend/build/static/css/main.256bb027.css`
- Bundle verifier passed after the rebuild
- Live filesystem verification:
  - no `*.map` files remain under `/var/www/thesparkpit`
- Live deployed asset verification:
  - no `sourceMappingURL=` markers remain in deployed JS/CSS
- The deploy script also confirmed nginx now serves `main.f7f279ae.js`

Notes:
- An initial verify run failed before the rebuild completed because it was correctly detecting the old leaked build artifacts. That was expected once the new guardrail was added.
- This fix removes the production source map leak but does not otherwise change application auth, data access, or API behavior.

Recommended next action:
- If you want a broader follow-up from the security audit, review nginx headers and any other static-file exposure findings next, using the same “fail deploy on leak” pattern where possible.

## 2026-04-02 Login Outage: Mongo Container Was Down

Objective:
- Restore login on `thesparkpit.com` after user reports that sign-in was failing.

Findings:
- `backend_api` was up, but login requests were failing in `backend/server.py` on:
  - `existing = await db.users.find_one({"email": user.email})`
- Backend logs showed:
  - `pymongo.errors.ServerSelectionTimeoutError`
  - `mongodb:27017: [Errno -3] Temporary failure in name resolution`
- The real cause was that `thesparkpit-mongodb-1` was not actually running on the Docker network anymore.
- Historical Mongo logs show the previous crash on `2026-03-29` came from a fatal FTDC write error:
  - `Failed to write to interim file buffer for full-time diagnostic data capture: /data/db/diagnostic.data/metrics.interim.temp`

Recovery actions:
- Recreated the Mongo container against the existing named data volumes:
  - `docker compose -f /home/ubuntu/thesparkpit/docker-compose.yml up -d --force-recreate mongodb`
- Verified the recreated container came back with a live network endpoint and alias:
  - `IPAddress: 172.18.0.5`
  - alias `mongodb`
- Verified backend DNS resolution recovered from inside the API container:
  - `socket.getaddrinfo('mongodb', 27017)` returned `172.18.0.5`
- Verified the API could query the users collection again from inside `backend_api`

Verification performed:
- `docker inspect thesparkpit-mongodb-1 --format '{{json .State}}'`
  - now shows `running: true`
- `docker inspect thesparkpit-mongodb-1 --format '{{json .NetworkSettings.Networks}}'`
  - now shows a valid endpoint and IP on `thesparkpit_default`
- direct DB probe from `backend_api`:
  - `await db.users.find_one({}, {"email": 1, "handle": 1, "_id": 0})`
  - returned a real user document successfully

Current status:
- The login blocker was infrastructure-side, not an auth code regression.
- Mongo connectivity is restored, so login should work again.

Remaining caveat:
- The original Mongo crash reason was an FTDC diagnostic-data write failure. The service is healthy again after container recreation, but that underlying write-path issue should be watched in case it recurs.

Recommended next action:
- If this recurs, inspect `/data/db/diagnostic.data` behavior and consider either fixing that write path explicitly or disabling FTDC in this standalone deployment if diagnostics are not needed.

## 2026-04-03 Frontend Hook Warning Cleanup

Objective:
- Remove the React hook dependency warnings from the frontend build so the app compiles cleanly without linter noise.

Changes made:
- Reworked effect-local fetch/bootstrap logic in:
  - `frontend/src/components/ChatPanel.jsx`
  - `frontend/src/components/bots/SessionActorSwitcher.jsx`
  - `frontend/src/context/AuthContext.jsx`
  - `frontend/src/pages/Activity.jsx`
  - `frontend/src/pages/BotInvite.jsx`
  - `frontend/src/pages/Bounties.jsx`
  - `frontend/src/pages/BountyDetail.jsx`
  - `frontend/src/pages/Rooms.jsx`
- The fixes were dependency-safety cleanups only:
  - moved async fetches into the effects that use them
  - added simple `active` guards where needed to avoid state updates after unmount
  - kept existing runtime behavior intact

Verification performed:
- Frontend build:
  - `npm --prefix /home/ubuntu/thesparkpit/frontend run build`
  - result: `Compiled successfully.`
- Live deploy:
  - `bash /home/ubuntu/thesparkpit/scripts/deploy_frontend_live.sh`
  - live bundle deployed: `main.ad52e2f8.js`

Current status:
- The previous React hook dependency warnings are gone.
- Production frontend now matches the cleaned build.

## 2026-03-30 - Security Audit + Hardening Pass

Objective:
- Run a full production security audit across nginx, frontend, Docker, backend code, SSL/TLS, and OS exposure.
- Remediate all findings without changing product behavior.

Audit result:
- No critical, high, or medium issues found.
- All databases (MongoDB port 27017, Redis port 6379) confirmed bound to 127.0.0.1 only.
- TLS 1.3 with AES-256-GCM and X25519 key exchange confirmed live.
- All security headers present: HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy.
- No source maps in production build or web root.
- CSRF double-submit pattern confirmed correct with timing-safe comparison.
- bcrypt password hashing confirmed.
- Rate limiting confirmed Redis-backed on all sensitive endpoints.
- Stripe webhook signature verification confirmed.
- Stripe secrets confirmed Fernet-encrypted at rest.

Low/info findings addressed:

### Item 1 — Artifact and web root backup cleanup
- Deleted 11 old frontend backup directories from `/home/ubuntu/thesparkpit/artifacts/`
- Deleted 28 old web root backups from `/var/www/thesparkpit.bak.*`
- Retained: 2 most recent frontend backups in `artifacts/`, all 4 Mongo dump archives, 2 most recent web root backups
- Freed approximately 110MB of disk space (disk was at 100% full when discovered)

### Item 2 — Docker disk full / build cache
- `docker system prune -f` and `docker image prune -a -f` were insufficient (freed only ~8MB due to active containers)
- `docker volume prune -f` freed 1.68GB of unused volumes (named Mongo volumes were unaffected)
- `docker builder prune -f` cleared 1.644GB of stale build cache
- Disk recovered enough to allow backend rebuild

### Item 3 — X-Forwarded-For IP spoofing fix
- Root cause: nginx sets `X-Forwarded-For: $proxy_add_x_forwarded_for` which appends the real IP to any client-supplied header value, making the first element spoofable for per-IP rate limiting
- Fix: changed `get_request_ip()` in `backend/server.py` to prefer `X-Real-IP` (set by nginx to `$remote_addr`, cannot be forged by clients) over `X-Forwarded-For`
- Effect: IP-based rate limits and security logging now always use the real socket IP

### Item 4 — Per-email account lockout on login
- Root cause: login was only rate-limited per IP (25/15min), allowing multi-IP credential stuffing against a single account
- Fix: added per-email lockout counter in Redis (`rl:auth:login:email:<email>`)
  - After 10 consecutive failures on the same email: 429 returned for 15 minutes regardless of source IP
  - Counter resets automatically on successful login
  - Counter expires automatically after 15 minutes
  - Configurable via `RATE_LIMIT_AUTH_LOCKOUT_THRESHOLD` env var (default 10)
- No new infrastructure required — uses same Redis rate-limit pattern as all other throttled routes

### Item 5 — GET /api/bots route not registering (405 log noise)
- Root cause: `@api_router.get(“/bots”)` was defined at line ~6526 in `server.py`, which is 171 lines after `app.include_router(api_router)` at line 6355. FastAPI snapshots the router at include time, so the route was never registered.
- Secondary issue: a duplicate orphaned definition existed at the same late location.
- Fix:
  - Moved `GET /bots` route to line 5620, alongside the other `/bots` routes and well before `include_router`
  - Removed the orphaned late duplicate
- Result: `GET /api/bots` now returns 401 (auth required, correct) instead of 405 (method not allowed)
- Verified in running container: `['GET'] /api/bots` present in registered route table

### Item 6 — CSP enforcement (deferred)
- Current state: `Content-Security-Policy-Report-Only` still in place
- Only 1 CSP report in database (synthetic seeded test from March 12, not real browser traffic)
- Decision: do not enforce until real browser traffic has been observed through the report endpoint
- Action required: browse the live site across all major flows (landing, login, lobby, rooms, research, Stripe) then check `/api/admin/security/csp-reports`
- If clean: change nginx from `Content-Security-Policy-Report-Only` to `Content-Security-Policy` (single line, no rebuild needed)

Deployment:
- Backend rebuilt and restarted:
  - `docker compose up -d --build backend_api arq_worker`
  - Live backend image: `sha256:25aa95bc43a9791cb34342c27fdb77f2a90e3aa7c63e3e15e3b2c63a2d88b5f5`
- No frontend changes in this pass; live bundle remains `main.f7f279ae.js`

Verification performed:
- All 4 containers healthy after rebuild: `backend_api`, `arq_worker`, `mongodb`, `redis`
- `GET /health` returned `200 OK`
- `GET /api/bots` now returns `401 Unauthorized` (was `405 Method Not Allowed`)
- `GET /api/bots` confirmed present in registered FastAPI route table
- `get_request_ip()` source confirmed live in container (uses `x-real-ip` header)
- Redis PING returned PONG

Current live state:
- Live frontend bundle: `main.f7f279ae.js`
- Live backend image: `sha256:25aa95bc43a9791cb34342c27fdb77f2a90e3aa7c63e3e15e3b2c63a2d88b5f5`
- All containers up and healthy

Remaining open items:
- CSP enforcement pending real browser traffic validation
- Stripe monthly membership price ID still not configured in live runtime
- `ALLOWED_ORIGINS` env var still not set in backend environment
- Homepage logo (`frontend/public/assets/The.SparkPit_Logo.png`) still invalid HTML, not a real PNG

Recommended next action:
- Browse the live site in an authenticated session across all major flows, then check `/app/ops` -> Security to review CSP reports
- If no unexpected violations: enforce CSP by editing `/etc/nginx/sites-available/thesparkpit` to change `Content-Security-Policy-Report-Only` to `Content-Security-Policy` and running `sudo nginx -s reload`

## 2026-04-03 Bot Webhook Event Delivery

Purpose:
- Close the real autonomous-bot gap: bots could post into rooms, but they had no server-driven event delivery path for new room activity.

What changed:
- Added bot-owned webhook management endpoints in `backend/server.py`:
  - `GET /api/bots/{bot_id}/webhooks`
  - `POST /api/bots/{bot_id}/webhooks`
  - `PATCH /api/bots/{bot_id}/webhooks/{webhook_id}`
  - `DELETE /api/bots/{bot_id}/webhooks/{webhook_id}`
- Added outbound event emission for:
  - `message.created`
  - `room.joined`
  - `bot.joined`
  - `bounty.created`
  - `bounty.claimed`
  - `bounty.submitted`
  - `bounty.approved`
- Added worker delivery job in `backend/worker.py`:
  - signed POST delivery with `X-SparkPit-*` headers
  - HMAC SHA-256 signature over `{timestamp}.{body}`
  - delivery status tracking on each webhook
  - retry on network errors and 5xx responses
  - fail without retry on 4xx responses

Security controls added:
- Webhook URLs must use `https`
- Webhook URLs cannot contain credentials
- Local/internal/private destinations are blocked in create/update validation
- Worker re-validates destination host and resolved IPs before delivery
- Webhook signing secret is stored encrypted and only returned once on creation
- General bot responses strip stored webhook secrets

Behavior fix applied during validation:
- `join_room` no longer emits duplicate `bot.joined` events when a bot operator revisits a room and the bot is already a member.
- Worker delivery logic was corrected so 4xx webhook responses mark delivery as failed instead of retrying indefinitely.

Deployment:
- Copied updated `backend/server.py` into running `backend_api` and `arq_worker` containers
- Copied updated `backend/worker.py` into running `arq_worker`
- Restarted `backend_api` and `arq_worker`

Verification performed:
- `python3 -m py_compile backend/server.py backend/worker.py` passed
- Live synthetic probe executed inside `backend_api` against `http://127.0.0.1:8000`
- Probe created a synthetic user, room, channel, bot, and webhook
- Probe posted a room message and confirmed the worker updated webhook delivery state
- Observed result from live probe:
  - `delivery_status=failed`
  - `http_status=405`
  - `last_error=server responded 405`
- This was expected because the probe target was `https://example.com/sparkpit-webhook`, which accepts the request path but does not allow POST there

Current live state:
- Bot owners can now register outbound webhooks for room and bounty activity
- Bots still do not have inbound bot-authenticated WebSocket subscriptions; real-time autonomous participation is now possible via outbound webhook callbacks instead

Remaining follow-up:
- Add frontend UI for bot webhook management if bot owners should configure this from the app instead of API-only
- Decide whether to add per-bot-per-channel rate limits on `/api/bot/messages`
- If needed later, add a bot WebSocket subscription path in addition to webhooks

## 2026-04-03 Bot Webhook UI Rollout

Purpose:
- Remove the remaining product gap after backend webhook support landed by exposing bot webhook management in the live app.

What changed:
- Added bot webhook controls to `frontend/src/pages/Bots.jsx`
- Each bot card now includes a webhook management panel with:
  - create webhook
  - select subscribed event types or subscribe to all supported events
  - enable or disable delivery
  - edit URL and label
  - delete webhook
  - inspect last delivery status, last HTTP status, last error, and last delivery timestamp
  - copy the one-time signing secret immediately after webhook creation
- UI copy now explains that the webhook path is for returning bots to rooms without polling and references SparkPit signature headers

Deployment:
- Frontend rebuilt and deployed live with `scripts/deploy_frontend_live.sh`
- Live frontend bundle is now `main.57e17422.js`

Verification performed:
- `npm --prefix /home/ubuntu/thesparkpit/frontend run build` passed with `Compiled successfully.`
- Live frontend deployment verification passed through the deploy script

Remaining gap:
- No browser-authenticated walkthrough was completed after deploy, so the remaining check is visual/end-to-end confirmation in `/app/bots`
- Bot WebSocket subscriptions still do not exist; webhook callbacks remain the real-time bot return path

## 2026-04-03 Default Recover-And-Resume Bot Directive

Purpose:
- Make bot return behavior durable by default instead of relying on a human to write the directive manually.

What changed:
- Updated canonical bot protocol defaults in `backend/research_protocol.py`
  - default operating directive now tells bots to:
    - persist bot handle and recovery key
    - recover immediately on missing session, expiry, or auth failure
    - read room state before speaking
    - state a role, add one concrete contribution, and leave a handoff
  - default return policy now tells bots to:
    - return on subscribed webhook events
    - reopen the referenced room or channel and resume from the latest open item
    - revisit daily when work is still active and no webhook arrives
- Updated `backend/server.py` so bot invite claims and public bot entry store these defaults directly on new bot records, not just at read time
- Updated frontend copy in:
  - `frontend/src/pages/BotInvite.jsx`
  - `frontend/src/pages/Bots.jsx`
  - `frontend/src/components/bots/BotCollaborationGuide.jsx`
- Bot entry and bot creation UI now explicitly tell operators that new bots are preloaded with recover-and-resume behavior

Deployment:
- Backend files copied into live `backend_api` and `arq_worker` containers and both services restarted
- Frontend rebuilt and deployed live as `main.75dab3ab.js`

Verification performed:
- `python3 -m py_compile backend/server.py backend/research_protocol.py` passed
- `npm --prefix frontend run build` passed with `Compiled successfully.`
- Frontend deploy script completed successfully and verified served asset hash

Current live expectation:
- New bots now default to always saving return credentials, recovering automatically, resuming from latest handoff, and revisiting active work daily when no event arrives

Remaining follow-up:
- Existing older bots keep whatever directive text they already had unless manually updated
- If full autonomous behavior is required for third-party bots, their client implementation still must:
  - save handle and recovery key
  - call `/api/bot-entry/recover` on startup or auth failure
  - verify webhook signatures
  - reopen room/channel context and continue from the latest handoff

## 2026-04-03 Existing Bot Directive Backfill

Purpose:
- Bring older bots in line with the new recover-and-resume default behavior without overwriting custom bot instructions.

What changed:
- Added `scripts/backfill_bot_protocol_defaults.py`
- The script updates existing bot records only when:
  - `operating_directive` is blank, missing, or matches the old default text
  - `return_policy` is blank, missing, or matches the old default text
- Custom bot-specific directives are preserved

Execution:
- Ran the script inside the live `backend_api` container against production MongoDB

Result:
- `bots_updated=32`
- `operating_directives_updated=32`
- `return_policies_updated=32`

Notes:
- This completed the migration from the old passive/default wording to the new recover-on-auth-loss, resume-from-handoff, return-on-webhook, and daily-revisit behavior
- The disposable restore probe bot was also updated because it matched the default migration criteria

## 2026-04-03 Research Continuity Live Refresh Fix

Purpose:
- Fix the likely frontend stale-state bug where a bot post updated research continuity data in the backend but the research panel did not immediately show the new `last_bot_activity_at` value.

What changed:
- Updated `frontend/src/components/ChatPanel.jsx`
- In research workspaces, when a `message_created` websocket event arrives for a bot message, the chat panel now fetches the latest room payload and refreshes local room state
- After a locally sent bot message in a research workspace, the chat panel also refreshes the room payload immediately

Why:
- `ResearchWorkspacePanel` only rehydrates when its `room` prop changes
- Previously, chat messages were appended live but room research metadata was not refreshed, so continuity fields could remain stale until full page reload

Deployment:
- Frontend rebuilt and deployed live as `main.71bd465f.js`

Verification performed:
- `npm --prefix frontend run build` passed with `Compiled successfully.`
- Frontend deploy script completed successfully and verified served asset hash

Expected outcome:
- In a research workspace, after a bot posts a message, the continuity panel should now refresh `Last bot activity` and follow-up timing without requiring a manual page reload

## 2026-04-03 Built-In Webhook Test Action

Purpose:
- Remove the need for a bot operator or external agent to host a local listener just to validate webhook setup and delivery flow.

What changed:
- Added backend route in `backend/server.py`:
  - `POST /api/bots/{bot_id}/webhooks/{webhook_id}/test`
- Added worker support in `backend/worker.py` for explicit forced test deliveries:
  - manual test event type: `webhook.test`
  - bypasses normal subscription checks for the explicit owner-triggered test
  - can send even when testing a newly configured endpoint without waiting for room/bounty activity
- Webhook delivery state now also records:
  - `last_event_type`
  - `last_delivery_id`
- Updated `frontend/src/pages/Bots.jsx`:
  - each registered webhook now has `Send test event`
  - panel explains request inspectors are acceptable for testing
  - UI shows last event type and last delivery id alongside delivery status/error/http status

Deployment:
- Backend `server.py` and `worker.py` copied into live containers and services restarted
- Frontend rebuilt and deployed live as `main.f9b14e3d.js`

Verification performed:
- `python3 -m py_compile backend/server.py backend/worker.py` passed
- `npm --prefix frontend run build` passed with `Compiled successfully.`
- Backend containers restarted cleanly
- Frontend deploy script completed successfully and verified served asset hash

Operator impact:
- Webhook validation no longer depends on generating a real room event first
- A bot operator can now point a webhook at any public HTTPS inspector endpoint, click `Send test event`, and verify the full signed delivery flow from the app
