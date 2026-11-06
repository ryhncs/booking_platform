from django.db.models import ProtectedError, Q
from drf_spectacular.plumbing import build_array_type, build_basic_type
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import SAFE_METHODS
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import Conflict

from . import services
from .models import SHIFT_OVERLAP_MESSAGE, Business, Service, Staff, WorkingHours
from .permissions import IsOwnerOrReadOnly
from .serializers import (
    BusinessSerializer,
    ServiceSerializer,
    StaffSerializer,
    WorkingHoursBulkSerializer,
    WorkingHoursSerializer,
)
from .validators import iana_timezones


class CatalogViewSet(viewsets.ModelViewSet):
    """Readable by any signed-in user, writable only by the owning owner.

    Writes are scoped to ``owner_lookup == request.user``, so another owner's
    objects behave as if they don't exist (404) rather than revealing them.
    """

    permission_classes = [IsOwnerOrReadOnly]
    owner_lookup: str
    # query param -> ORM lookup, e.g. ?business=3
    filter_params: dict[str, str] = {}

    def get_queryset(self):
        qs = self.queryset.all()
        if self.request.method not in SAFE_METHODS:
            qs = qs.filter(**{self.owner_lookup: self.request.user})
        for param, lookup in self.filter_params.items():
            raw = self.request.query_params.get(param)
            if raw is None:
                continue
            try:
                qs = qs.filter(**{lookup: int(raw)})
            except ValueError:
                raise ValidationError({param: "Must be an integer."}) from None
        return qs

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise Conflict("Cannot delete: it still has bookings.") from None


class BusinessViewSet(CatalogViewSet):
    queryset = Business.objects.order_by("name")
    serializer_class = BusinessSerializer
    owner_lookup = "owner"

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("mine") in ("1", "true"):
            qs = qs.filter(owner=self.request.user)
        return qs

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class StaffViewSet(CatalogViewSet):
    queryset = Staff.objects.select_related("business").order_by("display_name")
    serializer_class = StaffSerializer
    owner_lookup = "business__owner"
    filter_params = {"business": "business_id"}

    def get_queryset(self):
        qs = super().get_queryset()
        # Customers only see bookable staff; owners also see their inactive ones.
        return qs.filter(Q(is_active=True) | Q(business__owner=self.request.user))


class ServiceViewSet(CatalogViewSet):
    queryset = Service.objects.prefetch_related("staff").order_by("name")
    serializer_class = ServiceSerializer
    owner_lookup = "business__owner"
    filter_params = {"business": "business_id", "staff": "staff"}

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(Q(is_active=True) | Q(business__owner=self.request.user))


class WorkingHoursViewSet(CatalogViewSet):
    queryset = WorkingHours.objects.select_related("staff__business")
    serializer_class = WorkingHoursSerializer
    owner_lookup = "staff__business__owner"
    filter_params = {"staff": "staff_id"}

    # The serializer's overlap check gives a friendly answer up front, but two
    # concurrent requests can both pass it; the exclusion constraint then
    # rejects one of them. save_shift turns that into the same 400.
    def perform_create(self, serializer):
        self._save(serializer)

    def perform_update(self, serializer):
        self._save(serializer)

    def _save(self, serializer):
        try:
            services.save_shift(serializer.save)
        except services.ShiftConflict:
            raise ValidationError({"non_field_errors": [SHIFT_OVERLAP_MESSAGE]}) from None

    @extend_schema(
        summary="Add the same hours on several weekdays at once (all or nothing)",
        request=WorkingHoursBulkSerializer,
        responses={
            201: WorkingHoursSerializer(many=True),
            400: OpenApiResponse(description="Invalid input, or overlaps existing hours"),
        },
    )
    @action(detail=False, methods=["post"], url_path="bulk")
    def bulk(self, request):
        # IsOwnerOrReadOnly already requires the owner role for POST; the
        # OwnedStaffField rejects staff from another owner's business.
        context = self.get_serializer_context()
        data = WorkingHoursBulkSerializer(data=request.data, context=context)
        data.is_valid(raise_exception=True)
        try:
            shifts = services.create_weekly_shifts(**data.validated_data)
        except services.ShiftOverlap as exc:
            raise ValidationError({"weekdays": [str(exc)]}) from None
        body = WorkingHoursSerializer(shifts, many=True, context=context)
        return Response(body.data, status=status.HTTP_201_CREATED)


class TimezoneListView(APIView):
    """The exact set of names ``Business.timezone`` accepts.

    Clients build their timezone picker from this rather than from the
    browser's own list, which can differ from Python's tz database.
    """

    @extend_schema(
        summary="Valid IANA timezone names for a business",
        responses={200: build_array_type(build_basic_type(OpenApiTypes.STR))},
    )
    def get(self, request):
        return Response(sorted(iana_timezones()))
