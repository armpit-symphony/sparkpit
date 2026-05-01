# Work Orders Logbook

## 2026-03-04T02:27:00Z - WO 03022026-01
- Rotated admin password for `phil@thesparkpit.com` in Mongo using backend bcrypt hash function.
- Verified auth path over nginx HTTPS:
  - `POST /api/auth/login` returned `200 OK`.
  - `GET /api/me` returned admin user with `is_admin=true`, `role=admin`, `membership_status=active`.
- Captured backend warning and versions:
  - Warning: `passlib.handlers.bcrypt` trapped bcrypt version-read error.
  - Container versions: `bcrypt 4.1.3`, `passlib 1.7.4`.
  - Classified as non-blocking because hashing and login verification succeeded.
- Appended Mode A completion proof to `ops/work_orders/03022026-01.log.md` (no secrets).
- Committed WO log update:
  - Commit: `0cc9171`
  - Message: `docs(wo): record completed Mode A live proof and admin password rotation`

## 2026-03-06T23:32:00Z - Auth/Mongo Volume Incident
- Incident date: 2026-03-06
- Symptom: official admin login stopped working; active DB appeared empty/fresh
- Root cause: Mongo container recreated onto a fresh anonymous `/data/db` volume due to incorrect compose mount pattern (`/data` parent mount)
- Recovery: identified correct historical Mongo volume (`670bc0b1ca1e...`), restored live DB, then migrated current live state into stable named volumes
- Permanent fix: Mongo now mounts named volumes directly to `/data/db` and `/data/configdb`
- Verification: Phil successfully logged back into TheSparkPit; collection counts preserved
- Missing operational detail captured:
  - Confirmed running backend target remained `MONGO_URL=mongodb://mongodb:27017` and `DB_NAME=thesparkpit`; this was not a wrong-DB-name issue.
  - Proved the live Mongo container had anonymous child mounts at `/data/db` and `/data/configdb` via `docker inspect`.
  - Inspected historical anonymous Mongo volumes read-only and identified `670bc0b1ca1e...` as the pre-March-6 live dataset (`users=5`, `audit_events=29`, `invite_codes=3`, `phil@thesparkpit.com` present as `admin` / `active`).
  - Took pre-restore backup: `/home/ubuntu/thesparkpit/artifacts/thesparkpit-pre-restore-20260306T231117Z.archive.gz`
  - Created isolated source dump from the historical volume: `/home/ubuntu/thesparkpit/artifacts/thesparkpit-source-670bc-20260306T231117Z.archive.gz`
  - Restored only `thesparkpit.*` into current live Mongo with `mongorestore --archive --nsInclude='thesparkpit.*' --drop`
  - Took pre-change backup before permanent volume fix: `/home/ubuntu/thesparkpit/artifacts/thesparkpit-volume-fix-prechange-20260306T233015Z.archive.gz`
  - Migrated current live data from anonymous volumes into stable named volumes:
    - `thesparkpit_mongo_db_data` -> `/data/db`
    - `thesparkpit_mongo_configdb_data` -> `/data/configdb`
  - Recreated only `mongodb`, `backend_api`, and `arq_worker`; preserved restored state after switch.
  - Post-fix verification:
    - Mongo mounts are now stable named volumes only.
    - `thesparkpit` counts after cutover: `users=5`, `audit_events=30`, `invite_codes=3`, `tasks=2`.
    - `GET http://127.0.0.1:8000/api/` returned API online and CSRF route returned `200`.
