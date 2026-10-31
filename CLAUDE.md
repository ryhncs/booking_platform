# Booking Platform — notes for Claude Code

Portfolio project: multi-business appointment booking backend (Django 5.2, DRF, PostgreSQL 16, Redis, Celery; React + Redux Toolkit frontend later). The selling point is correctness under concurrency. Keep code production-quality: it is read by recruiters.

## Layout
- `backend/config/settings/{base,dev}.py` — settings via django-environ (`DATABASE_URL`, `SECRET_KEY`, `DEBUG`)
- `backend/apps/core` — `TsTzRange` helper + `btree_gist` extension migration (other apps' first migrations depend on it)
- `backend/apps/accounts` — custom `User` with `role` (customer / staff / owner)
- `backend/apps/businesses` — Business (IANA timezone), Staff, Service, WorkingHours, TimeOff
- `backend/apps/bookings` — Booking model + `services.py` (all booking writes go through it)
- `backend/tests` — pytest; `test_concurrency.py` races 20 threads for one slot

## Invariants — do not break
- No double booking is enforced by the `booking_no_overlap_per_staff` exclusion constraint (tstzrange, half-open `[start, end)`, cancelled excluded). Never replace it with a check-then-insert in Python.
- All Booking writes go through `apps/bookings/services.py`; views/serializers call it and map `BookingError` subclasses to HTTP errors (`SlotUnavailable` → 409).
- Timestamps stored in UTC; working hours are local to `Business.timezone`.
- PostgreSQL only (SQLite can't express the constraint).

## Commands (from `backend/`)
- `docker compose up --build` (from repo root) — db, redis, web on :8000
- `pytest --cov=apps` — needs Postgres reachable via `DATABASE_URL`
- `ruff check . && ruff format --check .` — CI runs both plus `makemigrations --check`

## Roadmap
- [x] Stage 1: models, constraint, service layer, tests, Docker, CI
- [ ] Stage 2: REST API — JWT (simplejwt), role-based permissions, business/staff/service CRUD for owners, availability endpoint (free slots for a staff+service+date), booking create/confirm/cancel, drf-spectacular Swagger at /api/docs/, API tests
- [ ] Stage 3: Redis cache for availability with invalidation on booking change; Celery + Beat: confirmation email, 24h reminder, release expired pending holds
- [ ] Stage 4: `frontend/` React + Redux Toolkit (RTK Query)
- [ ] Stage 5: deploy, architecture diagram, query benchmarks in README

Update the roadmap checkboxes and README when a stage is done.
