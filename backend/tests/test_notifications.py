"""Emails and periodic tasks, run eagerly (settings.test) against real commits.

Tasks are enqueued with transaction.on_commit, so these tests commit for real
(transaction=True); the locmem mail backend collects what would be sent.
"""

from datetime import timedelta
from unittest import mock

import pytest
from django.core import mail
from django.db import transaction
from django.utils import timezone

from apps.bookings import tasks
from apps.bookings.models import Booking
from apps.bookings.services import (
    HOLD_EXPIRED_REASON,
    cancel_booking,
    confirm_booking,
    create_booking,
    expire_booking,
)

from .conftest import next_monday_at

pytestmark = pytest.mark.django_db(transaction=True)

SEND = "django.core.mail.message.EmailMessage.send"


@pytest.fixture
def booking(customer, staff, service):
    return create_booking(customer=customer, staff=staff, service=service, start=next_monday_at(10))


def make_booking(customer, staff, service, *, status, start, expires_at=None):
    return Booking.objects.create(
        customer=customer,
        staff=staff,
        service=service,
        start=start,
        end=start + timedelta(hours=1),
        status=status,
        expires_at=expires_at,
    )


class TestConfirmationEmail:
    def test_sent_to_the_customer_on_confirm(self, booking, customer):
        confirm_booking(booking)
        assert len(mail.outbox) == 1
        message = mail.outbox[0]
        assert message.to == [customer.email]
        assert "confirmed" in message.subject.lower()
        assert "Haircut" in message.body
        assert "Sara" in message.body
        assert "Salon" in message.body
        assert "10:00" in message.body  # business-local, not UTC
        booking.refresh_from_db()
        assert booking.confirmation_email_sent_at is not None

    def test_nothing_is_sent_by_creating_a_booking(self, booking):
        assert mail.outbox == []

    def test_running_the_task_again_does_not_resend(self, booking):
        confirm_booking(booking)
        assert tasks.send_confirmation_email.delay(booking.pk).get() == "duplicate"
        assert len(mail.outbox) == 1

    def test_not_sent_before_the_transaction_commits(self, booking):
        with transaction.atomic():
            confirm_booking(booking)
            assert mail.outbox == []
        assert len(mail.outbox) == 1

    def test_not_sent_if_the_transaction_rolls_back(self, booking):
        with pytest.raises(RuntimeError), transaction.atomic():
            confirm_booking(booking)
            raise RuntimeError("abort")
        assert mail.outbox == []
        booking.refresh_from_db()
        assert booking.status == Booking.Status.PENDING

    def test_skipped_if_the_booking_is_no_longer_confirmed(self, booking, customer):
        confirm_booking(booking)
        mail.outbox.clear()
        Booking.objects.filter(pk=booking.pk).update(confirmation_email_sent_at=None)
        cancel_booking(booking, cancelled_by=customer)
        mail.outbox.clear()
        assert tasks.send_confirmation_email.delay(booking.pk).get() == "skipped"
        assert mail.outbox == []

    def test_missing_booking_is_ignored(self, db):
        assert tasks.send_confirmation_email.delay(999_999).get() == "missing"


class TestCancellationEmail:
    def test_customer_cancels_owner_is_told_who_and_why(self, booking, customer, owner):
        cancel_booking(booking, cancelled_by=customer, reason="Feeling unwell")
        assert len(mail.outbox) == 1
        message = mail.outbox[0]
        assert message.to == [owner.email]
        assert "Cancelled by: the customer" in message.body
        assert "Reason:       Feeling unwell" in message.body

    def test_owner_cancels_customer_is_told_who_and_why(self, booking, customer, owner):
        cancel_booking(booking, cancelled_by=owner, reason="Stylist is ill")
        assert len(mail.outbox) == 1
        message = mail.outbox[0]
        assert message.to == [customer.email]
        assert "Cancelled by: the business (Salon)" in message.body
        assert "Reason:       Stylist is ill" in message.body

    def test_no_reason_given(self, booking, customer):
        cancel_booking(booking, cancelled_by=customer)
        assert "No reason given." in mail.outbox[0].body

    def test_sent_once_even_if_the_task_runs_again(self, booking, customer):
        cancel_booking(booking, cancelled_by=customer)
        assert tasks.send_cancellation_email.delay(booking.pk).get() == "duplicate"
        assert len(mail.outbox) == 1
        booking.refresh_from_db()
        assert booking.cancellation_email_sent_at is not None

    def test_not_sent_for_a_booking_that_is_not_cancelled(self, booking):
        assert tasks.send_cancellation_email.delay(booking.pk).get() == "skipped"
        assert mail.outbox == []


