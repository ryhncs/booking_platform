"""Free-slot computation (read-only).

A slot is *offered* here but only *guaranteed* by ``services.create_booking``:
another customer can still take it between this read and the write, in which
case the exclusion constraint turns the loser's request into ``SlotUnavailable``.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.businesses.models import Service, Staff, TimeOff

from .models import Booking

SLOT_STEP = timedelta(minutes=15)

# Slots are cached per staff + service + date. Every key embeds the staff
# member's *version token*, so invalidating a staff member is one write that
# orphans all their keys (any service, any date) with no key scanning. The
# orphans simply expire after CACHE_TTL. The TTL is also the upper bound on
# staleness if Redis misses an invalidation (e.g. an outage during the write).
CACHE_TTL = 5 * 60


def _version_key(staff_id: int) -> str:
    return f"availability:version:{staff_id}"


def _slots_key(staff_id: int, version: str, service_id: int, day: date) -> str:
    return f"availability:{staff_id}:{version}:{service_id}:{day.isoformat()}"


def cache_version(staff_id: int) -> str:
    return cache.get(_version_key(staff_id)) or "0"


def invalidate_staff(staff_id: int) -> None:
    cache.set(_version_key(staff_id), uuid.uuid4().hex, timeout=None)


def invalidate_staff_after_commit(staff_id: int) -> None:
    """Drop cached availability once the surrounding transaction has committed.

    Invalidating *before* commit would let a concurrent reader recompute from
    the old rows and cache them under the new version; after commit, anything
    that reads the new version also sees the new rows. If the transaction rolls
    back, nothing is invalidated (nothing changed).
    """
    transaction.on_commit(lambda: invalidate_staff(staff_id))


def free_slots(*, staff: Staff, service: Service, day: date) -> list[tuple[datetime, datetime]]:
    """Return ``(start, end)`` pairs (aware, business-local) that are bookable on ``day``.

    ``day`` is a calendar date in the business's timezone. Slots start on
    ``SLOT_STEP`` boundaries within each of the staff member's shifts, must fit
    entirely inside the shift, and must not overlap an existing non-cancelled
    booking, time off, or the past.

    The expensive part is cached; "not in the past" is applied on every read so
    the passage of time can never make a cached entry stale.
    """
    key = _slots_key(staff.pk, cache_version(staff.pk), service.pk, day)
    slots = cache.get(key)
    if slots is None:
        slots = _compute_slots(staff=staff, service=service, day=day)
        cache.set(key, slots, timeout=CACHE_TTL)
    now = timezone.now()
    return [(start, end) for start, end in slots if start > now]


def _compute_slots(*, staff: Staff, service: Service, day: date) -> list[tuple[datetime, datetime]]:
    tz = ZoneInfo(staff.business.timezone)
    duration = timedelta(minutes=service.duration_minutes)

    shifts = list(staff.working_hours.filter(weekday=day.weekday()))
    if not shifts:
        return []

    day_start = datetime.combine(day, datetime.min.time(), tzinfo=tz)
    day_end = day_start + timedelta(days=1)

    # Same predicate as the DB constraint (anything not cancelled holds the
    # slot), so a slot listed as free is never rejected for that reason alone.
    busy = [
        (b.start, b.end)
        for b in Booking.objects.filter(staff=staff, start__lt=day_end, end__gt=day_start)
        .exclude(status=Booking.Status.CANCELLED)
        .only("start", "end")
    ]
    busy += list(
        TimeOff.objects.filter(staff=staff, start__lt=day_end, end__gt=day_start).values_list(
            "start", "end"
        )
    )

    slots: list[tuple[datetime, datetime]] = []
    for shift in shifts:
        shift_end = datetime.combine(day, shift.end_time, tzinfo=tz)
        start = datetime.combine(day, shift.start_time, tzinfo=tz)
        while start + duration <= shift_end:
            end = start + duration
            if not any(start < b_end and b_start < end for b_start, b_end in busy):
                slots.append((start, end))
            start += SLOT_STEP
    return sorted(slots)
