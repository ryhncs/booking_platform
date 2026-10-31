"""Builds the emails sent about bookings. Pure functions: no sending, no writes."""

from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.mail import EmailMessage

from .models import Booking


def _local(booking: Booking, moment) -> str:
    tz = ZoneInfo(booking.staff.business.timezone)
    return moment.astimezone(tz).strftime("%A %d %B %Y, %H:%M (%Z)")


def _details(booking: Booking) -> str:
    return (
        f"Service:  {booking.service.name}\n"
        f"With:     {booking.staff.display_name}\n"
        f"Where:    {booking.staff.business.name}\n"
        f"When:     {_local(booking, booking.start)}\n"
    )


def _name(user) -> str:
    return user.get_full_name() or user.email or user.username


def _message(subject: str, body: str, to: str) -> EmailMessage:
    return EmailMessage(subject=subject, body=body, from_email=settings.DEFAULT_FROM_EMAIL, to=[to])


def confirmation_email(booking: Booking) -> EmailMessage:
    body = f"Hi {_name(booking.customer)},\n\nYour booking is confirmed.\n\n{_details(booking)}"
    return _message(f"Booking confirmed: {booking.service.name}", body, booking.customer.email)


def reminder_email(booking: Booking) -> EmailMessage:
    body = (
        f"Hi {_name(booking.customer)},\n\n"
        f"A reminder that your booking is coming up within 24 hours.\n\n{_details(booking)}"
    )
    return _message(f"Reminder: {booking.service.name} tomorrow", body, booking.customer.email)


def cancelled_by_label(booking: Booking) -> str:
    if booking.cancelled_by_id is None:
        return "the system (automatic)"
    if booking.cancelled_by_id == booking.customer_id:
        return f"the customer ({_name(booking.cancelled_by)})"
    return f"the business ({booking.staff.business.name})"


def cancellation_recipient(booking: Booking):
    """Tell the party who did *not* cancel: the owner if the customer cancelled,
    otherwise (owner or system) the customer."""
    if booking.cancelled_by_id == booking.customer_id:
        return booking.staff.business.owner
    return booking.customer


def cancellation_email(booking: Booking) -> EmailMessage:
    recipient = cancellation_recipient(booking)
    reason = booking.cancellation_reason or "No reason given."
    body = (
        f"Hi {_name(recipient)},\n\n"
        f"A booking has been cancelled.\n\n{_details(booking)}\n"
        f"Cancelled by: {cancelled_by_label(booking)}\n"
        f"Reason:       {reason}\n"
    )
    return _message(f"Booking cancelled: {booking.service.name}", body, recipient.email)
