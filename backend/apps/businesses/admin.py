from django.contrib import admin

from .models import Business, Service, Staff, TimeOff, WorkingHours


class StaffInline(admin.TabularInline):
    model = Staff
    extra = 0


class WorkingHoursInline(admin.TabularInline):
    model = WorkingHours
    extra = 0


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
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
