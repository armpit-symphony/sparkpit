# The-Spark-Pit — Server Runbook (EC2)

Location: /home/ubuntu/thesparkpit
Branch: main (local may be ahead of origin)

## What we fixed today
- Disk was full (root 7.6G at 100%). Expanded EBS to 30G and resized:
  - nvme0n1 -> 30G
  - nvme0n1p1 -> ~29.9G
  - / now ~29G with ~23G free

## Frontend dependency fix
- React 19 peer-dep conflict with react-day-picker@8.10.1
- Bumped react-day-picker to ^9.0.0
- npm install + npm ci succeeded
- npm run build succeeded (ESLint warnings only)

## Git push note
- Outbound SSH(22) to GitHub appears blocked from this environment.
- If you ever push from this server, use HTTPS + PAT (over 443), or push from your local machine instead.

## How to run the site on this server
There are three possible run modes:
1) Docker Compose (preferred if available)
2) Systemd services (if unit files exist)
3) Manual (tmux/nohup) fallback

### Health checks
- See what’s running: ps aux | egrep -i "uvicorn|gunicorn|node|nginx|pm2|docker" | grep -v egrep
- Check open ports: sudo ss -lntp

## Nginx health endpoint
- Implemented `location = /health` on both HTTP (80) and HTTPS (443) server blocks in the thesparkpit vhost.
- HTTP /health returns 200 OK (exception to redirect).
- HTTPS /health returns 200 OK text/plain.
- Vhost file: /etc/nginx/sites-available/thesparkpit (or symlink target in /etc/nginx/sites-enabled)
- Reload command: `sudo nginx -t && sudo systemctl reload nginx`

## Deploy runbook (`./ops deploy`)
- `./ops deploy` includes API readiness loops (20 attempts, 2s interval) for:
  - direct backend: `http://127.0.0.1:8000/api/`
  - nginx path: `https://127.0.0.1/api/` with `Host: thesparkpit.com`
- If direct backend fails readiness, deploy prints `backend not ready`, tails `backend_api` logs, and exits non-zero.
- If direct backend is ready but nginx path fails readiness, deploy prints `nginx upstream not ready`, tails `backend_api` logs, and exits non-zero.

## Compose auto-start on reboot
- Systemd unit installed: `/etc/systemd/system/thesparkpit-compose.service`
- Enabled at boot: `sudo systemctl is-enabled thesparkpit-compose.service` -> `enabled`
- Service starts stack with: `docker compose up -d` in `/home/ubuntu/thesparkpit`
- Service management:
  - status: `sudo systemctl status thesparkpit-compose.service --no-pager`
  - restart: `sudo systemctl restart thesparkpit-compose.service`
  - disable: `sudo systemctl disable --now thesparkpit-compose.service`

## Deploy Frontend (safe/reversible)
Use this when nginx is serving stale UI from `/var/www/thesparkpit`.

Preferred path:

```bash
cd /home/ubuntu/thesparkpit || exit 1
bash scripts/deploy_frontend_live.sh
```

What it does:
- builds the frontend
- runs `scripts/verify_frontend_bundle.sh`
- backs up `/var/www/thesparkpit`
- syncs `frontend/build/` into `/var/www/thesparkpit`
- verifies deployed bundle hash matches built hash
- verifies nginx serves the same hash on `https://127.0.0.1/` with `Host: thesparkpit.com`

If you need to run the same flow manually, use the steps below.

```bash
cd /home/ubuntu/thesparkpit || exit 1

# 1) prove what nginx is serving right now
echo "SERVING:"
curl -k -sS https://127.0.0.1/ -H 'Host: thesparkpit.com' | rg -o 'static/js/main\.[a-f0-9]+\.js' -n

# 2) build frontend from repo
cd frontend && npm ci && npm run build && cd ..

# 2a) fail early if the built bundle contains broken /undefined/api references
bash scripts/verify_frontend_bundle.sh

# 3) backup deployed web root (timestamped)
sudo rsync -a --delete /var/www/thesparkpit/ /var/www/thesparkpit.bak.$(date +%Y%m%d-%H%M%S)/

# 4) sync the new build into nginx web root
sudo rsync -a --delete frontend/build/ /var/www/thesparkpit/

# 5) confirm nginx now references the new main bundle
echo "SERVING_AFTER:"
curl -k -sS https://127.0.0.1/ -H 'Host: thesparkpit.com' | rg -o 'static/js/main\.[a-f0-9]+\.js' -n
```

Pass condition:
- `SERVING_AFTER` shows the newly built hash.
- `scripts/verify_frontend_bundle.sh` passes before sync.
- Optional strong check:
  - `sha256sum frontend/build/static/js/main.*.js`
  - `sha256sum /var/www/thesparkpit/static/js/main.*.js`
  - Hashes should match exactly.

## Retry/Backoff Proof (ARQ)
Use this to prove retries happen with visible delay.

```bash
cd /home/ubuntu/thesparkpit || exit 1
PROBE_ID="retry-$(date +%s)"
START_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# enqueue probe: succeeds on 2nd attempt with 2s defer
PROBE_ID="$PROBE_ID" docker compose exec -T backend_api sh -lc "python - <<'PY'
import os, asyncio
from arq import create_pool
from arq.connections import RedisSettings
probe_id = os.environ['PROBE_ID']
async def main():
    pool = await create_pool(RedisSettings.from_dsn('redis://redis:6379/0'))
    job = await pool.enqueue_job('backend.worker.retry_probe', {'probe_id': probe_id, 'succeed_on': 2, 'defer_seconds': 2})
    print(job.job_id)
    await pool.aclose()
asyncio.run(main())
PY" | tee /tmp/retry_probe_job_id

# verify attempt counter reached 2 (failed once, retried, then succeeded)
docker compose exec -T redis redis-cli GET "tsp:retry_probe:${PROBE_ID}:attempts"

# inspect worker logs for retry timing around the probe window
docker compose logs --since 5m arq_worker | tail -n 200
```

Pass condition:
- Redis key `tsp:retry_probe:<PROBE_ID>:attempts` is `2` (or higher if repeated runs collide).
- Worker logs show first try and a later retry after ~2s defer.
