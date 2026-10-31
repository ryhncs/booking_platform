from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.businesses.models import Business, Service, Staff, WorkingHours

TEHRAN = ZoneInfo("Asia/Tehran")


def next_monday_at(hour: int, minute: int = 0) -> datetime:
    """A timezone-aware datetime on the next Monday (business local time)."""
    today = timezone.now().astimezone(TEHRAN).date()
    days_ahead = (0 - today.weekday()) % 7 or 7
    day = today + timedelta(days=days_ahead)
    return datetime.combine(day, time(hour, minute), tzinfo=TEHRAN)


@pytest.fixture
def owner(db):
    return User.objects.create_user("owner", "owner@example.com", "pw", role=User.Role.OWNER)


@pytest.fixture
def customer(db):
    return User.objects.create_user("cust", "cust@example.com", "pw")


@pytest.fixture
def make_customer(db):
    counter = iter(range(1000))

    def _make():
        n = next(counter)
        return User.objects.create_user(f"c{n}", f"c{n}@example.com", "pw")

    return _make


@pytest.fixture
def business(owner):
    return Business.objects.create(owner=owner, name="Salon", slug="salon", timezone="Asia/Tehran")


@pytest.fixture
def staff(business):
    s = Staff.objects.create(business=business, display_name="Sara")
    WorkingHours.objects.create(staff=s, weekday=0, start_time=time(9), end_time=time(17))
    return s


@pytest.fixture
def service(business, staff):
    svc = Service.objects.create(
        business=business, name="Haircut", duration_minutes=60, price=Decimal("250000")
    )
    svc.staff.add(staff)
    return svc


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_client():
    """Factory: an APIClient authenticated as the given user."""

    def _make(user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    return _make
