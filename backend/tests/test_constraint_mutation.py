"""What happens under the same races when the exclusion constraints are removed.

Skipped by default: it measures a deliberately broken database, and how many
requests slip through varies between runs, so it can't be a pass/fail CI check.
To reproduce the numbers in docs/BENCHMARKS.md:

    docker compose run --rm -e RUN_CONSTRAINT_MUTATION=1 web \
        pytest tests/test_constraint_mutation.py -q -s
"""

import os
import threading
from datetime import time

import pytest
from django.db import connection
from django.urls import reverse

from apps.bookings.models import Booking
from apps.bookings.services import SlotUnavailable, create_booking
from apps.businesses.models import WorkingHours

from .conftest import next_monday_at
from .test_shift_concurrency import N_CLIENTS, TUE, race

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_CONSTRAINT_MUTATION"),
    reason="set RUN_CONSTRAINT_MUTATION=1 to measure with the constraints removed",
)


@pytest.fixture
def without_constraint(transactional_db):
    """Run a test with one named constraint removed, then put it back."""
    removed = []

    def remove(model, name):
        constraint = next(c for c in model._meta.constraints if c.name == name)
        with connection.schema_editor() as editor:
            editor.remove_constraint(model, constraint)
        removed.append((model, constraint))

    yield remove

    for model, constraint in removed:
        model.objects.all().delete()  # the broken run left overlapping rows
        with connection.schema_editor() as editor:
            editor.add_constraint(model, constraint)


def test_bookings_without_the_constraint(without_constraint, make_customer, staff, service):
    without_constraint(Booking, "booking_no_overlap_per_staff")
    customers = [make_customer() for _ in range(N_CLIENTS)]
    start = next_monday_at(10)
    barrier = threading.Barrier(N_CLIENTS)
    outcomes: list[str] = []
    lock = threading.Lock()

    def attempt(customer):
        try:
            barrier.wait()
            create_booking(customer=customer, staff=staff, service=service, start=start)
            outcome = "won"
        except SlotUnavailable:
            outcome = "rejected"
        finally:
            connection.close()
        with lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=attempt, args=(c,)) for c in customers]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    won = outcomes.count("won")
    print(f"\nbookings without constraint: {won} of {N_CLIENTS} succeeded")
    assert won > 1


def test_shifts_without_the_constraint(without_constraint, owner, staff):
    without_constraint(WorkingHours, "working_hours_no_overlap")
    url = reverse("working-hours-list")
    requests = [
        (
            url,
            {
                "staff": staff.pk,
                "weekday": TUE,
                "start_time": time(9, i).strftime("%H:%M"),
                "end_time": time(12, i).strftime("%H:%M"),
            },
        )
        for i in range(N_CLIENTS)
    ]

    won = race(owner, requests).count(201)
    print(f"\nshifts without constraint: {won} of {N_CLIENTS} succeeded")
    assert won > 1
