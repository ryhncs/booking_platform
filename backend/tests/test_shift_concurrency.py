"""Many owners' requests race to add overlapping hours for one staff member.

Like test_concurrency.py: each thread has its own database connection and a
barrier releases them together, so the inserts genuinely overlap inside
PostgreSQL. The serializer's overlap check runs before the insert, so under a
race several requests pass it at once; only the working_hours_no_overlap
exclusion constraint can make sure exactly one wins, and the API must answer
the losers with a 400, never a 500.
"""

import threading
from datetime import time

import pytest
from django.db import connection
from django.db.models import Exists, OuterRef
from django.urls import reverse
from rest_framework.test import APIClient

from apps.businesses.models import WorkingHours

N_CLIENTS = 20
TUE, WED = 1, 2


def race(owner, requests):
    """POST every (url, body) at the same instant; return the status codes."""
    barrier = threading.Barrier(len(requests))
    statuses: list[int] = []
    lock = threading.Lock()

    def attempt(url, body):
        client = APIClient()
        client.force_authenticate(owner)
        try:
            barrier.wait()
            status = client.post(url, body, format="json").status_code
        except Exception as exc:  # surface anything unexpected in the assertion
            status = f"error: {exc!r}"
        finally:
            connection.close()
        with lock:
            statuses.append(status)

    threads = [threading.Thread(target=attempt, args=r) for r in requests]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return statuses


def overlapping_pairs(staff):
    other = WorkingHours.objects.filter(
        staff=OuterRef("staff"),
        weekday=OuterRef("weekday"),
        start_time__lt=OuterRef("end_time"),
        end_time__gt=OuterRef("start_time"),
    ).exclude(pk=OuterRef("pk"))
    return WorkingHours.objects.filter(staff=staff).filter(Exists(other)).count()


@pytest.mark.django_db(transaction=True)
def test_only_one_of_many_concurrent_shifts_wins(owner, staff):
    # 20 mutually overlapping Tuesday shifts: 09:00-12:00, 09:01-12:01, ...
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

    statuses = race(owner, requests)

    assert statuses.count(201) == 1, statuses
    assert statuses.count(400) == N_CLIENTS - 1, statuses
    assert staff.working_hours.filter(weekday=TUE).count() == 1
    assert overlapping_pairs(staff) == 0


@pytest.mark.django_db(transaction=True)
def test_bulk_and_single_requests_racing_never_overlap(owner, staff):
    # Half bulk (Tue+Wed), half single (Tue): any one success excludes all others.
    single = (
        reverse("working-hours-list"),
        {"staff": staff.pk, "weekday": TUE, "start_time": "10:00", "end_time": "14:00"},
    )
    bulk = (
        reverse("working-hours-bulk"),
        {"staff": staff.pk, "weekdays": [TUE, WED], "start_time": "09:00", "end_time": "13:00"},
    )
    requests = [single, bulk] * (N_CLIENTS // 2)

    statuses = race(owner, requests)

    assert statuses.count(201) == 1, statuses
    assert statuses.count(400) == N_CLIENTS - 1, statuses
    assert overlapping_pairs(staff) == 0
    # Whoever won, it was all-or-nothing: a bulk winner has both days, a single only Tuesday.
    days = sorted(staff.working_hours.exclude(weekday=0).values_list("weekday", flat=True))
    assert days in ([TUE], [TUE, WED])
