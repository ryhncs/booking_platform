"""POST /api/working-hours/bulk/: the same shift on several weekdays at once."""

from datetime import time, timedelta

import pytest
from django.urls import reverse

from apps.bookings.availability import cache_version, free_slots
from apps.businesses.models import WorkingHours

from .conftest import next_monday_at

URL = "working-hours-bulk"
MON, TUE, WED, THU, SAT, SUN = 0, 1, 2, 3, 5, 6


def post(client, staff, weekdays, start="09:00", end="13:00"):
    body = {"staff": staff.pk, "weekdays": weekdays, "start_time": start, "end_time": end}
    return client.post(reverse(URL), body, format="json")


def days_of(staff):
    return sorted(staff.working_hours.values_list("weekday", flat=True))


@pytest.mark.django_db
class TestBulkCreate:
    def test_creates_one_shift_per_day(self, owner, auth_client, staff):
        resp = post(auth_client(owner), staff, [SAT, SUN, TUE, WED])

        assert resp.status_code == 201
        assert [s["weekday"] for s in resp.data] == [TUE, WED, SAT, SUN]
        assert {(s["start_time"], s["end_time"]) for s in resp.data} == {("09:00:00", "13:00:00")}
        assert days_of(staff) == [MON, TUE, WED, SAT, SUN]  # fixture's Monday + 4 new

    def test_duplicate_days_are_ignored(self, owner, auth_client, staff):
        resp = post(auth_client(owner), staff, [TUE, TUE, WED])
        assert resp.status_code == 201
        assert len(resp.data) == 2

    def test_overlap_on_any_day_rejects_everything_and_names_the_days(
        self, owner, auth_client, staff
    ):
        WorkingHours.objects.create(
            staff=staff, weekday=WED, start_time=time(12), end_time=time(14)
        )
        # Monday 09:00-17:00 comes from the fixture.
        resp = post(auth_client(owner), staff, [MON, TUE, WED, THU], start="10:00", end="12:30")

        assert resp.status_code == 400
        assert resp.data["weekdays"] == [
            "Overlaps existing hours on Monday, Wednesday. Nothing was added."
        ]
        assert days_of(staff) == [MON, WED]  # Tuesday and Thursday were not created

    def test_adjacent_hours_are_not_an_overlap(self, owner, auth_client, staff):
        resp = post(auth_client(owner), staff, [MON], start="17:00", end="20:00")
        assert resp.status_code == 201

    @pytest.mark.parametrize(
        ("weekdays", "start", "end", "field"),
        [
            ([], "09:00", "13:00", "weekdays"),
            ([7], "09:00", "13:00", "weekdays"),
            ([TUE], "13:00", "09:00", "end_time"),
            ([TUE], "09:00", "09:00", "end_time"),
        ],
    )
    def test_invalid_input(self, owner, auth_client, staff, weekdays, start, end, field):
        resp = post(auth_client(owner), staff, weekdays, start, end)
        assert resp.status_code == 400
        assert field in resp.data
        assert days_of(staff) == [MON]


@pytest.mark.django_db
class TestPermissions:
    def test_anonymous_is_401(self, api_client, staff):
        assert post(api_client, staff, [TUE]).status_code == 401

    def test_customer_is_403(self, customer, auth_client, staff):
        assert post(auth_client(customer), staff, [TUE]).status_code == 403
        assert days_of(staff) == [MON]

    def test_other_owner_cannot_add_hours_to_my_staff(self, other_owner, auth_client, staff):
        resp = post(auth_client(other_owner), staff, [TUE, WED])
        # Same as the single-shift endpoint: not a staff member they own.
        assert resp.status_code == 400
        assert "staff" in resp.data
        assert days_of(staff) == [MON]


@pytest.mark.django_db(transaction=True)
class TestCacheInvalidation:
    """bulk_create skips signals, so the endpoint must invalidate by itself."""

    def test_new_hours_show_up_in_cached_availability(self, owner, auth_client, staff, service):
        tuesday = next_monday_at(9).date() + timedelta(days=1)
        assert free_slots(staff=staff, service=service, day=tuesday) == []  # cached: no shift

        resp = post(auth_client(owner), staff, [TUE], start="09:00", end="11:00")
        assert resp.status_code == 201

        slots = free_slots(staff=staff, service=service, day=tuesday)
        assert [s.strftime("%H:%M") for s, _ in slots] == [
            "09:00",
            "09:15",
            "09:30",
            "09:45",
            "10:00",
        ]

    def test_version_bumps_on_success_only(self, owner, auth_client, staff):
        before = cache_version(staff.pk)
        assert post(auth_client(owner), staff, [MON]).status_code == 400  # overlaps Monday
        assert cache_version(staff.pk) == before
        assert post(auth_client(owner), staff, [TUE]).status_code == 201
        assert cache_version(staff.pk) != before
