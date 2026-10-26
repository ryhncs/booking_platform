from django.contrib import admin

from .models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("start", "staff", "service", "customer", "status")
    list_filter = ("status", "staff__business")
    list_select_related = ("staff", "service", "customer")
    date_hierarchy = "start"
