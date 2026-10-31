# Booking Platform

A multi-business appointment booking backend (think a small Calendly or salon-booking system) built with **Django, Django REST Framework and PostgreSQL**. Businesses define services, staff and weekly working hours; customers book open slots.

The focus of the project is **correctness under concurrency**: two customers clicking "Book" on the same slot at the same millisecond must never both succeed.

![CI](https://github.com/ryhncs/booking_platform/actions/workflows/ci.yml/badge.svg)

## Highlights

**Double-booking is impossible at the database level.** Each booking's time is modelled as a half-open PostgreSQL range `tstzrange(start, end)`, and an exclusion constraint backed by a GiST index forbids two active bookings for the same staff member whose ranges overlap:

```python
ExclusionConstraint(
    name="booking_no_overlap_per_staff",
    expressions=[
        (TsTzRange("start", "end"), RangeOperators.OVERLAPS),
        ("staff", RangeOperators.EQUAL),
    ],
    condition=~Q(status="cancelled"),
)
```

This is stronger than the usual "check if the slot is free, then insert" approach, which has a race window between the check and the insert. Here PostgreSQL itself serialises conflicting inserts, so the rule holds no matter how many app servers or workers are running, and even for code that bypasses the service layer.

**Measured, not assumed.** `tests/test_concurrency.py` releases 20 threads (each with its own DB connection) through a barrier so they all try to book the same slot simultaneously:

| Implementation | Requests that succeeded |
|---|---|
| With the exclusion constraint | **1 of 20** (stable across repeated runs) |
| Constraint removed (mutation check) | 20 of 20 |

**Half-open ranges make back-to-back slots work naturally:** a 10:00–11:00 booking does not conflict with 11:00–12:00.

**Timezone-correct.** All timestamps are stored in UTC; working hours are interpreted in each business's own IANA timezone.

**Rules live in one place.** All booking writes go through `apps/bookings/services.py`, which raises typed, client-actionable errors (`SlotUnavailable`, `OutsideWorkingHours`, `InvalidBookingRequest`) instead of leaking database errors.

## Data model

```
User (role: customer | staff | owner)
 └── Business (timezone)
      ├── Staff ── WorkingHours (weekly shifts)
      │         └── TimeOff     (no-overlap constraint)
      └── Service (duration, price) ←→ Staff  (who offers what)

Booking: customer, staff, service, [start, end), status, expires_at
         status: pending → confirmed → completed, or → cancelled
```

Unconfirmed bookings carry an `expires_at` hold (10 minutes) so abandoned checkouts do not block a slot forever; a partial index on pending bookings keeps the expiry sweep cheap.

## API

Interactive docs (Swagger UI) at `/api/docs/`, OpenAPI schema at `/api/schema/`. Auth is JWT: `POST /api/auth/login/` with `{email, password}`, then send `Authorization: Bearer <access>`.

| Endpoint | Who | Notes |
| --- | --- | --- |
| `POST /api/auth/register/`, `/login/`, `/refresh/`; `GET/PATCH /api/me/` | anyone / signed-in | self-registration as `customer` or `owner` only |
| `/api/businesses/`, `/staff/`, `/services/`, `/working-hours/` | read: any signed-in user; write: owners | writes are scoped to the owner's own data (others' objects 404) |
| `GET /api/availability/?staff=&service=&date=` | signed-in | free slots in 15-minute steps, in the business's local time |
| `POST /api/bookings/`, `GET /api/bookings/`, `POST /api/bookings/{id}/confirm/` and `/cancel/` | customer, or owner of the business | all writes go through `services.py` |

Booking errors are mapped in one place: a lost race for a slot is **409** (`slot_unavailable`); other rule violations (outside working hours, past start, expired hold) are **400** with a machine-readable `code`.

## Caching and background work

**Availability cache (Redis).** Free slots are cached per staff + service + date. Every key embeds a per-staff *version token*, so invalidating a staff member is a single write that orphans all their keys (any service, any date) without scanning. Model signals on bookings, shifts, time off, services (including who offers them), staff and the business timezone bump the token **on commit**: never before (a concurrent reader could re-cache old rows under the new version) and never on rollback. A 5-minute TTL bounds staleness if an invalidation is ever missed, and a Redis outage degrades to computing slots from PostgreSQL. The "not in the past" filter is applied on every read, so time passing can't make an entry stale. The tests fail if invalidation is disabled.

**Celery + Beat.**

| Task | Trigger | Notes |
| --- | --- | --- |
| `send_confirmation_email` | booking confirmed | queued with `transaction.on_commit` |
| `send_cancellation_email` | booking cancelled | says who cancelled and why; goes to the party who did *not* cancel |
| `send_due_reminders` → `send_reminder_email` | every 15 min | confirmed bookings starting within 24h |
| `release_expired_holds` | every minute | cancels lapsed pending holds via `services.expire_booking`, which re-checks under a row lock so it can't cancel a booking confirmed meanwhile |
| `resend_unsent_emails` | every 5 min | safety net: re-queues confirmation/cancellation emails still unsent 2+ min after the status change (e.g. broker was down at commit); skips past bookings and gives up after 24h |

Email tasks are idempotent: each *claims* its send with an atomic `UPDATE … WHERE <sent_at> IS NULL` (`confirmation_email_sent_at`, `cancellation_email_sent_at`, `reminder_sent_at`), so duplicate deliveries and concurrent workers send once; a failed send releases the claim and is retried with backoff. That same claim is what makes the sweep safe: re-queuing can never double-send.

## Running locally

```bash
docker compose up --build
# API on http://localhost:8000, Swagger on /api/docs/, admin on /admin
# `worker` and `beat` run the Celery tasks; dev emails print in their log:
#   docker compose logs -f worker
docker compose exec web python manage.py createsuperuser
```

Run the tests (PostgreSQL is required; SQLite cannot express range exclusion constraints):

```bash
docker compose exec web pytest --cov=apps
```

Or run everything CI runs (lint, format, migrations check, OpenAPI validation, tests) in a throwaway container with `./check.sh`.

## Tech stack

Django 5.2 · DRF · simplejwt · drf-spectacular · PostgreSQL 16 (`btree_gist`, range types) · Redis · Docker Compose · pytest · GitHub Actions · Ruff

## Roadmap

- [x] **Stage 1:** data model, overlap constraint, booking service, concurrency tests, Docker, CI
- [x] **Stage 2:** REST API (JWT auth, role-based permissions, availability endpoint), OpenAPI docs via drf-spectacular
- [x] **Stage 3:** Redis caching of available slots with invalidation; Celery for confirmation emails, reminders and releasing expired holds
- [ ] **Stage 4:** React + Redux Toolkit frontend
- [ ] **Stage 5:** deployment, architecture diagram, query-performance benchmarks
