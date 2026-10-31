from rest_framework import serializers


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
