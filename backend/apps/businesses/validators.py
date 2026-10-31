from functools import lru_cache
from zoneinfo import available_timezones

from django.core.exceptions import ValidationError


@lru_cache(maxsize=1)
def iana_timezones() -> frozenset[str]:
    # Scanning tzdata on disk is slow, so do it once per process.
    return frozenset(available_timezones())


def validate_iana_timezone(value: str) -> None:
    if value not in iana_timezones():
        raise ValidationError(
            "%(value)s is not a valid IANA timezone name (e.g. 'Asia/Tehran').",
            code="invalid_timezone",
            params={"value": value},
        )
