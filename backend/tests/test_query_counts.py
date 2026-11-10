"""SQL statements per endpoint, asserted exactly, so an N+1 regression fails CI.

Requests use a real JWT, so the numbers include the one query that loads the
user. List endpoints are measured small and then with many more rows: the count
must not grow. SAVEPOINT/RELEASE are left out because they exist only as an
artefact of the test wrapping everything in a transaction.

These numbers are published in docs/BENCHMARKS.md: update both together.
"""

from datetime import time, timedelta

import pytest
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.bookings.models import Booking
from apps.bookings.services import create_booking
from apps.businesses.models import Business, Service, Staff, WorkingHours

from .conftest import next_monday_at

pytestmark = pytest.mark.django_db

# Every endpoint's SQL statement count; the single source for the tests below.
ME = 1
BUSINESSES_LIST = 3
STAFF_LIST = 3
SERVICES_LIST = 4
WORKING_HOURS_LIST = 3
AVAILABILITY_COLD = 7
AVAILABILITY_CACHED = 4
BOOKINGS_LIST = 3
BOOKING_CREATE = 7
BOOKING_CONFIRM = 8
BOOKING_CANCEL = 8


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
    return client


def sql_count(call):
    with CaptureQueriesContext(connection) as ctx:
        response = call()
    assert response.status_code < 300, response.data
    return sum(
        not q["sql"].startswith(("SAVEPOINT", "RELEASE SAVEPOINT")) for q in ctx.captured_queries
    )


def assert_flat(call, grow, expected):
    """The count equals `expected` and stays there after `grow` adds many rows."""
    small = sql_count(call)
    grow()
    large = sql_count(call)
    assert (small, large) == (expected, expected)


def add_bookings(customer, staff, service, *, days_ahead, count):
    start = timezone.now() + timedelta(days=days_ahead)
    for i in range(count):
        at = start + timedelta(days=i)
        Booking.objects.create(
            customer=customer,
            staff=staff,
            service=service,
            start=at,
            end=at + timedelta(hours=1),
        )


def test_me(customer):
    assert sql_count(lambda: client_for(customer).get(reverse("me"))) == ME


def test_businesses_list_is_flat(customer, owner, business):
    def grow():
        for i in range(15):
            Business.objects.create(owner=owner, name=f"B{i}", slug=f"b{i}")

    client = client_for(customer)
    assert_flat(lambda: client.get(reverse("business-list")), grow, BUSINESSES_LIST)


def test_staff_list_is_flat(customer, business, staff):
    def grow():
        for i in range(15):
            Staff.objects.create(business=business, display_name=f"S{i}")

    client = client_for(customer)
    url = reverse("staff-list")
    assert_flat(lambda: client.get(url, {"business": business.pk}), grow, STAFF_LIST)


def test_services_list_is_flat(customer, business, staff, service):
    def grow():
        members = [Staff.objects.create(business=business, display_name=f"S{i}") for i in range(5)]
        for i in range(15):
            extra = Service.objects.create(
                business=business, name=f"Svc{i}", duration_minutes=30, price=1
            )
            extra.staff.set(members)

    client = client_for(customer)
    url = reverse("service-list")
    assert_flat(lambda: client.get(url, {"business": business.pk}), grow, SERVICES_LIST)


def test_working_hours_list_is_flat(customer, staff):
    def grow():
        for weekday in range(1, 7):
            for hour in (8, 12, 16):
                WorkingHours.objects.create(
                    staff=staff, weekday=weekday, start_time=time(hour), end_time=time(hour + 2)
                )

    client = client_for(customer)
    url = reverse("working-hours-list")
    assert_flat(lambda: client.get(url, {"staff": staff.pk}), grow, WORKING_HOURS_LIST)


class TestAvailability:
    @pytest.fixture
    def get(self, customer, staff, service):
        client = client_for(customer)
        params = {"staff": staff.pk, "service": service.pk, "date": next_monday_at(9).date()}
        return lambda: client.get(reverse("availability"), params)

    def test_cold_is_flat_however_busy_the_day_is(self, get, make_customer, staff, service):
        def grow():
            for hour in (9, 11, 13, 15):
                create_booking(
                    customer=make_customer(),
                    staff=staff,
                    service=service,
                    start=next_monday_at(hour),
                )
            cache.clear()

        assert_flat(get, grow, AVAILABILITY_COLD)

    def test_cached_skips_the_schedule_queries(self, get):
        get()  # fills the cache
        assert sql_count(get) == AVAILABILITY_CACHED


def test_bookings_list_is_flat(customer, staff, service):
    add_bookings(customer, staff, service, days_ahead=30, count=1)
    client = client_for(customer)
    assert_flat(
        lambda: client.get(reverse("booking-list"), {"scope": "mine"}),
        lambda: add_bookings(customer, staff, service, days_ahead=60, count=12),
        BOOKINGS_LIST,
    )


class TestBookingWrites:
    def test_create(self, customer, staff, service):
        body = {
            "staff": staff.pk,
            "service": service.pk,
            "start": next_monday_at(10).isoformat(),
        }
        client = client_for(customer)
        count = sql_count(lambda: client.post(reverse("booking-list"), body, format="json"))
        assert count == BOOKING_CREATE

    def test_confirm(self, customer, staff, service):
        booking = create_booking(
            customer=customer, staff=staff, service=service, start=next_monday_at(10)
        )
        url = reverse("booking-confirm", args=[booking.pk])
        assert sql_count(lambda: client_for(customer).post(url)) == BOOKING_CONFIRM

    def test_cancel(self, customer, staff, service):
        booking = create_booking(
            customer=customer, staff=staff, service=service, start=next_monday_at(10)
        )
        url = reverse("booking-cancel", args=[booking.pk])
        assert sql_count(lambda: client_for(customer).post(url)) == BOOKING_CANCEL
