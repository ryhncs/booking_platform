from datetime import time, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.bookings.models import Booking
from apps.businesses.models import Business, Service, Staff, WorkingHours

pytestmark = pytest.mark.django_db


def url(name, pk=None):
    return reverse(f"{name}-list" if pk is None else f"{name}-detail", args=[pk] if pk else [])


@pytest.fixture
def owner_client(owner, auth_client):
    return auth_client(owner)


@pytest.fixture
def other_client(other_owner, auth_client):
    return auth_client(other_owner)


@pytest.fixture
def customer_client(customer, auth_client):
    return auth_client(customer)


class TestAuthentication:
    @pytest.mark.parametrize("name", ["business", "staff", "service", "working-hours"])
    def test_anonymous_is_rejected(self, api_client, name):
        assert api_client.get(url(name)).status_code == 401
        assert api_client.post(url(name), {}, format="json").status_code == 401


class TestBusiness:
    def test_owner_creates_business_owned_by_self(self, owner, owner_client):
        resp = owner_client.post(
            url("business"),
            {"name": "Spa", "slug": "spa", "timezone": "Europe/Berlin", "owner": 999},
            format="json",
        )
        assert resp.status_code == 201
        assert Business.objects.get(slug="spa").owner == owner

    def test_invalid_timezone_rejected(self, owner_client):
        resp = owner_client.post(
            url("business"), {"name": "X", "slug": "x", "timezone": "Mars/Olympus"}, format="json"
        )
        assert resp.status_code == 400
        assert "timezone" in resp.data

    def test_duplicate_slug_rejected(self, business, owner_client):
        resp = owner_client.post(url("business"), {"name": "Dup", "slug": "salon"}, format="json")
        assert resp.status_code == 400

    def test_owner_updates_and_deletes_own_business(self, business, owner_client):
        resp = owner_client.patch(url("business", business.pk), {"name": "New"}, format="json")
        assert resp.status_code == 200
        assert owner_client.delete(url("business", business.pk)).status_code == 204
        assert not Business.objects.filter(pk=business.pk).exists()

    def test_customer_can_read_but_not_write(self, business, customer_client):
        assert customer_client.get(url("business")).data["count"] == 1
        assert customer_client.get(url("business", business.pk)).status_code == 200
        body = {"name": "Hack", "slug": "hack"}
        assert customer_client.post(url("business"), body, format="json").status_code == 403
        patch = customer_client.patch(url("business", business.pk), {"name": "Hack"}, format="json")
        assert patch.status_code == 403
        assert customer_client.delete(url("business", business.pk)).status_code == 403
        business.refresh_from_db()
        assert business.name == "Salon"

    def test_other_owner_cannot_modify_or_delete(self, business, other_client):
        patch = other_client.patch(url("business", business.pk), {"name": "Hack"}, format="json")
        assert patch.status_code == 404
        assert other_client.delete(url("business", business.pk)).status_code == 404
        business.refresh_from_db()
        assert business.name == "Salon"

    def test_mine_filter(self, business, other_business, owner_client):
        resp = owner_client.get(url("business"), {"mine": "true"})
        assert [b["slug"] for b in resp.data["results"]] == ["salon"]

    def test_delete_with_bookings_is_409(self, business, staff, service, customer, owner_client):
        Booking.objects.create(
            customer=customer,
            staff=staff,
            service=service,
            start=timezone.now() + timedelta(days=1),
            end=timezone.now() + timedelta(days=1, hours=1),
        )
        assert owner_client.delete(url("business", business.pk)).status_code == 409
        assert Business.objects.filter(pk=business.pk).exists()


class TestStaff:
    def test_owner_creates_staff_in_own_business(self, business, owner_client):
        resp = owner_client.post(
            url("staff"), {"business": business.pk, "display_name": "Nia"}, format="json"
        )
        assert resp.status_code == 201
        assert Staff.objects.filter(business=business, display_name="Nia").exists()

    def test_cannot_create_staff_in_another_owners_business(self, other_business, owner_client):
        resp = owner_client.post(
            url("staff"), {"business": other_business.pk, "display_name": "Mole"}, format="json"
        )
        assert resp.status_code == 400
        assert not Staff.objects.filter(display_name="Mole").exists()

    def test_customer_cannot_create_staff(self, business, customer_client):
        resp = customer_client.post(
            url("staff"), {"business": business.pk, "display_name": "Nia"}, format="json"
        )
        assert resp.status_code == 403

    def test_other_owner_cannot_touch_staff(self, staff, other_client):
        patch = other_client.patch(url("staff", staff.pk), {"display_name": "X"}, format="json")
        assert patch.status_code == 404
        assert other_client.delete(url("staff", staff.pk)).status_code == 404
        staff.refresh_from_db()
        assert staff.display_name == "Sara"

    def test_cannot_move_staff_to_another_business(self, staff, other_business, other_client):
        # Even the *other* owner can't pull it in: it isn't theirs to edit.
        resp = other_client.patch(
            url("staff", staff.pk), {"business": other_business.pk}, format="json"
        )
        assert resp.status_code == 404

    def test_owner_cannot_reassign_own_staff_to_another_business(self, owner, staff, owner_client):
        second = Business.objects.create(owner=owner, name="Second", slug="second")
        resp = owner_client.patch(url("staff", staff.pk), {"business": second.pk}, format="json")
        assert resp.status_code == 400

    def test_inactive_staff_hidden_from_customers_but_not_owner(
        self, staff, owner_client, customer_client
    ):
        staff.is_active = False
        staff.save()
        assert customer_client.get(url("staff")).data["count"] == 0
        assert owner_client.get(url("staff")).data["count"] == 1

    def test_filter_by_business(self, staff, other_staff, customer_client, business):
        resp = customer_client.get(url("staff"), {"business": business.pk})
        assert [s["id"] for s in resp.data["results"]] == [staff.pk]

    def test_bad_filter_value_is_400(self, customer_client):
        assert customer_client.get(url("staff"), {"business": "abc"}).status_code == 400


