"""API details the frontend relies on: business context on bookings, the
scope filter, and the timezone list."""

import pytest
from django.urls import reverse

from apps.bookings.services import create_booking
from apps.businesses.models import Business, Service, Staff, WorkingHours

from .conftest import next_monday_at

pytestmark = pytest.mark.django_db


@pytest.fixture
def booking(customer, staff, service):
    return create_booking(customer=customer, staff=staff, service=service, start=next_monday_at(10))


def ids(resp):
    return [b["id"] for b in resp.data["results"]]


def test_booking_carries_business_context_for_display(customer, auth_client, booking):
    customer.first_name, customer.last_name = "Cy", "Rus"
    customer.save()
    data = auth_client(customer).get(reverse("booking-detail", args=[booking.pk])).data
    assert data["business"] == booking.staff.business_id
    assert data["business_name"] == "Salon"
    assert data["business_timezone"] == "Asia/Tehran"
    assert data["customer_name"] == "Cy Rus"


def test_customer_name_falls_back_to_email(customer, auth_client, booking):
    data = auth_client(customer).get(reverse("booking-detail", args=[booking.pk])).data
    assert data["customer_name"] == "cust@example.com"


class TestScope:
    @pytest.fixture
    def owners_own_booking(self, owner, other_business):
        """The owner of "Salon" books at someone else's business as a customer."""
        staff = Staff.objects.create(business=other_business, display_name="Bob")
        WorkingHours.objects.create(staff=staff, weekday=0, start_time="09:00", end_time="17:00")
        svc = Service.objects.create(
            business=other_business, name="Shave", duration_minutes=30, price=1
        )
        svc.staff.add(staff)
        # other_business runs on UTC: 14:00 Tehran is 10:30 UTC, inside its shift.
        return create_booking(customer=owner, staff=staff, service=svc, start=next_monday_at(14))

    def test_default_returns_both(self, owner, auth_client, booking, owners_own_booking):
        resp = auth_client(owner).get(reverse("booking-list"))
        assert sorted(ids(resp)) == sorted([booking.pk, owners_own_booking.pk])

    def test_mine_is_only_bookings_i_made(self, owner, auth_client, booking, owners_own_booking):
        resp = auth_client(owner).get(reverse("booking-list"), {"scope": "mine"})
        assert ids(resp) == [owners_own_booking.pk]

    def test_business_is_only_bookings_at_my_businesses(
        self, owner, auth_client, booking, owners_own_booking
    ):
        resp = auth_client(owner).get(reverse("booking-list"), {"scope": "business"})
        assert ids(resp) == [booking.pk]

    def test_customer_with_business_scope_sees_nothing(self, customer, auth_client, booking):
        resp = auth_client(customer).get(reverse("booking-list"), {"scope": "business"})
        assert resp.data["count"] == 0

    def test_invalid_scope_is_400(self, customer, auth_client):
        resp = auth_client(customer).get(reverse("booking-list"), {"scope": "everyone"})
        assert resp.status_code == 400


class TestTimezones:
    def test_lists_exactly_what_the_validator_accepts(self, customer, auth_client, owner):
        names = auth_client(customer).get(reverse("timezones")).data
        assert names == sorted(names)
        assert "Asia/Tehran" in names
        assert "UTC" in names
        # every listed name is accepted by the model validator
        business = Business(owner=owner, name="T", slug="t")
        for name in ("Asia/Tehran", names[0], names[-1]):
            business.timezone = name
            business.full_clean()

    def test_requires_authentication(self, api_client):
        assert api_client.get(reverse("timezones")).status_code == 401


def test_list_does_not_query_per_booking(
    customer, auth_client, staff, service, django_assert_max_num_queries
):
    for hour in (9, 11, 13):
        create_booking(customer=customer, staff=staff, service=service, start=next_monday_at(hour))
    with django_assert_max_num_queries(2):  # COUNT for pagination + one joined SELECT
        auth_client(customer).get(reverse("booking-list"))
