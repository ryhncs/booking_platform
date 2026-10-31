# Booking Platform — notes for Claude Code

Portfolio project: multi-business appointment booking backend (Django 5.2, DRF, PostgreSQL 16, Redis, Celery; React + Redux Toolkit frontend later). The selling point is correctness under concurrency. Keep code production-quality: it is read by recruiters.

## Layout
- `backend/config/settings/{base,dev}.py` — settings via django-environ (`DATABASE_URL`, `SECRET_KEY`, `DEBUG`)
- `backend/apps/core` — `TsTzRange` helper + `btree_gist` extension migration (other apps' first migrations depend on it)
- `backend/apps/accounts` — custom `User` with `role` (customer / staff / owner)
- `backend/apps/businesses` — Business (IANA timezone), Staff, Service, WorkingHours, TimeOff
- `backend/apps/bookings` — Booking model + `services.py` (all booking writes go through it)
- `backend/apps/bookings/{availability,signals}.py` — Redis-cached free slots + invalidation; `tasks.py`/`emails.py` — Celery tasks (worker/beat services in compose)
- `backend/tests` — pytest (needs Postgres **and Redis**; cache/notification tests use real commits, `transaction=True`); `test_concurrency.py` races 20 threads for one slot

## Invariants — do not break
- No double booking is enforced by the `booking_no_overlap_per_staff` exclusion constraint (tstzrange, half-open `[start, end)`, cancelled excluded). Never replace it with a check-then-insert in Python.
- All Booking writes go through `apps/bookings/services.py`; views/serializers call it and map `BookingError` subclasses to HTTP errors (`SlotUnavailable` → 409).
- Timestamps stored in UTC; working hours are local to `Business.timezone`.
- PostgreSQL only (SQLite can't express the constraint).
- Cached availability is invalidated by model signals via `transaction.on_commit` (never before commit). `QuerySet.update()`/`bulk_create()` skip signals: call `availability.invalidate_staff` yourself if you use them on Booking/WorkingHours/TimeOff/Service.
- Notification tasks are enqueued with `on_commit` and must stay idempotent (claim via the `*_sent_at` fields). Hold expiry goes through `services.expire_booking`, never a raw status update.

## Running things — always inside Docker
The dev machine is Windows with no local Python deps. The stack runs via `docker compose up` from the repo root, and every Python command goes through the `web` container (it mounts `./backend` at `/app`, so edits are picked up live):
- `docker compose exec web pytest`
- `docker compose exec web ruff check . --fix` then `docker compose exec web ruff format .`
- `docker compose exec web python manage.py makemigrations` (never hand-write migrations; generate them, then run `makemigrations --check --dry-run`)

Before saying a change is done, run all of the above and make sure they pass. Never report a change as tested if only a syntax check ran.

PyPI is unreachable from the dev network; the repo-root `.env` sets `PIP_INDEX_URL` to a mirror. After changing requirements, rebuild with `docker compose up --build`.

## Commands (from `backend/`, inside the container)
- `./check.sh` (from repo root) — all CI checks in Docker, incl. `spectacular --validate --fail-on-warn`
- `docker compose up --build` (from repo root) — db, redis, web on :8000
- `pytest --cov=apps` — needs Postgres reachable via `DATABASE_URL`
- `ruff check . && ruff format --check .` — CI runs both plus `makemigrations --check`

## Roadmap
- [x] Stage 1: models, constraint, service layer, tests, Docker, CI
- [x] Stage 2: REST API — JWT (simplejwt), role-based permissions, business/staff/service CRUD for owners, availability endpoint (free slots for a staff+service+date), booking create/confirm/cancel, drf-spectacular Swagger at /api/docs/, API tests
- [x] Stage 3: Redis cache for availability with invalidation on booking change; Celery + Beat: confirmation email, 24h reminder, release expired pending holds
- [ ] Stage 4: `frontend/` React + Redux Toolkit (RTK Query)
- [ ] Stage 5: deploy, architecture diagram, query benchmarks in README

Update the roadmap checkboxes and README when a stage is done.
