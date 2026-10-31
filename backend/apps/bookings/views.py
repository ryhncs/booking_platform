from datetime import timedelta
from zoneinfo import ZoneInfo

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.businesses.models import Service, Staff

from . import services
from .availability import free_slots
from .models import Booking
from .serializers import (
    AvailabilityQuerySerializer,
    BookingCreateSerializer,
    BookingSerializer,
)

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


class BookingViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Bookings the caller made, plus those at businesses the caller owns.

    Everything that changes a booking goes through ``services``; rule
    violations surface as ``BookingError`` and are mapped to HTTP statuses by
    ``exceptions.api_exception_handler`` (``SlotUnavailable`` -> 409).
    """

    serializer_class = BookingSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Booking.objects.select_related("staff__business", "service").filter(
            Q(customer=user) | Q(staff__business__owner=user)
        )
        wanted = self.request.query_params.get("status")
        if wanted:
            if wanted not in Booking.Status.values:
                raise ValidationError({"status": f"Must be one of {Booking.Status.values}."})
            qs = qs.filter(status=wanted)
        return qs

    def create(self, request, *args, **kwargs):
        data = BookingCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        booking = services.create_booking(customer=request.user, **data.validated_data)
        return Response(self.get_serializer(booking).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        booking = services.confirm_booking(self.get_object())
        return Response(self.get_serializer(booking).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        booking = services.cancel_booking(self.get_object())
        return Response(self.get_serializer(booking).data)