class TestReminders:
    def soon(self, **kwargs):
        return timezone.now() + timedelta(**kwargs)

    def test_confirmed_booking_within_24h_gets_one_reminder(self, customer, staff, service):
        due = make_booking(
            customer, staff, service, status=Booking.Status.CONFIRMED, start=self.soon(hours=20)
        )
        assert tasks.send_due_reminders() == 1
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [customer.email]
        assert "Reminder" in mail.outbox[0].subject
        due.refresh_from_db()
        assert due.reminder_sent_at is not None

    def test_sweep_is_idempotent(self, customer, staff, service):
        make_booking(
            customer, staff, service, status=Booking.Status.CONFIRMED, start=self.soon(hours=5)
        )
        tasks.send_due_reminders()
        assert tasks.send_due_reminders() == 0  # already reminded: not even queued
        assert len(mail.outbox) == 1

    def test_task_itself_is_idempotent(self, customer, staff, service):
        b = make_booking(
            customer, staff, service, status=Booking.Status.CONFIRMED, start=self.soon(hours=5)
        )
        assert tasks.send_reminder_email.delay(b.pk).get() == "sent"
        assert tasks.send_reminder_email.delay(b.pk).get() == "duplicate"
        assert len(mail.outbox) == 1

    @pytest.mark.parametrize(
        ("status", "hours"),
        [
            (Booking.Status.CONFIRMED, 30),  # more than 24h away
            (Booking.Status.CONFIRMED, -2),  # already started
            (Booking.Status.PENDING, 5),  # not confirmed
            (Booking.Status.CANCELLED, 5),
        ],
    )
    def test_not_reminded(self, customer, staff, service, status, hours):
        make_booking(customer, staff, service, status=status, start=self.soon(hours=hours))
        assert tasks.send_due_reminders() == 0
        assert mail.outbox == []

    def test_booking_cancelled_after_being_queued_is_skipped(self, customer, staff, service):
        b = make_booking(
            customer, staff, service, status=Booking.Status.CANCELLED, start=self.soon(hours=5)
        )
        assert tasks.send_reminder_email.delay(b.pk).get() == "skipped"
        assert mail.outbox == []


