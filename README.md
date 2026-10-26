# Booking Platform

A multi-business appointment booking backend (think a small Calendly or salon-booking system) built with **Django, Django REST Framework and PostgreSQL**. Businesses define services, staff and weekly working hours; customers book open slots.

The focus of the project is **correctness under concurrency**: two customers clicking "Book" on the same slot at the same millisecond must never both succeed.

![CI](https://github.com/ryhncs/booking-platform/actions/workflows/ci.yml/badge.svg)

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

## Running locally

```bash
docker compose up --build
# API on http://localhost:8000, admin on /admin
docker compose exec web python manage.py createsuperuser
```

Run the tests (PostgreSQL is required; SQLite cannot express range exclusion constraints):

```bash
docker compose exec web pytest --cov=apps
```

## Tech stack

Django 5.2 · DRF · PostgreSQL 16 (`btree_gist`, range types) · Redis · Docker Compose · pytest · GitHub Actions · Ruff

## Roadmap

- [x] **Stage 1:** data model, overlap constraint, booking service, concurrency tests, Docker, CI
- [ ] **Stage 2:** REST API (JWT auth, role-based permissions, availability endpoint), OpenAPI docs via drf-spectacular
- [ ] **Stage 3:** Redis caching of available slots with invalidation; Celery for confirmation emails, reminders and releasing expired holds
- [ ] **Stage 4:** React + Redux Toolkit frontend
- [ ] **Stage 5:** deployment, architecture diagram, query-performance benchmarks
