from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.bookings.models import Booking
from apps.bookings.services import create_booking

from .conftest import next_monday_at

pytestmark = pytest.mark.django_db

LIST = "booking-list"


def detail(pk):
    return reverse("booking-detail", args=[pk])


def action(name, pk):
    return reverse(f"booking-{name}", args=[pk])


@pytest.fixture
def client(customer, auth_client):
    return auth_client(customer)


@pytest.fixture
def owner_client(owner, auth_client):
    return auth_client(owner)


@pytest.fixture
def booking(customer, staff, service):
    return create_booking(customer=customer, staff=staff, service=service, start=next_monday_at(10))


def payload(staff, service, start=None, **extra):
    start = start or next_monday_at(10)
    return {"staff": staff.pk, "service": service.pk, "start": start.isoformat(), **extra}


class TestCreate:
    def test_creates_pending_booking_for_the_caller(self, client, customer, staff, service):
        resp = client.post(
            reverse(LIST), payload(staff, service, notes="window seat", customer=999), format="json"
        )
        assert resp.status_code == 201
        assert resp.data["status"] == "pending"
        assert resp.data["customer"] == customer.pk
        assert resp.data["notes"] == "window seat"
        assert resp.data["staff_name"] == "Sara"
        assert resp.data["service_name"] == "Haircut"
        booking = Booking.objects.get()
        assert booking.end - booking.start == timedelta(minutes=60)

    def test_requires_authentication(self, api_client, staff, service):
        resp = api_client.post(reverse(LIST), payload(staff, service), format="json")
        assert resp.status_code == 401

    def test_slot_taken_is_409(self, client, booking, staff, service, make_customer, auth_client):
        rival = auth_client(make_customer())
        resp = rival.post(reverse(LIST), payload(staff, service), format="json")
        assert resp.status_code == 409
        assert resp.data["code"] == "slot_unavailable"
        assert Booking.objects.count() == 1

    def test_overlapping_start_is_409(self, client, booking, staff, service):
        start = next_monday_at(10, 30)
        resp = client.post(reverse(LIST), payload(staff, service, start), format="json")
        assert resp.status_code == 409

    def test_cancelled_slot_can_be_rebooked(self, client, booking, staff, service):
        assert client.post(action("cancel", booking.pk)).status_code == 200
        resp = client.post(reverse(LIST), payload(staff, service), format="json")
        assert resp.status_code == 201

    def test_outside_working_hours_is_400(self, client, staff, service):
        resp = client.post(
            reverse(LIST), payload(staff, service, next_monday_at(20)), format="json"
        )
        assert resp.status_code == 400
        assert resp.data["code"] == "outside_working_hours"

    def test_past_start_is_400(self, client, staff, service):
        past = timezone.now() - timedelta(days=1)
        resp = client.post(reverse(LIST), payload(staff, service, past), format="json")
        assert resp.status_code == 400
        assert resp.data["code"] == "invalid_request"

    def test_start_without_utc_offset_is_400(self, client, staff, service):
        body = payload(staff, service)
        body["start"] = next_monday_at(10).replace(tzinfo=None).isoformat()
        resp = client.post(reverse(LIST), body, format="json")
        assert resp.status_code == 400
        assert "start" in resp.data

    def test_staff_not_offering_service_is_400(self, client, staff, service, other_staff):
        resp = client.post(reverse(LIST), payload(other_staff, service), format="json")
        assert resp.status_code == 400
        assert resp.data["code"] == "invalid_request"

    def test_inactive_service_is_400(self, client, staff, service):
        service.is_active = False
        service.save()
        resp = client.post(reverse(LIST), payload(staff, service), format="json")
        assert resp.status_code == 400

    def test_unknown_staff_is_400(self, client, staff, service):
        body = payload(staff, service)
        body["staff"] = staff.pk + 999
        assert client.post(reverse(LIST), body, format="json").status_code == 400


class TestList:
    def test_customer_sees_only_own_bookings(self, client, booking, make_customer, auth_client):
        stranger = auth_client(make_customer())
        assert client.get(reverse(LIST)).data["count"] == 1
        assert stranger.get(reverse(LIST)).data["count"] == 0

    def test_business_owner_sees_bookings_at_their_business(self, booking, owner_client):
        resp = owner_client.get(reverse(LIST))
        assert [b["id"] for b in resp.data["results"]] == [booking.pk]

    def test_other_owner_sees_nothing(self, booking, other_owner, auth_client):
        assert auth_client(other_owner).get(reverse(LIST)).data["count"] == 0

    def test_status_filter(self, client, booking):
        assert client.get(reverse(LIST), {"status": "pending"}).data["count"] == 1
        assert client.get(reverse(LIST), {"status": "confirmed"}).data["count"] == 0

    def test_invalid_status_filter_is_400(self, client):
        assert client.get(reverse(LIST), {"status": "bogus"}).status_code == 400

    def test_retrieve_own_and_hidden_from_strangers(
        self, client, booking, make_customer, auth_client, other_owner
    ):
        assert client.get(detail(booking.pk)).status_code == 200
        assert auth_client(make_customer()).get(detail(booking.pk)).status_code == 404
        assert auth_client(other_owner).get(detail(booking.pk)).status_code == 404


