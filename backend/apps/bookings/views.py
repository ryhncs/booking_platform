from datetime import timedelta
from zoneinfo import ZoneInfo

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.businesses.models import Service, Staff

from .availability import free_slots
from .serializers import AvailabilityQuerySerializer

MAX_DAYS_AHEAD = 180


class AvailabilityView(APIView):
    """Free slots for one staff member and service on one local date."""

    def get(self, request):
        query = AvailabilityQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data

        staff = get_object_or_404(
            Staff.objects.select_related("business"), pk=params["staff"], is_active=True
        )
        service = get_object_or_404(Service, pk=params["service"], is_active=True)
        if service.business_id != staff.business_id or not service.staff.filter(pk=staff.pk):
            raise ValidationError("This staff member does not offer this service.")

        tz = ZoneInfo(staff.business.timezone)
        today = timezone.now().astimezone(tz).date()
        day = params["date"]
        if not today <= day <= today + timedelta(days=MAX_DAYS_AHEAD):
            raise ValidationError(
                {"date": f"Must be between {today} and {MAX_DAYS_AHEAD} days from now."}
            )

        slots = free_slots(staff=staff, service=service, day=day)
        body = {
            "staff": staff.pk,
            "service": service.pk,
            "date": day.isoformat(),
            "timezone": staff.business.timezone,
            # Local wall-clock time with offset, e.g. 2026-11-02T09:00:00+03:30.
            "slots": [{"start": s.isoformat(), "end": e.isoformat()} for s, e in slots],
        }
        return Response(body)
