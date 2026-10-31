"""Celery tasks: booking emails and periodic housekeeping.

Every email task is idempotent. It *claims* the send with one atomic
``UPDATE ... WHERE <sent_at> IS NULL``; only the worker whose update changes a
row sends. A redelivered message, a duplicate enqueue or two workers racing all
find the timestamp set and do nothing. If sending fails, the claim is released
so the retry can try again. (A worker killed between the claim and the send
loses that one email rather than duplicating it.)
"""

import logging
from collections.abc import Callable
from datetime import timedelta

from celery import shared_task
from django.core.mail import EmailMessage
from django.utils import timezone

from . import emails, services
from .models import Booking

logger = logging.getLogger(__name__)

REMINDER_WINDOW = timedelta(hours=24)
SWEEP_BATCH = 500

email_task = shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_kwargs={"max_retries": 3},
)


def _send_once(
    booking_id: int,
    sent_field: str,
    build: Callable[[Booking], EmailMessage],
    is_applicable: Callable[[Booking], bool],
) -> str:
    booking = (
        Booking.objects.select_related(
            "customer", "cancelled_by", "service", "staff__business__owner"
        )
        .filter(pk=booking_id)
        .first()
    )
    if booking is None:
        return "missing"
    if not is_applicable(booking):
        return "skipped"

    claimed = Booking.objects.filter(pk=booking_id, **{f"{sent_field}__isnull": True}).update(
        **{sent_field: timezone.now()}
    )
    if not claimed:
        return "duplicate"
    try:
        build(booking).send(fail_silently=False)
    except Exception:
        Booking.objects.filter(pk=booking_id).update(**{sent_field: None})  # let the retry send
        raise
    return "sent"


@email_task
def send_confirmation_email(self, booking_id: int) -> str:
    return _send_once(
        booking_id,
        "confirmation_email_sent_at",
        emails.confirmation_email,
        lambda b: b.status == Booking.Status.CONFIRMED,
    )


@email_task
def send_cancellation_email(self, booking_id: int) -> str:
    return _send_once(
        booking_id,
        "cancellation_email_sent_at",
        emails.cancellation_email,
        lambda b: b.status == Booking.Status.CANCELLED,
    )


@email_task
def send_reminder_email(self, booking_id: int) -> str:
    return _send_once(
        booking_id,
        "reminder_sent_at",
        emails.reminder_email,
        lambda b: b.status == Booking.Status.CONFIRMED and b.start > timezone.now(),
    )


@shared_task
def send_due_reminders() -> int:
    """Queue a reminder for every confirmed booking starting within 24 hours."""
    now = timezone.now()
    due = list(
        Booking.objects.filter(
            status=Booking.Status.CONFIRMED,
            reminder_sent_at__isnull=True,
            start__gt=now,
            start__lte=now + REMINDER_WINDOW,
        ).values_list("pk", flat=True)[:SWEEP_BATCH]
    )
    for booking_id in due:
        send_reminder_email.delay(booking_id)
    return len(due)


@shared_task
def release_expired_holds() -> int:
    """Cancel pending bookings whose hold has lapsed, freeing their slots."""
    expired = list(
        Booking.objects.filter(
            status=Booking.Status.PENDING, expires_at__lte=timezone.now()
        ).values_list("pk", flat=True)[:SWEEP_BATCH]
    )
    released = sum(services.expire_booking(booking_id) for booking_id in expired)
    if released:
        logger.info("Released %d expired booking hold(s)", released)
    return released
