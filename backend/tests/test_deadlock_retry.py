"""Deterministic coverage of the 40P01 retry path in create_booking.

A real deadlock can't be provoked on demand, so Booking.objects.create is
patched to raise what Django raises for one: an OperationalError whose cause is
psycopg's DeadlockDetected. test_concurrency.py covers the real race.
"""

from unittest import mock

import psycopg
import pytest
from django.db import OperationalError

from apps.bookings.models import Booking
from apps.bookings.services import DEADLOCK_RETRIES, SlotUnavailable, create_booking

from .conftest import next_monday_at

pytestmark = pytest.mark.django_db


def deadlock():
    err = OperationalError("deadlock detected")
    err.__cause__ = psycopg.errors.DeadlockDetected("deadlock detected")
    return err


def patched_create(failures, error=deadlock):
    real = Booking.objects.create
    calls = {"n": 0}

    def create(**kwargs):
        calls["n"] += 1
        if calls["n"] <= failures:
            raise error()
        return real(**kwargs)

    return create, calls


def book(customer, staff, service):
    return create_booking(customer=customer, staff=staff, service=service, start=next_monday_at(10))


def test_retries_after_a_deadlock_and_succeeds(customer, staff, service):
    create, calls = patched_create(failures=DEADLOCK_RETRIES - 1)
    with mock.patch.object(Booking.objects, "create", create):
        booking = book(customer, staff, service)
    assert booking.pk
    assert calls["n"] == DEADLOCK_RETRIES


def test_gives_up_with_slot_unavailable_after_max_retries(customer, staff, service):
    create, calls = patched_create(failures=DEADLOCK_RETRIES + 5)
    with mock.patch.object(Booking.objects, "create", create), pytest.raises(SlotUnavailable):
        book(customer, staff, service)
    assert calls["n"] == DEADLOCK_RETRIES
    assert not Booking.objects.exists()


def test_other_operational_errors_are_not_swallowed(customer, staff, service):
    create, calls = patched_create(failures=1, error=lambda: OperationalError("connection lost"))
    with mock.patch.object(Booking.objects, "create", create), pytest.raises(OperationalError):
        book(customer, staff, service)
    assert calls["n"] == 1
