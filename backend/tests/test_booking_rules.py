from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError

from apps.bookings.models import Booking
from apps.bookings.services import (
    InvalidBookingRequest,
    OutsideWorkingHours,
    SlotUnavailable,
    cancel_booking,
    confirm_booking,
    create_booking,
)
from apps.businesses.models import Service, Staff, TimeOff

from .conftest import next_monday_at

pytestmark = pytest.mark.django_db


def test_creates_pending_booking_with_duration_from_service(customer, staff, service):
    start = next_monday_at(10)
    b = create_booking(customer=customer, staff=staff, service=service, start=start)
    assert b.status == Booking.Status.PENDING
    assert b.end - b.start == timedelta(minutes=60)
    assert b.expires_at is not None


def test_overlapping_booking_is_rejected(customer, make_customer, staff, service):
    create_booking(customer=customer, staff=staff, service=service, start=next_monday_at(10))
    with pytest.raises(SlotUnavailable):
        create_booking(
            customer=make_customer(), staff=staff, service=service, start=next_monday_at(10, 30)
        )


def test_back_to_back_bookings_are_allowed(customer, make_customer, staff, service):
    create_booking(customer=customer, staff=staff, service=service, start=next_monday_at(10))
    b2 = create_booking(
        customer=make_customer(), staff=staff, service=service, start=next_monday_at(11)
    )
    assert b2.pk


def test_cancelled_booking_frees_the_slot(customer, make_customer, staff, service):
    first = create_booking(
        customer=customer, staff=staff, service=service, start=next_monday_at(10)
    )
    cancel_booking(first)
    again = create_booking(
        customer=make_customer(), staff=staff, service=service, start=next_monday_at(10)
    )
    assert again.status == Booking.Status.PENDING


def test_different_staff_can_share_a_time(customer, make_customer, business, staff, service):
    other = Staff.objects.create(business=business, display_name="Mina")
    other.working_hours.create(
        weekday=0,
        start_time=staff.working_hours.first().start_time,
        end_time=staff.working_hours.first().end_time,
    )
    service.staff.add(other)
    create_booking(customer=customer, staff=staff, service=service, start=next_monday_at(10))
    assert create_booking(
        customer=make_customer(), staff=other, service=service, start=next_monday_at(10)
    ).pk


def test_constraint_holds_even_when_service_layer_is_bypassed(customer, staff, service):
    """The guarantee lives in the database, not only in Python."""
    start = next_monday_at(10)
    Booking.objects.create(
        customer=customer, staff=staff, service=service, start=start, end=start + timedelta(hours=1)
    )
    with pytest.raises(IntegrityError):
        Booking.objects.create(
            customer=customer,
            staff=staff,
            service=service,
            start=start + timedelta(minutes=15),
            end=start + timedelta(minutes=75),
        )


@pytest.mark.parametrize("hour,minute", [(8, 30), (16, 30), (17, 0)])
def test_outside_working_hours_is_rejected(customer, staff, service, hour, minute):
    with pytest.raises(OutsideWorkingHours):
        create_booking(
            customer=customer, staff=staff, service=service, start=next_monday_at(hour, minute)
        )


def test_last_slot_ending_exactly_at_close_is_allowed(customer, staff, service):
    assert create_booking(
        customer=customer, staff=staff, service=service, start=next_monday_at(16)
    ).pk


def test_time_off_blocks_booking(customer, staff, service):
    TimeOff.objects.create(staff=staff, start=next_monday_at(12), end=next_monday_at(14))
    with pytest.raises(SlotUnavailable):
        create_booking(
            customer=customer, staff=staff, service=service, start=next_monday_at(13, 30)
        )


def test_staff_must_offer_the_service(customer, business, staff):
    other = Service.objects.create(
        business=business, name="Color", duration_minutes=90, price=Decimal("1")
    )
    with pytest.raises(InvalidBookingRequest):
        create_booking(customer=customer, staff=staff, service=other, start=next_monday_at(10))


def test_past_start_is_rejected(customer, staff, service):
    with pytest.raises(InvalidBookingRequest):
        create_booking(
            customer=customer,
            staff=staff,
            service=service,
            start=next_monday_at(10) - timedelta(days=14),
        )


def test_confirm_then_cannot_confirm_again(customer, staff, service):
    b = create_booking(customer=customer, staff=staff, service=service, start=next_monday_at(10))
    b = confirm_booking(b)
    assert b.status == Booking.Status.CONFIRMED and b.expires_at is None
    with pytest.raises(InvalidBookingRequest):
        confirm_booking(b)