class TestReleaseExpiredHolds:
    def test_expired_pending_hold_is_cancelled_and_slot_freed(
        self, customer, make_customer, staff, service
    ):
        start = next_monday_at(10)
        held = create_booking(customer=customer, staff=staff, service=service, start=start)
        Booking.objects.filter(pk=held.pk).update(expires_at=timezone.now() - timedelta(minutes=1))

        assert tasks.release_expired_holds() == 1

        held.refresh_from_db()
        assert held.status == Booking.Status.CANCELLED
        assert held.cancelled_by is None
        assert held.cancellation_reason == HOLD_EXPIRED_REASON
        assert held.expires_at is None
        # the slot is genuinely free again
        again = create_booking(customer=make_customer(), staff=staff, service=service, start=start)
        assert again.pk != held.pk

    def test_customer_is_emailed_that_the_system_released_it(self, booking, customer):
        Booking.objects.filter(pk=booking.pk).update(expires_at=timezone.now() - timedelta(1))
        tasks.release_expired_holds()
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [customer.email]
        assert "the system" in mail.outbox[0].body
        assert HOLD_EXPIRED_REASON in mail.outbox[0].body

    def test_leaves_live_holds_and_confirmed_bookings_alone(
        self, customer, make_customer, staff, service
    ):
        live = create_booking(
            customer=customer, staff=staff, service=service, start=next_monday_at(10)
        )
        confirmed = create_booking(
            customer=make_customer(), staff=staff, service=service, start=next_monday_at(12)
        )
        confirm_booking(confirmed)
        mail.outbox.clear()

        assert tasks.release_expired_holds() == 0

        live.refresh_from_db()
        confirmed.refresh_from_db()
        assert live.status == Booking.Status.PENDING
        assert confirmed.status == Booking.Status.CONFIRMED
        assert mail.outbox == []

    def test_sweep_is_idempotent(self, booking):
        Booking.objects.filter(pk=booking.pk).update(expires_at=timezone.now() - timedelta(1))
        assert tasks.release_expired_holds() == 1
        assert tasks.release_expired_holds() == 0
        assert len(mail.outbox) == 1

    def test_expire_booking_never_cancels_a_booking_confirmed_in_the_meantime(self, booking):
        """The sweep selects ids first; expire_booking must re-check under the lock."""
        Booking.objects.filter(pk=booking.pk).update(
            status=Booking.Status.CONFIRMED, expires_at=None
        )
        assert expire_booking(booking.pk) is False
        booking.refresh_from_db()
        assert booking.status == Booking.Status.CONFIRMED

    def test_expire_booking_ignores_a_hold_that_is_still_live(self, booking):
        assert expire_booking(booking.pk) is False
        booking.refresh_from_db()
        assert booking.status == Booking.Status.PENDING

    def test_expire_booking_with_unknown_id(self, db):
        assert expire_booking(999_999) is False


class TestFailureHandling:
    def test_failed_send_is_retried_and_delivered_exactly_once(self, booking):
        with mock.patch(SEND, side_effect=[RuntimeError("smtp down"), 1]) as send:
            confirm_booking(booking)
        assert send.call_count == 2
        booking.refresh_from_db()
        assert booking.confirmation_email_sent_at is not None

    def test_gives_up_after_retries_and_releases_the_claim(self, booking):
        confirm_booking(booking)  # sent normally; reset so we can fail a fresh attempt
        Booking.objects.filter(pk=booking.pk).update(confirmation_email_sent_at=None)
        with (
            mock.patch(SEND, side_effect=RuntimeError("smtp down")) as send,
            pytest.raises(RuntimeError),
        ):
            tasks.send_confirmation_email.delay(booking.pk).get()
        assert send.call_count == 1 + 3  # first try + max_retries
        booking.refresh_from_db()
        assert booking.confirmation_email_sent_at is None  # a later run may still send it

    def test_broker_outage_does_not_break_the_booking_request(self, booking):
        with mock.patch.object(tasks.send_confirmation_email, "delay", side_effect=OSError("down")):
            confirmed = confirm_booking(booking)  # on_commit is robust: logged, not raised
        assert confirmed.status == Booking.Status.CONFIRMED
        booking.refresh_from_db()
        assert booking.status == Booking.Status.CONFIRMED


