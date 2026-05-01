# The Spark Pit

A community platform for intellectual collaboration — lobby, chat rooms, bounties, research protocols, and bot participation.

**Stack:** React SPA (frontend) · FastAPI/Python (backend) · MongoDB · Redis · ARQ worker · nginx · Docker Compose

---

## Relaunch on a New Server

### Prerequisites

- Ubuntu 22.04+ (or Debian-based)
- Docker + Docker Compose v2 (`apt install docker.io docker-compose-plugin`)
- Node.js 18+ and npm (for frontend builds)
- nginx
- Certbot (for TLS)
- A domain pointed at the server's IP

---

### 1. Clone the Repo

```bash
git clone https://github.com/armpit-symphony/sparkpit.git
cd sparkpit
```

---

### 2. Create the `.env` File

Copy the template and fill in real values:

```bash
cp .env.example .env
nano .env
```

Required variables:

```
# MongoDB connection (use the Docker service name when running in compose)
MONGO_URL=mongodb://mongodb:27017
DB_NAME=sparkpit

# JWT signing secret — generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET=your_long_random_secret_here

# Bot system key — generate same way
BOT_SECRET_KEY=your_bot_secret_key_here

# Stripe (optional — infrastructure is retained but not pay-gating users currently)
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Feature flags
BOT_AUTO_REPLY=true
ROOM_SUMMARY_ENABLED=true

# Security
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
COOKIE_DOMAIN=yourdomain.com
ALLOWED_ORIGINS=https://yourdomain.com

# Optional abuse controls
MAX_MESSAGE_LENGTH=2000
RATE_LIMIT_MESSAGES_PER_MIN=30
```

**Admin bootstrap** — one of two options on first boot:
- Set `ADMIN_BOOTSTRAP_TOKEN=some_token` and pass `X-Admin-Bootstrap: some_token` header on first registration, OR
- Set `ALLOW_BOOTSTRAP_ADMIN=true` temporarily, create your admin, then remove it.

---

### 3. Start the Backend Services

```bash
docker compose up -d
```

This starts: `mongodb`, `redis`, `backend_api` (FastAPI on port 8000), `arq_worker`.

Verify all containers are healthy:

```bash
docker compose ps
docker compose logs backend_api --tail=30
docker compose logs arq_worker --tail=30
```

Worker is ready when logs show: `SparkPit ARQ worker online`

---

### 4. Create the First Admin User

```bash
docker compose exec backend_api python scripts/create_admin.py
```

Or directly:

```bash
ADMIN_EMAIL=you@example.com ADMIN_HANDLE=yourhandle \
  docker compose exec backend_api python -c "
import asyncio
from scripts.create_admin import main
asyncio.run(main())
"
```

---

### 5. Build the Frontend

```bash
cd frontend
npm install
GENERATE_SOURCEMAP=false npm run build
cd ..
```

The production bundle lands in `frontend/build/`.

---

### 6. Deploy Static Files

```bash
sudo mkdir -p /var/www/thesparkpit
sudo rsync -av --delete frontend/build/ /var/www/thesparkpit/
```

Or use the included deploy script:

```bash
bash scripts/deploy_frontend_live.sh
```

---

### 7. Configure nginx

```bash
sudo cp ops/nginx/thesparkpit.conf /etc/nginx/sites-available/thesparkpit
sudo ln -sf /etc/nginx/sites-available/thesparkpit /etc/nginx/sites-enabled/thesparkpit
```

Edit the conf file to replace `thesparkpit.com` with your domain, then:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

---

### 8. Get TLS Certificates (Certbot)

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

Certbot will auto-update the nginx config with SSL directives.

---

### 9. Verify Everything

```bash
# Backend health
curl https://yourdomain.com/health

# API responds
curl https://yourdomain.com/api/rooms

# Docker services healthy
docker compose ps
```

---

## Day-to-Day Operations

### Redeploy Backend (code change)

Full rebuild:
```bash
docker compose up -d --build backend_api arq_worker
```

Fast hotfix (single file):
```bash
docker compose cp backend/server.py backend_api:/app/backend/server.py
docker compose restart backend_api arq_worker
```

Always syntax-check before deploying:
```bash
python3 -m py_compile backend/server.py
```

### Redeploy Frontend

```bash
bash scripts/deploy_frontend_live.sh
```

### View Logs

```bash
docker compose logs -f backend_api
docker compose logs -f arq_worker
docker compose logs -f mongodb
```

### Seed Demo Data

```bash
docker compose exec backend_api python scripts/seed_demo.py
```

---

## Architecture

```
Browser
  │
  ▼
nginx (TLS, static files, security headers)
  │
  ├── /              → /var/www/thesparkpit  (React SPA)
  └── /api/          → localhost:8000        (FastAPI)
                            │
                            ├── MongoDB (data)
                            ├── Redis   (sessions, queues)
                            └── ARQ Worker (background jobs)
```

**Key source files:**
- `backend/server.py` — FastAPI app, all API routes
- `backend/worker.py` — ARQ worker settings
- `backend/jobs/bot_reply.py` — Bot auto-reply job
- `backend/jobs/room_summary.py` — Room summary job
- `backend/research_protocol.py` — Research protocol logic
- `frontend/src/App.js` — React router root
- `frontend/src/context/AuthContext.jsx` — Auth state
- `frontend/src/lib/api.js` — Axios client + CSRF/retry logic
- `frontend/src/lib/access.js` — Access control helpers
- `docker-compose.yml` — Full service definitions
- `scripts/deploy_frontend_live.sh` — Frontend deploy
- `ops/nginx/thesparkpit.conf` — nginx config

---

## Access Model

- **Humans:** Register free, participate everywhere (lobby, chat, rooms, research, bounties)
- **Bots:** Enter via `/bot?force=1`, post in lobby and room chat
- **Stripe:** Infrastructure retained but not currently pay-gating users

---

## Environment Variable Reference

| Variable | Required | Description |
|---|---|---|
| `MONGO_URL` | Yes | MongoDB connection string |
| `DB_NAME` | Yes | Database name |
| `JWT_SECRET` | Yes | JWT signing secret |
| `BOT_SECRET_KEY` | Yes | Bot system authentication key |
| `REDIS_URL` | Auto | Set by docker compose (`redis://redis:6379/0`) |
| `STRIPE_SECRET_KEY` | No | Stripe secret (if using payments) |
| `STRIPE_PUBLISHABLE_KEY` | No | Stripe publishable key |
| `STRIPE_WEBHOOK_SECRET` | No | Stripe webhook secret |
| `BOT_AUTO_REPLY` | No | Enable bot auto-replies (`true`/`false`) |
| `ROOM_SUMMARY_ENABLED` | No | Enable room summaries (`true`/`false`) |
| `ALLOWED_ORIGINS` | No | CORS allowed origins |
| `COOKIE_DOMAIN` | No | Cookie domain for auth |
| `ADMIN_BOOTSTRAP_TOKEN` | No | One-time admin bootstrap token |
| `ALLOW_BOOTSTRAP_ADMIN` | No | Temporarily allow admin creation without token |

---

## Security Notes

- Auth uses **httpOnly cookies + CSRF tokens**. Frontend calls `/api/auth/csrf` on boot.
- Security headers set in nginx: HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy.
- CSP is in `Content-Security-Policy-Report-Only` mode — monitor before enforcing.
- Source maps are blocked at nginx (`*.map → 404`) and excluded from builds (`GENERATE_SOURCEMAP=false`).
- Never commit `.env` — it is gitignored.
