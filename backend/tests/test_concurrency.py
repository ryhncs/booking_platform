"""Many clients race for the same slot at the same instant.

Each thread opens its own database connection and all of them are released
together by a barrier, so the inserts genuinely overlap inside PostgreSQL.
A check-then-insert implementation would let several through; the exclusion
constraint must let exactly one win.
"""

import threading

import pytest
from django.db import connection

from apps.bookings.models import Booking
from apps.bookings.services import SlotUnavailable, create_booking

from .conftest import next_monday_at

N_CLIENTS = 20


@pytest.mark.django_db(transaction=True)
def test_only_one_of_many_concurrent_requests_wins(make_customer, staff, service):
    customers = [make_customer() for _ in range(N_CLIENTS)]
    start = next_monday_at(10)
    barrier = threading.Barrier(N_CLIENTS)
    results: list[str] = []
    lock = threading.Lock()

    def attempt(customer):
        try:
            barrier.wait()
            create_booking(customer=customer, staff=staff, service=service, start=start)
            outcome = "won"
        except SlotUnavailable:
            outcome = "rejected"
        except Exception as exc:  # surface anything unexpected in the assertion
            outcome = f"error: {exc!r}"
        finally:
            connection.close()
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=attempt, args=(c,)) for c in customers]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count("won") == 1, results
    assert results.count("rejected") == N_CLIENTS - 1, results
    assert Booking.objects.filter(staff=staff).count() == 1
