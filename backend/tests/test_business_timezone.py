import pytest
from django.core.exceptions import ValidationError

from apps.businesses.admin import BusinessAdminForm


@pytest.mark.parametrize("name", ["UTC", "Asia/Tehran", "America/New_York"])
def test_valid_timezone_accepted(business, name):
    business.timezone = name
    business.full_clean()


@pytest.mark.parametrize("name", ["", "Mars/Olympus", "tehran", "+03:30", "../etc/passwd"])
def test_invalid_timezone_rejected(business, name):
    business.timezone = name
    with pytest.raises(ValidationError) as exc:
        business.full_clean()
    assert "timezone" in exc.value.message_dict


def test_admin_form_uses_dropdown_of_iana_names(owner):
    form = BusinessAdminForm()
    choices = dict(form.fields["timezone"].choices)
    assert "Asia/Tehran" in choices
    assert "Mars/Olympus" not in choices


def test_admin_form_rejects_unknown_timezone(owner):
    form = BusinessAdminForm(
        data={"owner": owner.pk, "name": "X", "slug": "x", "timezone": "Mars/Olympus"}
    )
    assert not form.is_valid()
    assert "timezone" in form.errors
