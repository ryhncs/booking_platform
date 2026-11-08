"""Load realistic demo data: ``python manage.py seed_demo``.

Safe to run repeatedly. The demo catalog is updated in place and the bookings
at demo businesses are replaced, so their dates are always relative to today.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings.models import Booking
from apps.bookings.services import (
    cancel_booking,
    confirm_booking,
    create_booking,
    expire_booking,
)
from apps.businesses.models import Business, Service, Staff, WorkingHours
from apps.businesses.services import create_weekly_shifts

DEMO_PASSWORD = "demo-pass-1234"
CUSTOMER_EMAIL = "customer@demo.com"
OWNER_EMAIL = "owner@demo.com"

TIMEZONE = "Asia/Tehran"
SAT_TO_WED = [5, 6, 0, 1, 2]
# Long enough that a seeded pending booking is still there when someone opens
# the app; a real hold lasts 10 minutes and beat would release it.
DEMO_HOLD = timedelta(hours=24)

CATALOG = [
    {
        "slug": "noor-hair-studio",
        "name": "Noor Hair Studio",
        "shifts": [(time(9), time(17))],
        "staff": ["Sara Ahmadi", "Leila Karimi", "Nima Rostami"],
        # name, minutes, price, indexes into "staff"
        "services": [
            ("Haircut", 45, "450000", [0, 1, 2]),
            ("Blow dry", 30, "250000", [0, 1]),
            ("Hair colour", 120, "1800000", [1]),
            ("Beard trim", 15, "150000", [2]),
        ],
    },
    {
        "slug": "sepid-dental-clinic",
        "name": "Sepid Dental Clinic",
        # Split day with a lunch break: two shifts per working day.
        "shifts": [(time(9), time(13)), (time(14), time(18))],
        "staff": ["Dr. Maryam Tehrani", "Dr. Reza Moradi"],
        "services": [
            ("Check-up", 30, "600000", [0, 1]),
            ("Scale and polish", 45, "1200000", [0, 1]),
            ("Filling", 60, "2500000", [0]),
            ("Root canal", 90, "7500000", [1]),
        ],
    },
    {
        "slug": "pars-car-service",
        "name": "Pars Car Service",
        "shifts": [(time(8), time(16))],
        "staff": ["Hamid Jafari", "Ali Sadeghi", "Omid Bagheri"],
        "services": [
            ("Oil change", 30, "900000", [0, 1, 2]),
            ("Brake inspection", 45, "700000", [0, 1]),
            ("Full service", 180, "4500000", [0]),
            ("Wheel alignment", 60, "1100000", [2]),
        ],
    },
]

# The same mix of bookings at every business:
# (state, staff index, service index, working day, hour, cancellation reason)
# Working day 0 is the next working day; negative days are in the past.
BOOKINGS = [
    ("confirmed", 0, 0, 0, 10, ""),
    ("pending", 1, 0, 0, 11, ""),
    ("cancelled_by_customer", 0, 1, 1, 10, "Something came up at work."),
    ("cancelled_by_owner", 1, 1, 1, 11, "Staff member is unwell, sorry."),
    ("hold_expired", 0, 0, 2, 10, ""),
    ("confirmed", 1, 1, 2, 11, ""),
    ("completed", 0, 0, -3, 10, ""),
    ("completed", 1, 1, -5, 11, ""),
]


def _working_days(today: date, step: int) -> Iterator[date]:
    """Sat-Wed dates after (step=1) or before (step=-1) ``today``, nearest first."""
    day = today
    while True:
        day += timedelta(days=step)
        if day.weekday() in SAT_TO_WED:
            yield day


def _demo_user(email: str, role: str) -> User:
    user = User.objects.filter(email=email).first() or User(username=email, email=email)
    user.role = role
    user.set_password(DEMO_PASSWORD)
    user.save()
    return user


class Command(BaseCommand):
    help = "Create or refresh demo businesses, staff, services, bookings and accounts."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "Refusing to run with DEBUG off: demo accounts use a public password."
            )
        with transaction.atomic():
            customer = _demo_user(CUSTOMER_EMAIL, User.Role.CUSTOMER)
            owner = _demo_user(OWNER_EMAIL, User.Role.OWNER)
            self._check_slugs_are_free(owner)
            for entry in CATALOG:
                self._seed_business(entry, owner, customer)
        self.stdout.write(
            self.style.SUCCESS(
                f"Demo data ready: {len(CATALOG)} businesses, "
                f"{len(CATALOG) * len(BOOKINGS)} bookings.\n"
                f"  customer: {CUSTOMER_EMAIL} / {DEMO_PASSWORD}\n"
                f"  owner:    {OWNER_EMAIL} / {DEMO_PASSWORD}"
            )
        )

    def _check_slugs_are_free(self, owner: User) -> None:
        slugs = [entry["slug"] for entry in CATALOG]
        taken = Business.objects.filter(slug__in=slugs).exclude(owner=owner)
        if taken.exists():
            names = ", ".join(taken.values_list("slug", flat=True))
            raise CommandError(f"These slugs belong to a non-demo owner: {names}")

    def _seed_business(self, entry: dict, owner: User, customer: User) -> None:
        business, _ = Business.objects.update_or_create(
            slug=entry["slug"],
            defaults={"owner": owner, "name": entry["name"], "timezone": TIMEZONE},
        )
        # Bookings first: they protect the staff and services they refer to.
        Booking.objects.filter(staff__business=business).delete()

        staff = [
            Staff.objects.update_or_create(
                business=business, display_name=name, defaults={"is_active": True}
            )[0]
            for name in entry["staff"]
        ]
        WorkingHours.objects.filter(staff__in=staff).delete()
        for member in staff:
            for start_time, end_time in entry["shifts"]:
                create_weekly_shifts(
                    staff=member, weekdays=SAT_TO_WED, start_time=start_time, end_time=end_time
                )

        services = []
        for name, minutes, price, offered_by in entry["services"]:
            service, _ = Service.objects.update_or_create(
                business=business,
                name=name,
                defaults={
                    "duration_minutes": minutes,
                    "price": Decimal(price),
                    "is_active": True,
                },
            )
            service.staff.set(staff[i] for i in offered_by)
            services.append(service)

        self._seed_bookings(business, staff, services, owner, customer)

    def _seed_bookings(self, business, staff, services, owner, customer) -> None:
        tz = ZoneInfo(TIMEZONE)
        today = timezone.now().astimezone(tz).date()
        ahead = _working_days(today, 1)
        behind = _working_days(today, -1)
        future = [next(ahead) for _ in range(3)]
        past = [next(behind) for _ in range(5)]

        for state, staff_i, service_i, day, hour, reason in BOOKINGS:
            when = future[day] if day >= 0 else past[-day - 1]
            start = datetime.combine(when, time(hour), tzinfo=tz)
            member, service = staff[staff_i], services[service_i]

            if state == "completed":
                # The one direct insert: create_booking rightly refuses a past
                # start, and nothing in the app creates history.
                Booking.objects.create(
                    customer=customer,
                    staff=member,
                    service=service,
                    start=start,
                    end=start + timedelta(minutes=service.duration_minutes),
                    status=Booking.Status.COMPLETED,
                )
                continue

            booking = create_booking(customer=customer, staff=member, service=service, start=start)
            if state == "confirmed":
                confirm_booking(booking)
            elif state == "cancelled_by_customer":
                cancel_booking(booking, cancelled_by=customer, reason=reason)
            elif state == "cancelled_by_owner":
                cancel_booking(booking, cancelled_by=owner, reason=reason)
            elif state == "hold_expired":
                Booking.objects.filter(pk=booking.pk).update(
                    expires_at=timezone.now() - timedelta(minutes=1)
                )
                expire_booking(booking.pk)

        self._finalise(business)

    def _finalise(self, business: Business) -> None:
        """Adjust fields that only matter for demo data (no signals needed)."""
        now = timezone.now()
        bookings = Booking.objects.filter(staff__business=business)
        bookings.filter(status=Booking.Status.PENDING).update(expires_at=now + DEMO_HOLD)
        # Claim the emails for what already "happened", so seeding sends none:
        # the tasks queued on commit find these set and do nothing. Pending
        # bookings stay unclaimed, so confirming one in a demo still emails.
        bookings.filter(status=Booking.Status.CONFIRMED).update(
            confirmation_email_sent_at=now, reminder_sent_at=now
        )
        bookings.filter(status=Booking.Status.CANCELLED).update(cancellation_email_sent_at=now)
