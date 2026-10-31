from datetime import datetime, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.bookings.models import Booking
from apps.bookings.services import cancel_booking, create_booking
from apps.businesses.models import Business, Service, Staff, TimeOff, WorkingHours

from .conftest import next_monday_at

pytestmark = pytest.mark.django_db

URL = "availability"


@pytest.fixture
def client(customer, auth_client):
    return auth_client(customer)


@pytest.fixture
def monday():
    return next_monday_at(9).date()


def get(client, staff, service, day):
    return client.get(reverse(URL), {"staff": staff.pk, "service": service.pk, "date": day})


def starts(resp):
    return [s["start"][11:16] for s in resp.data["slots"]]


def test_requires_authentication(api_client, staff, service, monday):
    assert get(api_client, staff, service, monday).status_code == 401


def test_full_day_lists_every_quarter_hour_that_fits(client, staff, service, monday):
    resp = get(client, staff, service, monday)
    assert resp.status_code == 200
    assert resp.data["timezone"] == "Asia/Tehran"
    # 09:00-17:00 shift, 60 min service, 15 min step -> 09:00 ... 16:00
    assert len(resp.data["slots"]) == 29
    assert starts(resp)[0] == "09:00"
    assert starts(resp)[-1] == "16:00"
    first = resp.data["slots"][0]
    assert first["start"].endswith("+03:30")
    assert first["end"][11:16] == "10:00"


def test_existing_booking_blocks_overlapping_slots_only(client, customer, staff, service, monday):
    create_booking(customer=customer, staff=staff, service=service, start=next_monday_at(10))
    got = starts(get(client, staff, service, monday))
    assert "09:00" in got  # ends exactly when the booking starts
    assert "09:15" not in got
    assert "10:45" not in got
    assert "11:00" in got  # starts exactly when the booking ends


def test_cancelled_booking_frees_its_slots(client, customer, staff, service, monday):
    booking = create_booking(
        customer=customer, staff=staff, service=service, start=next_monday_at(10)
    )
    cancel_booking(booking, cancelled_by=customer)
    assert "10:00" in starts(get(client, staff, service, monday))


def test_time_off_removes_slots(client, staff, service, monday):
    TimeOff.objects.create(staff=staff, start=next_monday_at(13), end=next_monday_at(15))
    got = starts(get(client, staff, service, monday))
    assert "12:00" in got
    assert "12:15" not in got
    assert "14:45" not in got
    assert "15:00" in got


def test_day_without_a_shift_is_empty(client, staff, service, monday):
    resp = get(client, staff, service, monday + timedelta(days=1))
    assert resp.status_code == 200
    assert resp.data["slots"] == []


def test_slots_in_the_past_are_not_offered(client, staff, service):
    # Use today's local date; whatever has already started must be absent.
    today = timezone.now().astimezone(next_monday_at(9).tzinfo).date()
    resp = get(client, staff, service, today)
    assert resp.status_code == 200
    now = timezone.now()
    for slot in resp.data["slots"]:
        assert datetime.fromisoformat(slot["start"]) > now


def test_offered_slot_is_actually_bookable(client, customer, staff, service, monday):
    slot = get(client, staff, service, monday).data["slots"][5]
    booking = create_booking(
        customer=customer,
        staff=staff,
        service=service,
        start=datetime.fromisoformat(slot["start"]),
    )
    assert booking.status == Booking.Status.PENDING


@pytest.mark.parametrize("offset", [-1, 181])
def test_date_out_of_range_is_400(client, staff, service, offset):
    day = timezone.now().date() + timedelta(days=offset)
    assert get(client, staff, service, day).status_code == 400


def test_bad_date_is_400(client, staff, service):
    assert get(client, staff, service, "not-a-date").status_code == 400


def test_missing_params_is_400(client):
    assert client.get(reverse(URL)).status_code == 400


def test_staff_who_does_not_offer_service_is_400(client, owner, staff, service, monday):
    other = Service.objects.create(
        business=service.business, name="Other", duration_minutes=30, price=1
    )
    assert get(client, staff, other, monday).status_code == 400


def test_service_from_another_business_is_400(client, staff, other_business, monday):
    foreign = Service.objects.create(
        business=other_business, name="Shave", duration_minutes=30, price=1
    )
    assert get(client, staff, foreign, monday).status_code == 400


def test_inactive_staff_is_404(client, staff, service, monday):
    staff.is_active = False
    staff.save()
    assert get(client, staff, service, monday).status_code == 404


def test_unknown_staff_is_404(client, staff, service, monday):
    staff.pk += 999
    assert get(client, staff, service, monday).status_code == 404


def test_uses_business_timezone_for_the_date(client, owner, monday):
    """The same wall-clock hours exist in any zone; only the offset changes."""
    berlin = Business.objects.create(owner=owner, name="B", slug="b", timezone="Europe/Berlin")
    s = Staff.objects.create(business=berlin, display_name="Z")
    WorkingHours.objects.create(
        staff=s, weekday=monday.weekday(), start_time="09:00", end_time="10:00"
    )
    svc = Service.objects.create(business=berlin, name="S", duration_minutes=30, price=1)
    svc.staff.add(s)
    resp = get(client, s, svc, monday)
    assert starts(resp) == ["09:00", "09:15", "09:30"]
    assert resp.data["slots"][0]["start"][-6:] in ("+01:00", "+02:00")
