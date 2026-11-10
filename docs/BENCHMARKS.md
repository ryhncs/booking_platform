# Benchmarks

Everything here was measured, not estimated. The commands to reproduce each
number are next to it. Absolute timings depend on the machine; the ratios and
query counts don't.

**Machine:** Windows 11, Docker Desktop 29.0.1 (Linux VM with 8 CPUs, 7.6 GiB),
Python 3.13, PostgreSQL 16, Redis 7. Measured on 2026-11-08/10.

## 1. Availability endpoint: cold vs cached

`GET /api/availability/` on the demo data (`seed_demo`): Sara Ahmadi, Haircut
(45 min), the next working day, which has one confirmed booking and returns 25
free slots.

Requests go out in **pairs**. First the staff member's cache version is bumped,
which is the same invalidation a booking change triggers. Then one request runs
**cold**: it computes the slots from PostgreSQL and fills Redis. The same
request then runs again, **cached**. Pairing means slow drift on the machine
affects both sides equally. Each run is 50 warm-up pairs, then 1,000 measured
pairs. The server is one gunicorn sync worker with `DEBUG` off, reached over
loopback HTTP from the same container, with a real JWT on every request. The
timing covers the whole HTTP round trip.

### Default database settings (a new PostgreSQL connection per request)

| Run | cold p50 | cold p95 | cached p50 | cached p95 |
| --- | ---: | ---: | ---: | ---: |
| 1 | 31.5 ms | 39.2 ms | 20.7 ms | 25.9 ms |
| 2 | 32.0 ms | 40.2 ms | 20.8 ms | 26.2 ms |
| 3 | 32.6 ms | 48.9 ms | 21.3 ms | 30.2 ms |

### With persistent connections (`?conn_max_age=600` on `DATABASE_URL`)

| Run | cold p50 | cold p95 | cached p50 | cached p95 |
| --- | ---: | ---: | ---: | ---: |
| 1 | 10.8 ms | 15.0 ms | 7.0 ms | 9.8 ms |
| 2 | 11.4 ms | 18.1 ms | 7.3 ms | 11.4 ms |
| 3 | 11.1 ms | 15.2 ms | 7.1 ms | 10.3 ms |

### What this shows

* **The cache cuts latency by about a third** in both setups: about 11 ms at the
  median with default settings, about 4 ms with persistent connections. It saves
  3 of the endpoint's 7 SQL statements (shifts, bookings and time off for the
  day). The other 4 still run on a cache hit: the JWT user lookup, the staff
  member, the service, and the "does this person offer this service" check.
* **Opening a database connection costs more than the cache saves.** Django's
  default (`CONN_MAX_AGE = 0`) connects to PostgreSQL on every request, which
  accounts for about 20 ms here. Persistent connections take the cold path from
  about 32 ms to 11 ms. They aren't enabled in this repo because production
  settings were out of scope. They'd be the first change for a deployment.
* The demo day is small: one shift and one booking. The cold path always runs
  the same number of queries however busy the day is (see section 2). Only the
  Python slot loop grows with more shifts and bookings, so a fuller schedule
  makes caching relatively more valuable.

### Reproduce

```bash
docker compose up -d db redis
docker compose run --rm web python manage.py seed_demo

# Default settings
docker compose run --rm -e DJANGO_SETTINGS_MODULE=config.settings.base -e DEBUG=false web sh -c '
  gunicorn config.wsgi:application --bind 127.0.0.1:8001 --workers 1 --log-level warning &
  sleep 5; python manage.py benchmark_availability --url http://127.0.0.1:8001 --requests 1000'

# Persistent connections: same command with
#   -e "DATABASE_URL=postgres://booking:booking@db:5432/booking?conn_max_age=600"
```

The command is `backend/apps/bookings/management/commands/benchmark_availability.py`.
Before it starts measuring, it checks that the cold and cached responses are
identical, and that the server really filled the Redis cache it reads.

## 2. SQL statements per endpoint

Measured with a real JWT, so every count includes the one query that loads the
user. `SAVEPOINT`/`RELEASE` statements are excluded, because they exist only as
an artefact of the test transaction. These are **asserted exactly** in
`backend/tests/test_query_counts.py`. Each list endpoint is measured with a few
rows and again with many more, and the count must not change. An N+1 regression
therefore fails CI. Removing the services list's `prefetch_related` turned 4
statements into 19 and failed the test.

| Endpoint | Statements | Stays flat as rows grow |
| --- | ---: | --- |
| `GET /api/me/` | 1 | n/a |
| `GET /api/businesses/` | 3 | yes (1 → 16 businesses) |
| `GET /api/staff/?business=` | 3 | yes (1 → 16 staff) |
| `GET /api/services/?business=` | 4 | yes (1 → 16 services, 5 staff each) |
| `GET /api/working-hours/?staff=` | 3 | yes (1 → 19 shifts) |
| `GET /api/availability/` cold | 7 | yes (0 → 4 bookings that day) |
| `GET /api/availability/` cached | 4 | n/a |
| `GET /api/bookings/?scope=mine` | 3 | yes (1 → 13 bookings) |
| `POST /api/bookings/` | 7 | n/a |
| `POST /api/bookings/{id}/confirm/` | 8 | n/a |
| `POST /api/bookings/{id}/cancel/` | 8 | n/a |

A list is the user, a `COUNT(*)` for pagination, and one joined `SELECT`, plus
one prefetch for services' staff. A booking write is its rule checks, a
`SELECT ... FOR UPDATE` on the row, the `UPDATE`, and loading the relations for
the response.

```bash
docker compose run --rm web pytest tests/test_query_counts.py -v
```

## 3. Concurrency: the exclusion constraints

Each race releases 20 threads through a barrier. Each thread has its own
database connection, so the requests genuinely overlap inside PostgreSQL.

| Race | With the constraint | Constraint removed |
| --- | --- | --- |
| 20 customers book the same slot (`tests/test_concurrency.py`) | exactly 1 succeeds, in 20 of 20 runs | **20 of 20** succeed, in 5 of 5 runs |
| 20 overlapping shifts for one staff member, via the API (`tests/test_shift_concurrency.py`) | exactly 1 succeeds, in 20 of 20 runs | **4–11 of 20** succeed (9, 4, 11, 6, 7 over 5 runs) |
| 10 bulk plus 10 single overlapping shift requests | exactly 1 succeeds, in 20 of 20 runs | n/a |

Without the constraint, every booking gets through: `create_booking` has no
overlap check in Python at all, by design. Shifts do have a serializer
pre-check, which catches some of the losers but not all of them. That's exactly
why the database is the guarantee and the pre-check only provides friendlier
messages. With the constraints, every loser was rejected cleanly: `SlotUnavailable`
for bookings (which the API answers with 409), and a 400 for shifts, never a 500.

```bash
# With the constraints: repeat the races (the README's "20 of 20" numbers)
docker compose run --rm web sh -c 'for i in $(seq 1 20); do
  pytest tests/test_concurrency.py tests/test_shift_concurrency.py -q || echo FAILED; done'

# Constraints removed (skipped in CI): drops them in the test database, races, restores them
docker compose run --rm -e RUN_CONSTRAINT_MUTATION=1 web \
  pytest tests/test_constraint_mutation.py -q -s
```