class TestConfirm:
    def test_customer_confirms(self, client, booking):
        resp = client.post(action("confirm", booking.pk))
        assert resp.status_code == 200
        assert resp.data["status"] == "confirmed"
        assert resp.data["expires_at"] is None

    def test_business_owner_confirms(self, owner_client, booking):
        assert owner_client.post(action("confirm", booking.pk)).status_code == 200

    def test_stranger_cannot_confirm(self, booking, make_customer, auth_client):
        resp = auth_client(make_customer()).post(action("confirm", booking.pk))
        assert resp.status_code == 404
        booking.refresh_from_db()
        assert booking.status == Booking.Status.PENDING

    def test_other_owner_cannot_confirm(self, booking, other_owner, auth_client):
        assert auth_client(other_owner).post(action("confirm", booking.pk)).status_code == 404
        booking.refresh_from_db()
        assert booking.status == Booking.Status.PENDING

    def test_expired_hold_cannot_be_confirmed(self, client, booking):
        Booking.objects.filter(pk=booking.pk).update(expires_at=timezone.now() - timedelta(1))
        resp = client.post(action("confirm", booking.pk))
        assert resp.status_code == 400
        assert resp.data["code"] == "invalid_request"

    def test_cancelled_booking_cannot_be_confirmed(self, client, booking):
        client.post(action("cancel", booking.pk))
        assert client.post(action("confirm", booking.pk)).status_code == 400

    def test_requires_authentication(self, api_client, booking):
        assert api_client.post(action("confirm", booking.pk)).status_code == 401


class TestCancel:
    def test_customer_cancels(self, client, customer, booking):
        resp = client.post(action("cancel", booking.pk), {"reason": "Sick"}, format="json")
        assert resp.status_code == 200
        assert resp.data["status"] == "cancelled"
        assert resp.data["cancelled_by"] == customer.pk
        assert resp.data["cancellation_reason"] == "Sick"
        booking.refresh_from_db()
        assert booking.cancelled_by == customer
        assert booking.cancellation_reason == "Sick"

    def test_owner_cancel_records_the_owner_not_the_customer(self, owner, owner_client, booking):
        resp = owner_client.post(
            action("cancel", booking.pk), {"reason": "Staff out sick"}, format="json"
        )
        assert resp.status_code == 200
        assert resp.data["cancelled_by"] == owner.pk
        assert resp.data["cancelled_by"] != booking.customer_id
        assert resp.data["cancellation_reason"] == "Staff out sick"

    def test_reason_is_optional(self, client, customer, booking):
        resp = client.post(action("cancel", booking.pk))
        assert resp.status_code == 200
        assert resp.data["cancellation_reason"] == ""
        assert resp.data["cancelled_by"] == customer.pk

    def test_overlong_reason_is_400(self, client, booking):
        resp = client.post(action("cancel", booking.pk), {"reason": "x" * 1001}, format="json")
        assert resp.status_code == 400
        booking.refresh_from_db()
        assert booking.status == Booking.Status.PENDING

    def test_uncancelled_booking_has_no_cancellation_data(self, client, booking):
        data = client.get(detail(booking.pk)).data
        assert data["cancelled_by"] is None
        assert data["cancellation_reason"] == ""

    def test_cancelling_a_confirmed_booking(self, client, booking):
        client.post(action("confirm", booking.pk))
        assert client.post(action("cancel", booking.pk)).data["status"] == "cancelled"

    def test_business_owner_cancels(self, owner_client, booking):
        assert owner_client.post(action("cancel", booking.pk)).status_code == 200

    def test_stranger_cannot_cancel(self, booking, make_customer, auth_client):
        assert auth_client(make_customer()).post(action("cancel", booking.pk)).status_code == 404
        booking.refresh_from_db()
        assert booking.status == Booking.Status.PENDING

    def test_other_owner_cannot_cancel(self, booking, other_owner, auth_client):
        assert auth_client(other_owner).post(action("cancel", booking.pk)).status_code == 404

    def test_cancelling_twice_is_400(self, client, booking):
        client.post(action("cancel", booking.pk))
        assert client.post(action("cancel", booking.pk)).status_code == 400


def test_bookings_cannot_be_edited_or_deleted_via_the_api(client, booking):
    resp = client.patch(detail(booking.pk), {"status": "confirmed"}, format="json")
    assert resp.status_code == 405
    assert client.delete(detail(booking.pk)).status_code == 405
