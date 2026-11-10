"""Measure GET /api/availability/ latency, cold vs cached, over real HTTP.

See docs/BENCHMARKS.md for how to run it. Requests go out in pairs: bump the
staff member's cache version, request (cold: computes and fills the cache),
request again (cached). Pairing means slow drift on the machine affects both
sides equally. Only the HTTP call is timed.
"""

from __future__ import annotations

import json
import statistics
import time
import urllib.request
from datetime import date, timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import User
from apps.bookings import availability
from apps.bookings.management.commands.seed_demo import CUSTOMER_EMAIL, SAT_TO_WED, TIMEZONE
from apps.businesses.models import Service, Staff

WARMUP_PAIRS = 50


def _next_working_day() -> date:
    day = timezone.now().astimezone(ZoneInfo(TIMEZONE)).date() + timedelta(days=1)
    while day.weekday() not in SAT_TO_WED:
        day += timedelta(days=1)
    return day


def _summary(label: str, samples: list[float]) -> str:
    cuts = statistics.quantiles(samples, n=100, method="inclusive")
    return (
        f"{label:<8}{len(samples):>7}{cuts[49]:>10.2f}{cuts[94]:>10.2f}"
        f"{cuts[98]:>10.2f}{statistics.fmean(samples):>10.2f}"
    )


class Command(BaseCommand):
    help = "Measure availability endpoint latency, cold vs cached (needs seed_demo data)."

    def add_arguments(self, parser):
        parser.add_argument("--url", default="http://127.0.0.1:8000", help="Server to measure.")
        parser.add_argument(
            "--requests", type=int, default=1000, help="Measured cold/cached pairs."
        )

    def handle(self, *args, **options):
        try:
            customer = User.objects.get(email=CUSTOMER_EMAIL)
            staff = Staff.objects.get(display_name="Sara Ahmadi")
            service = Service.objects.get(name="Haircut", business=staff.business)
        except (User.DoesNotExist, Staff.DoesNotExist, Service.DoesNotExist) as exc:
            raise CommandError("Demo data not found: run `manage.py seed_demo` first.") from exc

        day = _next_working_day()
        query = urlencode({"staff": staff.pk, "service": service.pk, "date": day.isoformat()})
        request = urllib.request.Request(
            f"{options['url']}/api/availability/?{query}",
            headers={"Authorization": f"Bearer {AccessToken.for_user(customer)}"},
        )

        def timed_get() -> tuple[float, dict]:
            started = time.perf_counter()
            with urllib.request.urlopen(request) as response:
                body = response.read()
            elapsed_ms = (time.perf_counter() - started) * 1000
            return elapsed_ms, json.loads(body)

        def pair() -> tuple[float, float, dict]:
            availability.invalidate_staff(staff.pk)
            cold, body = timed_get()
            cached, cached_body = timed_get()
            if cached_body != body:
                raise CommandError("Cold and cached responses differ.")
            return cold, cached, body

        for _ in range(WARMUP_PAIRS):  # let the server warm up; not measured
            _, _, body = pair()
        if not body["slots"]:
            raise CommandError(f"No free slots on {day}: the measurement would be meaningless.")
        # Make sure "cached" really means cached: the server must have filled
        # the same Redis this process is looking at.
        key = availability._slots_key(
            staff.pk, availability.cache_version(staff.pk), service.pk, day
        )
        if cache.get(key) is None:
            raise CommandError("The server did not fill the cache this command can see.")

        colds, cacheds = [], []
        for _ in range(options["requests"]):
            cold, cached, _ = pair()
            colds.append(cold)
            cacheds.append(cached)

        self.stdout.write(f"{options['url']}  {day}  {len(body['slots'])} slots")
        self.stdout.write(
            f"{'mode':<8}{'n':>7}{'p50 ms':>10}{'p95 ms':>10}{'p99 ms':>10}{'mean ms':>10}"
        )
        self.stdout.write(_summary("cold", colds))
        self.stdout.write(_summary("cached", cacheds))
