"""Schedule writes that need more than a single-row save.

No overlapping shifts is enforced by the ``working_hours_no_overlap``
exclusion constraint, not by locks or checks in Python: the checks here only
produce friendly error messages, the database is the guarantee.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import time

import psycopg
from django.db import IntegrityError, OperationalError, transaction

# bulk_create() does not send post_save, so the signal that normally clears
# cached availability (apps/bookings/signals.py) never fires for these rows.
from apps.bookings.availability import invalidate_staff_after_commit

from .models import Staff, WorkingHours

OVERLAP_CONSTRAINT = "working_hours_no_overlap"
DEADLOCK_RETRIES = 3


class ShiftConflict(Exception):
    """The database refused a shift because it overlaps another one."""


class ShiftOverlap(ShiftConflict):
    """Some requested days already have hours that overlap the new shift."""

    def __init__(self, weekdays: Iterable[int]):
        self.weekdays = sorted(weekdays)
        names = ", ".join(WorkingHours.Weekday(day).label for day in self.weekdays)
        super().__init__(f"Overlaps existing hours on {names}. Nothing was added.")


def save_shift[T](write: Callable[[], T]) -> T:
    """Run a shift insert/update so an overlap becomes ``ShiftConflict``.

    ``write`` runs in a savepoint, so a rejected write leaves any surrounding
    transaction usable. Like bookings (see apps/bookings/services.py), two
    transactions inserting conflicting ranges at the same moment can deadlock
    on the exclusion constraint instead of one getting a clean violation;
    nothing was written, so the write is retried, and the retry either
    succeeds or sees the committed rival and fails as an overlap.
    """
    for attempt in range(1, DEADLOCK_RETRIES + 1):
        try:
            with transaction.atomic():
                return write()
        except IntegrityError as exc:
            if OVERLAP_CONSTRAINT in str(exc):
                raise ShiftConflict() from exc
            raise
        except OperationalError as exc:
            if not isinstance(exc.__cause__, psycopg.errors.DeadlockDetected):
                raise
            if attempt == DEADLOCK_RETRIES:
                raise ShiftConflict() from exc
    raise AssertionError("unreachable")  # pragma: no cover


def _clashing_days(staff: Staff, days: list[int], start_time: time, end_time: time) -> set[int]:
    return set(
        WorkingHours.objects.filter(
            staff=staff,
            weekday__in=days,
            start_time__lt=end_time,
            end_time__gt=start_time,
        ).values_list("weekday", flat=True)
    )


def create_weekly_shifts(
    *, staff: Staff, weekdays: Iterable[int], start_time: time, end_time: time
) -> list[WorkingHours]:
    """Give ``staff`` the same shift on several weekdays: all of them or none.

    Raises ``ShiftOverlap`` (naming every clashing day) if any day already has
    hours overlapping ``[start_time, end_time)``; in that case nothing is saved.
    """
    days = sorted(set(weekdays))

    # Fast, friendly path: name the clashing days before trying anything.
    clashing = _clashing_days(staff, days, start_time, end_time)
    if clashing:
        raise ShiftOverlap(clashing)

    def insert_all() -> list[WorkingHours]:
        shifts = WorkingHours.objects.bulk_create(
            WorkingHours(staff=staff, weekday=day, start_time=start_time, end_time=end_time)
            for day in days
        )
        # Inside the savepoint: if the insert is rolled back, so is this.
        invalidate_staff_after_commit(staff.pk)
        return shifts

    try:
        return save_shift(insert_all)
    except ShiftConflict:
        # Another request added overlapping hours between our check and our
        # insert. The constraint rejected the whole batch; look again to say
        # which days collide now (the rival has committed by this point).
        raise ShiftOverlap(_clashing_days(staff, days, start_time, end_time) or days) from None
