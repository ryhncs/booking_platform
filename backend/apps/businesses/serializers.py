from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Business, Service, Staff, WorkingHours


class OwnedBusinessField(serializers.PrimaryKeyRelatedField):
    """Only the requesting owner's own businesses are valid targets."""

    def get_queryset(self):
        return Business.objects.filter(owner=self.context["request"].user)


# Declared as an integer id for the OpenAPI schema: outside a ModelSerializer
# (e.g. WorkingHoursBulkSerializer) drf-spectacular can't infer the pk type.
@extend_schema_field(OpenApiTypes.INT)
class OwnedStaffField(serializers.PrimaryKeyRelatedField):
    def get_queryset(self):
        return Staff.objects.filter(business__owner=self.context["request"].user)


class BusinessSerializer(serializers.ModelSerializer):
    class Meta:
        model = Business
        fields = ["id", "owner", "name", "slug", "timezone", "created_at"]
        read_only_fields = ["id", "owner", "created_at"]


class StaffSerializer(serializers.ModelSerializer):
    business = OwnedBusinessField()

    class Meta:
        model = Staff
        fields = ["id", "business", "display_name", "is_active"]
        read_only_fields = ["id"]

    def validate_business(self, value):
        if self.instance and value != self.instance.business:
            raise serializers.ValidationError("A staff member cannot move to another business.")
        return value


class ServiceSerializer(serializers.ModelSerializer):
    business = OwnedBusinessField()
    staff = OwnedStaffField(many=True, required=False)

    class Meta:
        model = Service
        fields = ["id", "business", "name", "duration_minutes", "price", "staff", "is_active"]
        read_only_fields = ["id"]
        extra_kwargs = {"price": {"min_value": 0}}

    def validate_business(self, value):
        if self.instance and value != self.instance.business:
            raise serializers.ValidationError("A service cannot move to another business.")
        return value

    def validate(self, attrs):
        business = attrs.get("business") or self.instance.business
        wrong = [s.pk for s in attrs.get("staff", []) if s.business_id != business.pk]
        if wrong:
            raise serializers.ValidationError(
                {"staff": f"Staff {wrong} do not belong to this service's business."}
            )
        return attrs


class WorkingHoursSerializer(serializers.ModelSerializer):
    staff = OwnedStaffField()

    class Meta:
        model = WorkingHours
        fields = ["id", "staff", "weekday", "start_time", "end_time"]
        read_only_fields = ["id"]

    def validate_staff(self, value):
        if self.instance and value != self.instance.staff:
            raise serializers.ValidationError("A shift cannot move to another staff member.")
        return value

    def validate(self, attrs):
        current = self.instance
        staff = attrs.get("staff") or current.staff
        weekday = attrs.get("weekday", current.weekday if current else None)
        start = attrs.get("start_time", current.start_time if current else None)
        end = attrs.get("end_time", current.end_time if current else None)

        if end <= start:
            raise serializers.ValidationError({"end_time": "Must be after start_time."})

        overlapping = WorkingHours.objects.filter(
            staff=staff, weekday=weekday, start_time__lt=end, end_time__gt=start
        )
        if current:
            overlapping = overlapping.exclude(pk=current.pk)
        if overlapping.exists():
            raise serializers.ValidationError("Overlaps another shift on the same weekday.")
        return attrs


class WorkingHoursBulkSerializer(serializers.Serializer):
    """Input for POST /working-hours/bulk/: one shift on several weekdays."""

    staff = OwnedStaffField()
    weekdays = serializers.ListField(
        child=serializers.ChoiceField(choices=WorkingHours.Weekday.choices),
        allow_empty=False,
        max_length=7,
        help_text="0 = Monday ... 6 = Sunday. Duplicates are ignored.",
    )
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()

    def validate(self, attrs):
        if attrs["end_time"] <= attrs["start_time"]:
            raise serializers.ValidationError({"end_time": "Must be after start_time."})
        return attrs
