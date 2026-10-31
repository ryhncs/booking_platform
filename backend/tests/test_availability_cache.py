"""Cached availability must never serve a slot that is no longer free.

These tests use real commits (transaction=True) so that the on_commit
invalidation actually runs, and the real Redis configured in settings.test.
"""

from datetime import timedelta
from unittest import mock

import pytest
from django.core.cache import cache
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.bookings.availability import cache_version, free_slots
from apps.bookings.services import cancel_booking, confirm_booking, create_booking
from apps.businesses.models import Business, Service, TimeOff, WorkingHours

from .conftest import next_monday_at

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def monday():
    return next_monday_at(9).date()


def starts(staff, service, day):
    return [s.strftime("%H:%M") for s, _ in free_slots(staff=staff, service=service, day=day)]


def test_cache_is_really_redis():
    # IGNORE_EXCEPTIONS makes a dead cache silent, so prove it round-trips.
    cache.set("probe", "ok", timeout=5)
    assert cache.get("probe") == "ok"


def test_second_read_is_served_from_cache(staff, service, monday, django_assert_num_queries):
    first = starts(staff, service, monday)
    with django_assert_num_queries(0):
        assert starts(staff, service, monday) == first
    assert "10:00" in first


def test_cache_is_keyed_by_service_and_date(staff, service, monday):
    other = Service.objects.create(
        business=service.business, name="Quick", duration_minutes=15, price=1
    )
    other.staff.add(staff)
    assert starts(staff, service, monday)[-1] == "16:00"  # 60 min must end by 17:00
    assert starts(staff, other, monday)[-1] == "16:45"  # 15 min fits later
    assert starts(staff, service, monday + timedelta(days=1)) == []  # no Tuesday shift


class TestStaleSlotIsNeverServed:
    def test_after_booking_is_created(self, customer, staff, service, monday):
        assert "10:00" in starts(staff, service, monday)  # warms the cache
        create_booking(customer=customer, staff=staff, service=service, start=next_monday_at(10))
        got = starts(staff, service, monday)
        assert "10:00" not in got
        assert "10:30" not in got
        assert "09:00" in got  # ends exactly when the booking starts
        assert "11:00" in got

    def test_after_booking_is_cancelled(self, customer, staff, service, monday):
        booking = create_booking(
            customer=customer, staff=staff, service=service, start=next_monday_at(10)
        )
        assert "10:00" not in starts(staff, service, monday)  # warms the cache (blocked)
        cancel_booking(booking, cancelled_by=customer)
        assert "10:00" in starts(staff, service, monday)

    def test_confirm_invalidates_too(self, customer, staff, service):
        booking = create_booking(
            customer=customer, staff=staff, service=service, start=next_monday_at(10)
        )
        before = cache_version(staff.pk)
        confirm_booking(booking)
        assert cache_version(staff.pk) != before

    def test_end_to_end_through_the_api(self, customer, make_customer, auth_client, staff, service):
        mine, rival = auth_client(customer), auth_client(make_customer())
        day = next_monday_at(9).date()
        query = {"staff": staff.pk, "service": service.pk, "date": day}

        def offered():
            resp = rival.get(reverse("availability"), query)
            return [s["start"][11:16] for s in resp.data["slots"]]

        assert "10:00" in offered()
        body = {"staff": staff.pk, "service": service.pk, "start": next_monday_at(10).isoformat()}
        assert mine.post(reverse("booking-list"), body, format="json").status_code == 201
        assert "10:00" not in offered()  # the rival must not be offered a taken slot

    def test_after_working_hours_change(self, staff, service, monday):
        assert "16:00" in starts(staff, service, monday)
        shift = WorkingHours.objects.get(staff=staff)
        shift.end_time = shift.end_time.replace(hour=12)
        shift.save()
        got = starts(staff, service, monday)
        assert "16:00" not in got
        assert got[-1] == "11:00"

    def test_after_working_hours_added_and_deleted(self, staff, service, monday):
        tuesday = monday + timedelta(days=1)
        assert starts(staff, service, tuesday) == []
        shift = WorkingHours.objects.create(
            staff=staff, weekday=1, start_time="09:00", end_time="11:00"
        )
        assert starts(staff, service, tuesday) == ["09:00", "09:15", "09:30", "09:45", "10:00"]
        shift.delete()
        assert starts(staff, service, tuesday) == []

    def test_after_time_off_added_and_removed(self, staff, service, monday):
        assert "13:00" in starts(staff, service, monday)
        off = TimeOff.objects.create(staff=staff, start=next_monday_at(12), end=next_monday_at(15))
        got = starts(staff, service, monday)
        assert "13:00" not in got
        assert "15:00" in got
        off.delete()
        assert "13:00" in starts(staff, service, monday)

    def test_after_service_duration_change(self, staff, service, monday):
        assert starts(staff, service, monday)[-1] == "16:00"
        service.duration_minutes = 120
        service.save()
        assert starts(staff, service, monday)[-1] == "15:00"

    def test_after_service_is_detached_from_staff(self, staff, service):
        before = cache_version(staff.pk)
        service.staff.remove(staff)
        assert cache_version(staff.pk) != before

    def test_after_service_staff_cleared_and_added(self, staff, service):
        before = cache_version(staff.pk)
        service.staff.clear()
        cleared = cache_version(staff.pk)
        assert cleared != before
        staff.services.add(service)  # reverse side of the relation
        assert cache_version(staff.pk) != cleared

    def test_after_service_deleted(self, staff, service):
        before = cache_version(staff.pk)
        service.delete()
        assert cache_version(staff.pk) != before

    def test_after_business_timezone_change(self, staff, service, monday):
        before = cache_version(staff.pk)
        business = Business.objects.get(pk=staff.business_id)
        business.timezone = "Europe/Berlin"
        business.save()
        assert cache_version(staff.pk) != before

    def test_after_staff_deactivated(self, staff):
        before = cache_version(staff.pk)
        staff.is_active = False
        staff.save()
        assert cache_version(staff.pk) != before


class TestInvalidationScope:
    def test_other_staff_caches_are_untouched(self, customer, staff, service, other_staff):
        other_before = cache_version(other_staff.pk)
        create_booking(customer=customer, staff=staff, service=service, start=next_monday_at(10))
        assert cache_version(other_staff.pk) == other_before

    def test_rolled_back_change_does_not_invalidate(self, customer, staff, service):
        before = cache_version(staff.pk)
        with pytest.raises(RuntimeError), transaction.atomic():
            create_booking(
                customer=customer, staff=staff, service=service, start=next_monday_at(10)
            )
            raise RuntimeError("abort")
        assert cache_version(staff.pk) == before

    def test_invalidation_waits_for_commit(self, customer, staff, service):
        before = cache_version(staff.pk)
        with transaction.atomic():
            create_booking(
                customer=customer, staff=staff, service=service, start=next_monday_at(10)
            )
            assert cache_version(staff.pk) == before  # nothing yet: not committed
        assert cache_version(staff.pk) != before


def test_past_slots_are_filtered_on_read_not_baked_into_the_cache(staff, service, monday):
    """The cached list is time-independent; "now" is applied on every read."""
    assert starts(staff, service, monday)  # populate the cache
    far_future = timezone.now() + timedelta(days=3650)
    with mock.patch("apps.bookings.availability.timezone.now", return_value=far_future):
        assert starts(staff, service, monday) == []
