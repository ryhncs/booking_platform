"""The working_hours_no_overlap exclusion constraint and how each write path reports it."""

from datetime import time
from unittest import mock

import psycopg
import pytest
from django.db import IntegrityError, OperationalError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.forms import modelform_factory
from django.urls import reverse

from apps.businesses import services
from apps.businesses.models import SHIFT_OVERLAP_MESSAGE, Staff, WorkingHours
from apps.businesses.serializers import WorkingHoursSerializer

MON, TUE, WED = 0, 1, 2


def shift(staff, weekday, start, end):
    return WorkingHours.objects.create(
        staff=staff, weekday=weekday, start_time=time(*start), end_time=time(*end)
    )


@pytest.mark.django_db
class TestDatabaseConstraint:
    """Straight to the ORM: no serializer, no service, only PostgreSQL."""

    def test_overlapping_shift_is_refused(self, staff):
        # The fixture gives Monday 09:00-17:00.
        with pytest.raises(IntegrityError, match="working_hours_no_overlap"), transaction.atomic():
            shift(staff, MON, (16,), (18,))

    def test_shift_inside_another_is_refused(self, staff):
        with pytest.raises(IntegrityError, match="working_hours_no_overlap"), transaction.atomic():
            shift(staff, MON, (10,), (11,))

    def test_back_to_back_shifts_are_allowed(self, staff):
        # Half-open [start, end): 17:00 is not inside 09:00-17:00.
        shift(staff, MON, (17,), (20,))
        shift(staff, MON, (6,), (9,))
        assert staff.working_hours.filter(weekday=MON).count() == 3

    def test_other_weekday_or_other_staff_is_fine(self, staff, business):
        shift(staff, TUE, (9,), (17,))
        nia = Staff.objects.create(business=business, display_name="Nia")
        shift(nia, MON, (9,), (17,))

    def test_moving_a_shift_onto_another_is_refused(self, staff):
        evening = shift(staff, MON, (18,), (20,))
        evening.start_time = time(16)
        with pytest.raises(IntegrityError), transaction.atomic():
            evening.save()


@pytest.mark.django_db
class TestAdminAndModelValidation:
    """The admin validates through ModelForm -> Model.validate_constraints()."""

    def test_model_form_reports_the_friendly_message(self, staff):
        Form = modelform_factory(WorkingHours, fields="__all__")
        form = Form(
            data={"staff": staff.pk, "weekday": MON, "start_time": "16:00", "end_time": "18:00"}
        )
        assert not form.is_valid()
        assert SHIFT_OVERLAP_MESSAGE in form.non_field_errors()

    def test_model_form_accepts_back_to_back(self, staff):
        Form = modelform_factory(WorkingHours, fields="__all__")
        form = Form(
            data={"staff": staff.pk, "weekday": MON, "start_time": "17:00", "end_time": "18:00"}
        )
        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestApiMapsTheConstraint:
    """When the friendly pre-check is bypassed (as in a lost race), the DB
    constraint still rejects the write and the API still answers 400."""

    def test_single_create(self, owner, auth_client, staff):
        body = {"staff": staff.pk, "weekday": MON, "start_time": "16:00", "end_time": "18:00"}
        with mock.patch.object(WorkingHoursSerializer, "validate", lambda self, attrs: attrs):
            resp = auth_client(owner).post(reverse("working-hours-list"), body, format="json")
        assert resp.status_code == 400
        assert resp.data == {"non_field_errors": [SHIFT_OVERLAP_MESSAGE]}
        assert staff.working_hours.count() == 1

    def test_single_update(self, owner, auth_client, staff):
        evening = shift(staff, MON, (18,), (20,))
        with mock.patch.object(WorkingHoursSerializer, "validate", lambda self, attrs: attrs):
            resp = auth_client(owner).patch(
                reverse("working-hours-detail", args=[evening.pk]),
                {"start_time": "16:00"},
                format="json",
            )
        assert resp.status_code == 400
        assert resp.data == {"non_field_errors": [SHIFT_OVERLAP_MESSAGE]}
        evening.refresh_from_db()
        assert evening.start_time == time(18)

    def test_bulk_still_names_the_days(self, owner, auth_client, staff):
        real = services._clashing_days
        calls = {"n": 0}

        def precheck_misses_once(*args):
            calls["n"] += 1
            return set() if calls["n"] == 1 else real(*args)

        body = {
            "staff": staff.pk,
            "weekdays": [MON, TUE],
            "start_time": "16:00",
            "end_time": "18:00",
        }
        with mock.patch.object(services, "_clashing_days", precheck_misses_once):
            resp = auth_client(owner).post(reverse("working-hours-bulk"), body, format="json")

        assert resp.status_code == 400
        assert resp.data == {"weekdays": ["Overlaps existing hours on Monday. Nothing was added."]}
        assert sorted(staff.working_hours.values_list("weekday", flat=True)) == [MON]  # no Tuesday


class TestSaveShift:
    def deadlock(self):
        err = OperationalError("deadlock detected")
        err.__cause__ = psycopg.errors.DeadlockDetected("deadlock detected")
        return err

    @pytest.mark.django_db
    def test_retries_a_deadlock_then_succeeds(self):
        attempts = []

        def write():
            attempts.append(1)
            if len(attempts) < services.DEADLOCK_RETRIES:
                raise self.deadlock()
            return "saved"

        assert services.save_shift(write) == "saved"
        assert len(attempts) == services.DEADLOCK_RETRIES

    @pytest.mark.django_db
    def test_persistent_deadlock_becomes_a_conflict(self):
        def write():
            raise self.deadlock()

        with pytest.raises(services.ShiftConflict):
            services.save_shift(write)

    @pytest.mark.django_db
    def test_unrelated_database_errors_propagate(self):
        def write():
            raise IntegrityError('violates check constraint "working_hours_end_after_start"')

        with pytest.raises(IntegrityError):
            services.save_shift(write)


@pytest.mark.django_db(transaction=True)
def test_migration_stops_with_a_clear_message_if_shifts_already_overlap(staff):
    """0003 must refuse to continue (before 0004 adds the constraint) and say why."""

    def migrate(targets):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)

    latest = MigrationExecutor(connection).loader.graph.leaf_nodes()
    migrate([("businesses", "0002_validate_timezone")])  # constraint gone
    try:
        bad = shift(staff, MON, (12,), (18,))  # overlaps the fixture's 09:00-17:00
        with pytest.raises(RuntimeError) as exc:
            migrate([("businesses", "0003_check_no_overlapping_shifts")])
        message = str(exc.value)
        assert "working_hours_no_overlap" in message
        assert f"working hours id={bad.pk}: staff id={staff.pk}, Mon 12:00-18:00" in message
        assert "run `python manage.py migrate` again" in message

        bad.delete()  # fix the data as the message says...
        migrate(latest)  # ...and the migrations go through
    finally:
        WorkingHours.objects.filter(staff=staff).exclude(start_time=time(9)).delete()
        migrate(latest)
    with pytest.raises(IntegrityError), transaction.atomic():
        shift(staff, MON, (12,), (18,))  # constraint is back
