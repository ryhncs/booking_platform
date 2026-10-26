from django.contrib.postgres.fields import DateTimeRangeField
from django.db.models import Func


class TsTzRange(Func):
    """SQL ``tstzrange(start, end)`` — a half-open ``[start, end)`` range.

    Half-open means a booking ending at 10:00 and one starting at 10:00 do
    not overlap, which is exactly the behaviour back-to-back slots need.
    """

    function = "TSTZRANGE"
    output_field = DateTimeRangeField()
