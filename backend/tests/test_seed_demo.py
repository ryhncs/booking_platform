"""The seed_demo management command.

Real commits (transaction=True) so that the tasks queued on commit actually
run (eagerly) and the "seeding sends no email" test means something.
"""

import io
from collections import Counter
from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings.management.commands.seed_demo import (
    CUSTOMER_EMAIL,
    DEMO_PASSWORD,
    OWNER_EMAIL,
    SAT_TO_WED,
)
from apps.bookings.models import Booking
from apps.bookings.services import confirm_booking, create_booking
from apps.businesses.models import Business, Service, Staff, WorkingHours

from .conftest import next_monday_at

pytestmark = pytest.mark.django_db(transaction=True)

DEMO_SLUGS = {"noor-hair-studio", "sepid-dental-clinic", "pars-car-service"}


@pytest.fixture(autouse=True)
def _debug_on(settings):
    settings.DEBUG = True  # the test runner forces it off; the command requires it


def seed():
    call_command("seed_demo", stdout=io.StringIO())


def snapshot():
    return {
        "users": User.objects.count(),
        "businesses": Business.objects.count(),
        "staff": Staff.objects.count(),
        "services": Service.objects.count(),
        "hours": WorkingHours.objects.count(),
        "bookings": Booking.objects.count(),
        "states": Counter(Booking.objects.values_list("status", flat=True)),
    }


def test_creates_the_three_demo_businesses_with_every_booking_state():
    seed()

    assert set(Business.objects.values_list("slug", flat=True)) == DEMO_SLUGS
    assert Counter(Booking.objects.values_list("status", flat=True)) == {
        Booking.Status.CONFIRMED: 6,
        Booking.Status.PENDING: 3,
        Booking.Status.CANCELLED: 9,
        Booking.Status.COMPLETED: 6,
    }


def test_is_idempotent():
    seed()
    first = snapshot()
    seed()
    assert snapshot() == first


def test_staff_work_saturday_to_wednesday_only():
    seed()
    assert set(WorkingHours.objects.values_list("weekday", flat=True)) == set(SAT_TO_WED)
    # The clinic's split day is two shifts on each working day.
    dentist = Staff.objects.get(display_name="Dr. Reza Moradi")
    assert dentist.working_hours.count() == 2 * len(SAT_TO_WED)


def test_cancellations_record_who_and_why():
    seed()
    cancelled = Booking.objects.filter(status=Booking.Status.CANCELLED)
    owner = User.objects.get(email=OWNER_EMAIL)
    customer = User.objects.get(email=CUSTOMER_EMAIL)
    assert cancelled.filter(cancelled_by=customer).count() == 3
    assert cancelled.filter(cancelled_by=owner).count() == 3
    assert cancelled.filter(cancelled_by=None).count() == 3  # expired holds
    assert not cancelled.filter(cancellation_reason="").exists()


def test_dates_are_on_the_right_side_of_today():
    seed()
    now = timezone.now()
    done = Booking.objects.filter(status=Booking.Status.COMPLETED)
    assert not done.filter(start__gte=now).exists()
    assert (
        not Booking.objects.exclude(status=Booking.Status.COMPLETED).filter(start__lte=now).exists()
    )


def test_pending_bookings_outlast_the_ten_minute_hold():
    seed()
    soonest = timezone.now() + timedelta(hours=23)
    pending = Booking.objects.filter(status=Booking.Status.PENDING)
    assert pending.count() == 3
    assert not pending.filter(expires_at__lt=soonest).exists()


def test_seeding_sends_no_email_but_confirming_a_pending_booking_does():
    seed()
    assert mail.outbox == []

    confirm_booking(Booking.objects.filter(status=Booking.Status.PENDING).first())
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [CUSTOMER_EMAIL]


@pytest.mark.parametrize(("email", "role"), [(CUSTOMER_EMAIL, "customer"), (OWNER_EMAIL, "owner")])
def test_demo_accounts_can_log_in(api_client, email, role):
    seed()
    tokens = api_client.post(
        reverse("auth-login"), {"email": email, "password": DEMO_PASSWORD}, format="json"
    )
    assert tokens.status_code == 200
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens.data['access']}")
    assert api_client.get(reverse("me")).data["role"] == role


def test_seeded_data_is_bookable_through_the_api(auth_client):
    seed()
    customer = User.objects.get(email=CUSTOMER_EMAIL)
    client = auth_client(customer)
    staff = Staff.objects.get(display_name="Sara Ahmadi")
    service = Service.objects.get(name="Haircut")
    day = timezone.now().astimezone(ZoneInfo("Asia/Tehran")).date() + timedelta(days=1)
    while day.weekday() not in SAT_TO_WED:
        day += timedelta(days=1)

    slots = client.get(
        reverse("availability"), {"staff": staff.pk, "service": service.pk, "date": day}
    ).data["slots"]

    assert slots
    assert slots[0]["start"][11:16] == "09:00"
    # Sara's seeded confirmed 10:00 Haircut (45 min) is not offered again.
    assert "10:00" not in [s["start"][11:16] for s in slots]


def test_leaves_other_businesses_alone(business, staff, service, customer):
    mine = create_booking(customer=customer, staff=staff, service=service, start=next_monday_at(10))
    seed()
    seed()
    assert Booking.objects.filter(pk=mine.pk).exists()
    assert Business.objects.get(pk=business.pk).name == "Salon"


def test_refuses_to_run_with_debug_off(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError, match="DEBUG"):
        seed()
    assert not User.objects.filter(email=OWNER_EMAIL).exists()


def test_refuses_to_take_over_a_slug_owned_by_someone_else(owner):
    Business.objects.create(owner=owner, name="Real", slug="noor-hair-studio")
    with pytest.raises(CommandError, match="noor-hair-studio"):
        seed()
    assert Business.objects.get(slug="noor-hair-studio").name == "Real"
    assert not User.objects.filter(email=OWNER_EMAIL).exists()  # rolled back
