from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import RangeOperators
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q

from apps.core.db import TsTzRange

from .validators import validate_iana_timezone


class Business(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="businesses"
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    # IANA name, e.g. "Asia/Tehran". Working hours are interpreted in this zone;
    # every timestamp in the database is stored in UTC.
    timezone = models.CharField(max_length=64, default="UTC", validators=[validate_iana_timezone])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "businesses"

    def __str__(self) -> str:
        return self.name


class Staff(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="staff")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_profiles",
    )
    display_name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "staff"

    def __str__(self) -> str:
        return f"{self.display_name} @ {self.business}"


class Service(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="services")
    name = models.CharField(max_length=120)
    duration_minutes = models.PositiveIntegerField(
        validators=[MinValueValidator(5), MaxValueValidator(8 * 60)]
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    staff = models.ManyToManyField(Staff, related_name="services", blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(duration_minutes__gte=5), name="service_min_duration"
            ),
            models.CheckConstraint(condition=Q(price__gte=0), name="service_price_non_negative"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.duration_minutes} min)"


class WorkingHours(models.Model):
    """A weekly recurring shift, in the business's local time."""

    class Weekday(models.IntegerChoices):
        MONDAY = 0
        TUESDAY = 1
        WEDNESDAY = 2
        THURSDAY = 3
        FRIDAY = 4
        SATURDAY = 5
        SUNDAY = 6

    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name="working_hours")
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ["weekday", "start_time"]
        verbose_name_plural = "working hours"
        constraints = [
            models.CheckConstraint(
                condition=Q(end_time__gt=F("start_time")), name="working_hours_end_after_start"
            ),
            models.UniqueConstraint(
                fields=["staff", "weekday", "start_time"], name="working_hours_unique_shift"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.staff} {self.get_weekday_display()} {self.start_time}-{self.end_time}"


class TimeOff(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name="time_off")
    start = models.DateTimeField()
    end = models.DateTimeField()
    reason = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name_plural = "time off"
        constraints = [
            models.CheckConstraint(
                condition=Q(end__gt=F("start")), name="time_off_end_after_start"
            ),
            ExclusionConstraint(
                name="time_off_no_overlap",
                expressions=[
                    (TsTzRange("start", "end"), RangeOperators.OVERLAPS),
                    ("staff", RangeOperators.EQUAL),
                ],
            ),
        ]

    def __str__(self) -> str:
        return f"{self.staff} off {self.start:%Y-%m-%d %H:%M}–{self.end:%H:%M}"
