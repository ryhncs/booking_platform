"""Free-slot computation (read-only).

A slot is *offered* here but only *guaranteed* by ``services.create_booking``:
another customer can still take it between this read and the write, in which
case the exclusion constraint turns the loser's request into ``SlotUnavailable``.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.businesses.models import Service, Staff, TimeOff

from .models import Booking

SLOT_STEP = timedelta(minutes=15)


def free_slots(*, staff: Staff, service: Service, day: date) -> list[tuple[datetime, datetime]]:
    """Return ``(start, end)`` pairs (aware, business-local) that are bookable on ``day``.

    ``day`` is a calendar date in the business's timezone. Slots start on
    ``SLOT_STEP`` boundaries within each of the staff member's shifts, must fit
    entirely inside the shift, and must not overlap an existing non-cancelled
    booking, time off, or the past.
    """
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

    now = timezone.now()
    slots: list[tuple[datetime, datetime]] = []
    for shift in shifts:
        shift_end = datetime.combine(day, shift.end_time, tzinfo=tz)
        start = datetime.combine(day, shift.start_time, tzinfo=tz)
        while start + duration <= shift_end:
            end = start + duration
            if start > now and not any(start < b_end and b_start < end for b_start, b_end in busy):
                slots.append((start, end))
            start += SLOT_STEP
    return sorted(slots)