class TestResendUnsentEmails:
    """The safety net for an email whose enqueue was lost (broker down at commit)."""

    def age(self, booking, **delta):
        """Pretend the last status change happened `delta` ago."""
        Booking.objects.filter(pk=booking.pk).update(updated_at=timezone.now() - timedelta(**delta))

    def confirm_losing_the_email(self, booking):
        with mock.patch.object(
            tasks.send_confirmation_email, "delay", side_effect=OSError("broker down")
        ):
            confirm_booking(booking)
        assert mail.outbox == []

    def cancel_losing_the_email(self, booking, **kwargs):
        with mock.patch.object(
            tasks.send_cancellation_email, "delay", side_effect=OSError("broker down")
        ):
            cancel_booking(booking, **kwargs)
        assert mail.outbox == []

    def test_lost_confirmation_is_eventually_sent(self, booking, customer):
        self.confirm_losing_the_email(booking)
        self.age(booking, minutes=3)

        assert tasks.resend_unsent_emails() == 1

        assert [m.to for m in mail.outbox] == [[customer.email]]
        assert "confirmed" in mail.outbox[0].subject.lower()
        booking.refresh_from_db()
        assert booking.confirmation_email_sent_at is not None

    def test_lost_cancellation_is_eventually_sent_with_who_and_why(self, booking, customer, owner):
        self.cancel_losing_the_email(booking, cancelled_by=customer, reason="Changed my mind")
        self.age(booking, minutes=3)

        assert tasks.resend_unsent_emails() == 1

        assert [m.to for m in mail.outbox] == [[owner.email]]
        assert "Cancelled by: the customer" in mail.outbox[0].body
        assert "Changed my mind" in mail.outbox[0].body

    def test_waits_for_the_original_task_before_assuming_it_was_lost(self, booking):
        self.confirm_losing_the_email(booking)
        self.age(booking, minutes=1)  # inside the 2 minute grace period
        assert tasks.resend_unsent_emails() == 0
        assert mail.outbox == []

    def test_does_not_touch_emails_that_were_already_sent(self, booking):
        confirm_booking(booking)  # normal path: sent immediately
        assert len(mail.outbox) == 1
        self.age(booking, minutes=10)
        assert tasks.resend_unsent_emails() == 0
        assert len(mail.outbox) == 1

    def test_sweep_is_idempotent(self, booking):
        self.confirm_losing_the_email(booking)
        self.age(booking, minutes=3)
        assert tasks.resend_unsent_emails() == 1
        assert tasks.resend_unsent_emails() == 0
        assert len(mail.outbox) == 1

    def test_a_late_original_task_does_not_double_send(self, booking):
        """The sweep and the (slow, not lost) original task both run: one email."""
        self.confirm_losing_the_email(booking)
        self.age(booking, minutes=3)
        tasks.resend_unsent_emails()
        assert tasks.send_confirmation_email.delay(booking.pk).get() == "duplicate"
        assert len(mail.outbox) == 1

    def test_cancelled_after_a_lost_confirmation_only_sends_the_cancellation(
        self, booking, customer
    ):
        self.confirm_losing_the_email(booking)
        self.cancel_losing_the_email(booking, cancelled_by=customer)
        self.age(booking, minutes=3)

        assert tasks.resend_unsent_emails() == 1  # not a stale "confirmed" email as well

        assert len(mail.outbox) == 1
        assert "cancelled" in mail.outbox[0].subject.lower()

    def test_gives_up_after_the_max_age(self, booking):
        self.confirm_losing_the_email(booking)
        self.age(booking, hours=25)
        assert tasks.resend_unsent_emails() == 0
        assert mail.outbox == []

    def test_skips_bookings_that_are_already_in_the_past(self, customer, staff, service):
        past = make_booking(
            customer,
            staff,
            service,
            status=Booking.Status.CONFIRMED,
            start=timezone.now() - timedelta(hours=3),
        )
        self.age(past, minutes=10)
        assert tasks.resend_unsent_emails() == 0
        assert mail.outbox == []

    def test_pending_bookings_are_not_emailed(self, booking):
        self.age(booking, minutes=10)
        assert tasks.resend_unsent_emails() == 0
        assert mail.outbox == []

    def test_runs_every_five_minutes(self):
        from config import celery_app

        entry = celery_app.conf.beat_schedule["resend-unsent-emails"]
        assert entry["task"] == "apps.bookings.tasks.resend_unsent_emails"
        assert entry["schedule"] == 300


def test_beat_schedule_points_at_real_tasks():
    from celery import current_app

    from config import celery_app

    celery_app.loader.import_default_modules()
    for entry in celery_app.conf.beat_schedule.values():
        assert entry["task"] in current_app.tasks
