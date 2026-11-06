from django.contrib.postgres.fields import DateTimeRangeField
from django.db.models import Func


class TsTzRange(Func):
    """SQL ``tstzrange(start, end)`` — a half-open ``[start, end)`` range.

    Half-open means a booking ending at 10:00 and one starting at 10:00 do
    not overlap, which is exactly the behaviour back-to-back slots need.
    """

    function = "TSTZRANGE"
    output_field = DateTimeRangeField()


class TimeRange(Func):
    """A half-open ``[start, end)`` range of two time-of-day columns.

    PostgreSQL has no range type for ``time``, so both times are placed on the
    same fixed (arbitrary) date and compared as a ``tsrange``::

        tsrange(DATE '2000-01-01' + start_time, DATE '2000-01-01' + end_time, '[)')

    The expression is immutable, so it can back a GiST exclusion constraint.
    Half-open again: a 09:00-12:00 shift and a 12:00-17:00 shift don't overlap.
    (``output_field`` only tells Django it's a range; it's never cast to tstzrange.)
    """

    function = "TSRANGE"
    template = "%(function)s(DATE '2000-01-01' + %(expressions)s, '[)')"
    arg_joiner = ", DATE '2000-01-01' + "
    output_field = DateTimeRangeField()
