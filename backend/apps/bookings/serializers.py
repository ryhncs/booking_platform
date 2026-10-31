from django.utils import timezone
from rest_framework import serializers

from apps.businesses.models import Service, Staff

from .models import Booking


class AvailabilityQuerySerializer(serializers.Serializer):
    staff = serializers.IntegerField(min_value=1)
    service = serializers.IntegerField(min_value=1)
    date = serializers.DateField(help_text="Calendar date in the business's timezone.")


class SlotSerializer(serializers.Serializer):
    start = serializers.CharField(help_text="ISO 8601, business-local time with UTC offset.")
    end = serializers.CharField(help_text="ISO 8601, business-local time with UTC offset.")


class AvailabilitySerializer(serializers.Serializer):
    staff = serializers.IntegerField()
    service = serializers.IntegerField()
    date = serializers.CharField()
    timezone = serializers.CharField(help_text="IANA zone the slot times are expressed in.")
    slots = SlotSerializer(many=True)


class OffsetDateTimeField(serializers.DateTimeField):
    """Rejects datetimes without a UTC offset.

    DRF would otherwise silently read "2026-11-02T09:00:00" as UTC, which is
    almost never what a client booking in business-local time means.
    """

    def enforce_timezone(self, value):
        if timezone.is_naive(value):
            raise serializers.ValidationError(
                "Include a UTC offset, e.g. 2026-11-02T09:00:00+03:30 or ...Z."
            )
        return super().enforce_timezone(value)


class BookingCreateSerializer(serializers.Serializer):
    staff = serializers.PrimaryKeyRelatedField(queryset=Staff.objects.select_related("business"))
    service = serializers.PrimaryKeyRelatedField(queryset=Service.objects.all())
    start = OffsetDateTimeField()
    notes = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")


class BookingSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source="staff.display_name", read_only=True)
    service_name = serializers.CharField(source="service.name", read_only=True)

    class Meta:
        model = Booking
        fields = [
            "id",
            "customer",
            "staff",
            "staff_name",
            "service",
            "service_name",
            "start",
            "end",
            "status",
            "expires_at",
            "notes",
            "created_at",
        ]
        read_only_fields = fields
