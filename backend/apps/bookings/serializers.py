from django.utils import timezone
from rest_framework import serializers

from apps.businesses.models import Service, Staff

from .models import Booking


class ErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()
    code = serializers.CharField(
        required=False, help_text="Machine-readable, e.g. slot_unavailable."
    )


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


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")


class BookingSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source="staff.display_name", read_only=True)
    service_name = serializers.CharField(source="service.name", read_only=True)
    customer_name = serializers.SerializerMethodField()
    business = serializers.IntegerField(source="staff.business_id", read_only=True)
    business_name = serializers.CharField(source="staff.business.name", read_only=True)
    business_timezone = serializers.CharField(
        source="staff.business.timezone",
        read_only=True,
        help_text="IANA zone; start/end are UTC, display them in this zone.",
    )

    class Meta:
        model = Booking
        fields = [
            "id",
            "customer",
            "customer_name",
            "business",
            "business_name",
            "business_timezone",
            "staff",
            "staff_name",
            "service",
            "service_name",
            "start",
            "end",
            "status",
            "expires_at",
            "notes",
            "cancelled_by",
            "cancellation_reason",
            "created_at",
        ]
        read_only_fields = fields

    def get_customer_name(self, obj) -> str:
        return obj.customer.get_full_name() or obj.customer.email