class TestService:
    payload = {"name": "Color", "duration_minutes": 90, "price": "400000.00"}

    def test_owner_creates_service_with_staff(self, business, staff, owner_client):
        resp = owner_client.post(
            url("service"),
            {**self.payload, "business": business.pk, "staff": [staff.pk]},
            format="json",
        )
        assert resp.status_code == 201
        assert Service.objects.get(name="Color").staff.get() == staff

    def test_cannot_create_service_in_another_business(self, other_business, owner_client):
        resp = owner_client.post(
            url("service"), {**self.payload, "business": other_business.pk}, format="json"
        )
        assert resp.status_code == 400

    def test_cannot_attach_another_owners_staff(self, business, other_staff, owner_client):
        resp = owner_client.post(
            url("service"),
            {**self.payload, "business": business.pk, "staff": [other_staff.pk]},
            format="json",
        )
        assert resp.status_code == 400

    def test_cannot_attach_own_staff_from_a_different_business(self, owner, business, owner_client):
        second = Business.objects.create(owner=owner, name="Second", slug="second")
        foreign = Staff.objects.create(business=second, display_name="Elsewhere")
        resp = owner_client.post(
            url("service"),
            {**self.payload, "business": business.pk, "staff": [foreign.pk]},
            format="json",
        )
        assert resp.status_code == 400

    @pytest.mark.parametrize(
        "bad", [{"price": "-1"}, {"duration_minutes": 1}, {"duration_minutes": 9999}]
    )
    def test_invalid_values_rejected(self, business, owner_client, bad):
        resp = owner_client.post(
            url("service"), {**self.payload, "business": business.pk, **bad}, format="json"
        )
        assert resp.status_code == 400

    def test_customer_can_list_but_not_write(self, service, customer_client):
        assert customer_client.get(url("service")).data["count"] == 1
        resp = customer_client.patch(url("service", service.pk), {"price": "1"}, format="json")
        assert resp.status_code == 403

    def test_other_owner_cannot_touch_service(self, service, other_client):
        patch = other_client.patch(url("service", service.pk), {"price": "1"}, format="json")
        assert patch.status_code == 404
        assert other_client.delete(url("service", service.pk)).status_code == 404
        assert Service.objects.filter(pk=service.pk).exists()

    def test_filter_by_staff(self, service, staff, customer_client):
        assert customer_client.get(url("service"), {"staff": staff.pk}).data["count"] == 1
        assert customer_client.get(url("service"), {"staff": staff.pk + 99}).data["count"] == 0


class TestWorkingHours:
    def test_owner_creates_shift(self, staff, owner_client):
        resp = owner_client.post(
            url("working-hours"),
            {"staff": staff.pk, "weekday": 1, "start_time": "09:00", "end_time": "12:00"},
            format="json",
        )
        assert resp.status_code == 201

    def test_end_must_be_after_start(self, staff, owner_client):
        resp = owner_client.post(
            url("working-hours"),
            {"staff": staff.pk, "weekday": 1, "start_time": "12:00", "end_time": "09:00"},
            format="json",
        )
        assert resp.status_code == 400

    def test_overlapping_shift_rejected(self, staff, owner_client):
        # fixture has Monday 09:00-17:00
        resp = owner_client.post(
            url("working-hours"),
            {"staff": staff.pk, "weekday": 0, "start_time": "16:00", "end_time": "20:00"},
            format="json",
        )
        assert resp.status_code == 400

    def test_adjacent_shift_allowed(self, staff, owner_client):
        resp = owner_client.post(
            url("working-hours"),
            {"staff": staff.pk, "weekday": 0, "start_time": "17:00", "end_time": "20:00"},
            format="json",
        )
        assert resp.status_code == 201

    def test_update_does_not_conflict_with_itself(self, staff, owner_client):
        shift = WorkingHours.objects.get(staff=staff)
        resp = owner_client.patch(
            url("working-hours", shift.pk), {"end_time": "18:00"}, format="json"
        )
        assert resp.status_code == 200
        shift.refresh_from_db()
        assert shift.end_time == time(18)

    def test_cannot_add_shift_to_another_owners_staff(self, other_staff, owner_client):
        resp = owner_client.post(
            url("working-hours"),
            {"staff": other_staff.pk, "weekday": 1, "start_time": "09:00", "end_time": "12:00"},
            format="json",
        )
        assert resp.status_code == 400
        assert not WorkingHours.objects.filter(staff=other_staff).exists()

    def test_other_owner_cannot_touch_shift(self, staff, other_client):
        shift = WorkingHours.objects.get(staff=staff)
        patch = other_client.patch(
            url("working-hours", shift.pk), {"end_time": "18:00"}, format="json"
        )
        assert patch.status_code == 404
        assert other_client.delete(url("working-hours", shift.pk)).status_code == 404

    def test_customer_cannot_write_shift(self, staff, customer_client):
        resp = customer_client.post(
            url("working-hours"),
            {"staff": staff.pk, "weekday": 1, "start_time": "09:00", "end_time": "12:00"},
            format="json",
        )
        assert resp.status_code == 403
