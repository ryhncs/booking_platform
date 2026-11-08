"""The WorkingHours inline on the Staff admin, submitted the way a browser does.

Django skips the exclusion constraint when validating an inline row (the
constraint uses the inline's foreign key), so overlapping rows are only caught
by the inline formset. The test client re-raises server errors, so a missing
check fails these tests with the database's IntegrityError, not a 500 page.
"""

from datetime import time

import pytest
from django.urls import reverse

from apps.businesses.models import Staff, WorkingHours

pytestmark = pytest.mark.django_db

MON, TUE = 0, 1


def row(weekday="", start="", end="", pk="", delete=False):
    return {"weekday": weekday, "start": start, "end": end, "id": pk, "delete": delete}


def payload(staff_fields, rows, *, initial=0, staff_pk=""):
    data = {
        **staff_fields,
        "working_hours-TOTAL_FORMS": len(rows),
        "working_hours-INITIAL_FORMS": initial,
        "working_hours-MIN_NUM_FORMS": 0,
        "working_hours-MAX_NUM_FORMS": 1000,
    }
    for i, r in enumerate(rows):
        data |= {
            f"working_hours-{i}-id": r["id"],
            f"working_hours-{i}-staff": staff_pk,
            f"working_hours-{i}-weekday": r["weekday"],
            f"working_hours-{i}-start_time": r["start"],
            f"working_hours-{i}-end_time": r["end"],
        }
        if r["delete"]:
            data[f"working_hours-{i}-DELETE"] = "on"
    return data


@pytest.fixture
def post_change(admin_client, staff):
    """Submit the admin change page for the `staff` fixture (Monday 09:00-17:00)."""

    def _post(rows, initial=0):
        fields = {
            "business": staff.business_id,
            "display_name": staff.display_name,
            "is_active": "on",
        }
        url = reverse("admin:businesses_staff_change", args=[staff.pk])
        return admin_client.post(url, payload(fields, rows, initial=initial, staff_pk=staff.pk))

    return _post


def errors_of(response):
    assert response.status_code == 200  # re-rendered form, not a redirect or a 500
    formset = response.context["inline_admin_formsets"][0].formset
    return list(formset.non_form_errors())


def tuesdays(staff):
    return list(staff.working_hours.filter(weekday=TUE).values_list("start_time", "end_time"))


def test_two_overlapping_new_rows_get_a_form_error_naming_them(post_change, staff):
    resp = post_change([row(TUE, "09:00", "12:00"), row(TUE, "11:00", "14:00")])

    assert errors_of(resp) == ["Row 1 (Tuesday 09:00–12:00) overlaps row 2 (Tuesday 11:00–14:00)."]
    assert "Row 1 (Tuesday 09:00–12:00) overlaps row 2" in resp.content.decode()  # really shown
    assert tuesdays(staff) == []


def test_every_clashing_pair_is_reported(post_change):
    resp = post_change(
        [row(TUE, "09:00", "12:00"), row(TUE, "11:00", "14:00"), row(TUE, "13:00", "15:00")]
    )

    assert errors_of(resp) == [
        "Row 1 (Tuesday 09:00–12:00) overlaps row 2 (Tuesday 11:00–14:00).",
        "Row 2 (Tuesday 11:00–14:00) overlaps row 3 (Tuesday 13:00–15:00).",
    ]


def test_overlapping_rows_when_adding_a_new_staff_member(admin_client, business):
    # The staff member doesn't exist yet, so no row has anything in the database to clash with.
    fields = {"business": business.pk, "display_name": "Nia", "is_active": "on"}
    resp = admin_client.post(
        reverse("admin:businesses_staff_add"),
        payload(fields, [row(TUE, "09:00", "12:00"), row(TUE, "11:00", "14:00")]),
    )

    assert errors_of(resp) == ["Row 1 (Tuesday 09:00–12:00) overlaps row 2 (Tuesday 11:00–14:00)."]
    assert not Staff.objects.filter(display_name="Nia").exists()


def test_back_to_back_rows_are_saved(post_change, staff):
    resp = post_change([row(TUE, "09:00", "12:00"), row(TUE, "12:00", "17:00")])

    assert resp.status_code == 302
    assert tuesdays(staff) == [(time(9), time(12)), (time(12), time(17))]


def test_same_hours_on_different_weekdays_are_saved(post_change, staff):
    resp = post_change([row(TUE, "09:00", "12:00"), row(3, "09:00", "12:00")])

    assert resp.status_code == 302
    assert sorted(staff.working_hours.values_list("weekday", flat=True)) == [MON, TUE, 3]


def test_a_new_row_marked_for_deletion_is_ignored(post_change, staff):
    resp = post_change([row(TUE, "09:00", "12:00"), row(TUE, "11:00", "14:00", delete=True)])

    assert resp.status_code == 302
    assert tuesdays(staff) == [(time(9), time(12))]


def test_a_blank_extra_row_is_ignored(post_change, staff):
    resp = post_change([row(TUE, "09:00", "12:00"), row()])

    assert resp.status_code == 302
    assert tuesdays(staff) == [(time(9), time(12))]


def test_replacing_a_saved_row_in_one_submission(post_change, staff):
    """Delete Monday 09:00-17:00 and add an overlapping Monday 10:00-11:00 together."""
    monday = WorkingHours.objects.get(staff=staff)
    resp = post_change(
        [row(MON, "09:00", "17:00", pk=monday.pk, delete=True), row(MON, "10:00", "11:00")],
        initial=1,
    )

    assert resp.status_code == 302
    assert list(staff.working_hours.values_list("start_time", "end_time")) == [(time(10), time(11))]


def test_an_existing_row_edited_onto_a_new_row_is_caught(post_change, staff):
    monday = WorkingHours.objects.get(staff=staff)
    resp = post_change(
        [row(TUE, "09:00", "17:00", pk=monday.pk), row(TUE, "10:00", "11:00")],
        initial=1,
    )

    assert errors_of(resp) == ["Row 1 (Tuesday 09:00–17:00) overlaps row 2 (Tuesday 10:00–11:00)."]
    monday.refresh_from_db()
    assert monday.weekday == MON
