"""Schedule writes that need more than a single-row save."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import time

from django.db import transaction

# bulk_create() does not send post_save, so the signal that normally clears
# cached availability (apps/bookings/signals.py) never fires for these rows.
from apps.bookings.availability import invalidate_staff_after_commit

from .models import Staff, WorkingHours


class ShiftOverlap(Exception):
    """Some requested days already have hours that overlap the new shift."""

    def __init__(self, weekdays: Iterable[int]):
        self.weekdays = sorted(weekdays)
        names = ", ".join(WorkingHours.Weekday(day).label for day in self.weekdays)
        super().__init__(f"Overlaps existing hours on {names}. Nothing was added.")


def create_weekly_shifts(
    *, staff: Staff, weekdays: Iterable[int], start_time: time, end_time: time
) -> list[WorkingHours]:
    """Give ``staff`` the same shift on several weekdays: all of them or none.

    Raises ``ShiftOverlap`` (naming every clashing day) if any day already has
    hours overlapping ``[start_time, end_time)``; in that case nothing is saved.
    """
    days = sorted(set(weekdays))
    with transaction.atomic():
        # Lock the staff row so two bulk requests for the same person run one
        # after the other; otherwise both could pass the overlap check below
        # and together create overlapping shifts.
        Staff.objects.select_for_update().get(pk=staff.pk)

        clashing = set(
            WorkingHours.objects.filter(
                staff=staff,
                weekday__in=days,
                start_time__lt=end_time,
                end_time__gt=start_time,
            ).values_list("weekday", flat=True)
        )
        if clashing:
            raise ShiftOverlap(clashing)

        shifts = WorkingHours.objects.bulk_create(
            WorkingHours(staff=staff, weekday=day, start_time=start_time, end_time=end_time)
            for day in days
        )
        invalidate_staff_after_commit(staff.pk)
    return shifts
