# The Spark Pit

This project was bootstrapped by [Emergent](https://emergent.sh).

## Ops / Local Dev (Stage 1.3)

### Required env vars (backend)
```
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
REDIS_URL=redis://redis:6379/0
```

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
