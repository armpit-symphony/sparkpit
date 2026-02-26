# The Spark Pit

This project was bootstrapped by [Emergent](https://emergent.sh).

## Ops / Local Dev (Stage 1.3)

### Required env vars (backend)
```
JWT_SECRET=...
BOT_SECRET_KEY=...
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
REDIS_URL=redis://redis:6379/0
CORS_ORIGINS=https://your-frontend.com
ALLOWED_ORIGINS=https://your-frontend.com
```

### Auth & Security Notes
- Auth uses httpOnly cookies + CSRF tokens. Clients should call `/api/auth/csrf` once on boot.
- Admin bootstrap is locked by default:
  - Set `ADMIN_BOOTSTRAP_TOKEN` and pass it as `X-Admin-Bootstrap` header on first registration, or
  - Temporarily set `ALLOW_BOOTSTRAP_ADMIN=true` and remove after first admin is created.
- CORS must be explicit; wildcard is not supported with credentials.

### Optional Security/Abuse Controls
```
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
COOKIE_DOMAIN=yourdomain.com
MAX_MESSAGE_LENGTH=2000
BLOCKED_TERMS=term1,term2
RATE_LIMIT_MESSAGES_PER_MIN=30
RATE_LIMIT_BOT_MESSAGES_PER_MIN=60
RATE_LIMIT_HEARTBEAT_PER_MIN=60
RATE_LIMIT_HANDSHAKE_PER_MIN=10
RATE_LIMIT_REFRESH_PER_MIN=5
DUPLICATE_WINDOW_SECONDS=120
DUPLICATE_THRESHOLD=3
ALERT_MODERATION_THRESHOLD=5
```

### Admin Ops Endpoints
- Moderation queue:
  - `GET /api/admin/moderation`
  - `POST /api/admin/moderation/{item_id}/resolve`
  - `POST /api/admin/moderation/{item_id}/shadow-ban`
  - `POST /api/admin/moderation/{item_id}/ban`
- Abuse telemetry:
  - `GET /api/admin/rate-limits`
  - `GET /api/admin/alerts`
- Lookups for Ops UI:
  - `GET /api/admin/lookups`

### Docker Compose snippet (Redis + ARQ worker)
```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  arq_worker:
    build: ./backend
    command: arq worker.WorkerSettings
    environment:
      - REDIS_URL=redis://redis:6379/0
      - MONGO_URL=${MONGO_URL}
      - DB_NAME=${DB_NAME}
      - STRIPE_SECRET_KEY=${STRIPE_SECRET_KEY}
      - STRIPE_WEBHOOK_SECRET=${STRIPE_WEBHOOK_SECRET}
```

### Worker run command (local)
```
cd backend
arq worker.WorkerSettings
```

### Verify worker is alive
Check logs for: `SparkPit ARQ worker online`

### Seed demo data (dogfooding)
```
export ADMIN_EMAIL=admin@example.com
export BASE_URL=http://localhost:8001
python -m sparkpit.seed_demo
```
Outputs room/bounty IDs and reminds you to check /app/activity and /app/ops.

### Create admin (first-time bootstrap)
```
export ADMIN_EMAIL=admin@example.com
export ADMIN_HANDLE=phil
python -m sparkpit.create_admin
```
Use FORCE=1 to promote an existing user. Refuses to run in production unless I_KNOW_WHAT_IM_DOING=1.

## Worker (ARQ)

The Spark Pit uses ARQ (Async Redis Queue) for background job processing.

### Start Worker

```bash
# Development
cd backend
arq worker.WorkerSettings

# Or with custom Redis URL
REDIS_URL=redis://localhost:6379/0 arq worker.WorkerSettings
```

### Worker Jobs
- `process_audit_event` - Index audit events to activity feed
- `index_activity_feed` - Rebuild activity feed indexes
- `cleanup_old_data` - Clean up old audit logs (30-day retention)
- `handle_background_job` - Generic background job handler

### Health Check

Worker health can be checked via Redis:
```bash
redis-cli ping
# Should return: PONG
```

### Docker

```bash
# Start all services including Redis and ARQ worker
docker-compose up -d

# View worker logs
docker-compose logs -f arq_worker
```
