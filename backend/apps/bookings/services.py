"""Booking domain logic.

All writes to ``Booking`` go through these functions, so the rules live in
one place instead of being scattered across views and serializers.

Correctness split:
* The *no double-booking* rule is enforced by PostgreSQL (exclusion
  constraint), so it holds under any amount of concurrency.
* Business rules that depend on other tables (working hours, time off,
  which staff offer which service) are validated here in Python.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg
from django.db import IntegrityError, OperationalError, transaction
from django.utils import timezone

from apps.businesses.models import Service, Staff, TimeOff

from .models import Booking

OVERLAP_CONSTRAINT = "booking_no_overlap_per_staff"
PENDING_HOLD = timedelta(minutes=10)
DEADLOCK_RETRIES = 3


class BookingError(Exception):
    """Base class for rule violations a client can act on."""

    code = "booking_error"


class SlotUnavailable(BookingError):
    code = "slot_unavailable"


class OutsideWorkingHours(BookingError):
    code = "outside_working_hours"


class InvalidBookingRequest(BookingError):
    code = "invalid_request"


def _fits_working_hours(staff: Staff, start: datetime, end: datetime) -> bool:
    tz = ZoneInfo(staff.business.timezone)
    local_start, local_end = start.astimezone(tz), end.astimezone(tz)
    if local_start.date() != local_end.date():
        return False  # shifts never cross midnight in this model
    return staff.working_hours.filter(
        weekday=local_start.weekday(),
        start_time__lte=local_start.time(),
        end_time__gte=local_end.time(),
    ).exists()


def create_booking(
    *, customer, staff: Staff, service: Service, start: datetime, notes: str = ""
) -> Booking:
    if timezone.is_naive(start):
        raise InvalidBookingRequest("start must include a timezone offset")
    if start <= timezone.now():
        raise InvalidBookingRequest("start must be in the future")
    if not (staff.is_active and service.is_active):
        raise InvalidBookingRequest("staff member or service is not available")
    if staff.business_id != service.business_id or not service.staff.filter(pk=staff.pk).exists():
        raise InvalidBookingRequest("this staff member does not offer this service")

    end = start + timedelta(minutes=service.duration_minutes)

    if not _fits_working_hours(staff, start, end):
        raise OutsideWorkingHours("requested time is outside the staff member's working hours")
    if TimeOff.objects.filter(staff=staff, start__lt=end, end__gt=start).exists():
        raise SlotUnavailable("staff member is unavailable at that time")

    # An exclusion constraint is checked against *uncommitted* rows too. When
    # two transactions insert conflicting ranges at the same instant, each can
    # find the other's pending tuple and wait for it to finish; PostgreSQL
    # resolves that cycle by aborting one of them with a deadlock error
    # (SQLSTATE 40P01) instead of the usual exclusion violation. Nothing was
    # written, so the insert is safe to retry: the retry either wins the slot
    # or now sees the committed rival row and fails cleanly with SlotUnavailable.
    for attempt in range(1, DEADLOCK_RETRIES + 1):
        try:
            # Savepoint: if the insert fails, only it is rolled back, leaving
            # any surrounding transaction usable.
            with transaction.atomic():
                return Booking.objects.create(
                    customer=customer,
                    staff=staff,
                    service=service,
                    start=start,
                    end=end,
                    status=Booking.Status.PENDING,
                    expires_at=timezone.now() + PENDING_HOLD,
                    notes=notes,
                )
        except IntegrityError as exc:
            if OVERLAP_CONSTRAINT in str(exc):
                raise SlotUnavailable("this slot has just been taken") from exc
            raise
        except OperationalError as exc:
            if not isinstance(exc.__cause__, psycopg.errors.DeadlockDetected):
                raise
            if attempt == DEADLOCK_RETRIES:
                raise SlotUnavailable("this slot is being contended; please retry") from exc
    raise AssertionError("unreachable")  # pragma: no cover


def confirm_booking(booking: Booking) -> Booking:
    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=booking.pk)
        if booking.status != Booking.Status.PENDING:
            raise InvalidBookingRequest(f"cannot confirm a {booking.status} booking")
        if booking.expires_at and booking.expires_at <= timezone.now():
            raise InvalidBookingRequest("the hold on this booking has expired")
        booking.status = Booking.Status.CONFIRMED
        booking.expires_at = None
        booking.save(update_fields=["status", "expires_at", "updated_at"])
    return booking


def cancel_booking(booking: Booking, *, cancelled_by, reason: str = "") -> Booking:
    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=booking.pk)
        if booking.status not in (Booking.Status.PENDING, Booking.Status.CONFIRMED):
            raise InvalidBookingRequest(f"cannot cancel a {booking.status} booking")
        booking.status = Booking.Status.CANCELLED
        booking.expires_at = None
        booking.cancelled_by = cancelled_by
        booking.cancellation_reason = reason
        booking.save(
            update_fields=[
                "status",
                "expires_at",
                "cancelled_by",
                "cancellation_reason",
                "updated_at",
            ]
        )
    return booking
