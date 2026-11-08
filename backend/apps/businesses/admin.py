from itertools import combinations

from django import forms
from django.contrib import admin

from .models import Business, Service, Staff, TimeOff, WorkingHours
from .validators import iana_timezones


class BusinessAdminForm(forms.ModelForm):
    timezone = forms.ChoiceField(choices=[(tz, tz) for tz in sorted(iana_timezones())])

    class Meta:
        model = Business
        fields = ["owner", "name", "slug", "timezone"]


class StaffInline(admin.TabularInline):
    model = Staff
    extra = 0


class WorkingHoursInlineFormSet(forms.BaseInlineFormSet):
    """Reject rows in the same submission that overlap each other.

    Inline rows get no overlap check of their own: Django leaves an inline's
    foreign key out of model validation, which makes it skip every constraint
    using that field, including working_hours_no_overlap. Overlapping rows
    would reach the database and fail the save with a 500. This reports them
    as a form error instead; the constraint remains the actual guarantee.
    """

    def clean(self):
        super().clean()
        rows = []
        for number, form in enumerate(self.forms, start=1):
            is_blank_extra_row = form.instance.pk is None and not form.has_changed()
            # A row with its own errors is already reported and blocks the save.
            if is_blank_extra_row or form.errors or self._should_delete_form(form):
                continue
            data = form.cleaned_data
            rows.append((number, data["weekday"], data["start_time"], data["end_time"]))

        errors = []
        for first, second in combinations(rows, 2):
            number_a, weekday_a, start_a, end_a = first
            number_b, weekday_b, start_b, end_b = second
            # Half-open [start, end): back-to-back shifts don't overlap.
            if weekday_a == weekday_b and start_a < end_b and start_b < end_a:
                day = WorkingHours.Weekday(weekday_a).label
                errors.append(
                    f"Row {number_a} ({day} {start_a:%H:%M}–{end_a:%H:%M}) overlaps "
                    f"row {number_b} ({day} {start_b:%H:%M}–{end_b:%H:%M})."
                )
        if errors:
            raise forms.ValidationError(errors)


class WorkingHoursInline(admin.TabularInline):
    model = WorkingHours
    formset = WorkingHoursInlineFormSet
    extra = 0


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    form = BusinessAdminForm
    list_display = ("name", "owner", "timezone")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [StaffInline]


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ("display_name", "business", "is_active")
    list_filter = ("business", "is_active")
    inlines = [WorkingHoursInline]


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "business", "duration_minutes", "price", "is_active")
    list_filter = ("business",)
    filter_horizontal = ("staff",)


@admin.register(TimeOff)
class TimeOffAdmin(admin.ModelAdmin):
    list_display = ("staff", "start", "end", "reason")
