from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import RangeOperators
from django.db import models
from django.db.models import F, Q

from apps.businesses.models import Service, Staff
from apps.core.db import TsTzRange


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"

    # Statuses that occupy the staff member's time. A cancelled booking frees
    # its slot, so it is excluded from the overlap constraint below.
    ACTIVE_STATUSES = (Status.PENDING, Status.CONFIRMED, Status.COMPLETED)

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="bookings"
    )
    staff = models.ForeignKey(Staff, on_delete=models.PROTECT, related_name="bookings")
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="bookings")
    start = models.DateTimeField()
    end = models.DateTimeField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    # Unconfirmed bookings hold the slot only until this moment; a periodic
    # task releases expired holds (added in stage 3).
    expires_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_bookings",
    )
    cancellation_reason = models.TextField(blank=True)
    # Set when the corresponding email has been claimed for sending. They make
    # the notification tasks idempotent: a duplicate delivery finds the
    # timestamp already set and does nothing.
    confirmation_email_sent_at = models.DateTimeField(null=True, blank=True)
    cancellation_email_sent_at = models.DateTimeField(null=True, blank=True)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start"]
        indexes = [
            models.Index(fields=["staff", "start"], name="booking_staff_start_idx"),
            models.Index(fields=["customer", "-start"], name="booking_customer_start_idx"),
            # Keeps the 24h-reminder sweep cheap: only unreminded confirmed bookings.
            models.Index(
                fields=["start"],
                name="booking_reminder_due_idx",
                condition=Q(status="confirmed", reminder_sent_at__isnull=True),
            ),
            # Keep the lost-email sweep cheap: only bookings still owed an email.
            models.Index(
                fields=["updated_at"],
                name="booking_confirm_unsent_idx",
                condition=Q(status="confirmed", confirmation_email_sent_at__isnull=True),
            ),
            models.Index(
                fields=["updated_at"],
                name="booking_cancel_unsent_idx",
                condition=Q(status="cancelled", cancellation_email_sent_at__isnull=True),
            ),
            models.Index(
                fields=["expires_at"],
                name="booking_pending_expiry_idx",
                condition=Q(status="pending"),
            ),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(end__gt=F("start")), name="booking_end_after_start"),
            # The core guarantee: one staff member can never hold two active
            # bookings whose [start, end) ranges overlap. Enforced by PostgreSQL
            # with a GiST index, so it holds even under concurrent requests.
            ExclusionConstraint(
                name="booking_no_overlap_per_staff",
                expressions=[
                    (TsTzRange("start", "end"), RangeOperators.OVERLAPS),
                    ("staff", RangeOperators.EQUAL),
                ],
                condition=~Q(status="cancelled"),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.service.name} with {self.staff.display_name} at {self.start:%Y-%m-%d %H:%M}"
