"""Translate service-layer ``BookingError``s into HTTP responses.

Views just call ``services.py``; this handler is the single place that decides
how each rule violation looks on the wire.
"""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from .services import BookingError, InvalidBookingRequest, OutsideWorkingHours, SlotUnavailable

STATUS_FOR_ERROR: dict[type[BookingError], int] = {
    SlotUnavailable: status.HTTP_409_CONFLICT,
    OutsideWorkingHours: status.HTTP_400_BAD_REQUEST,
    InvalidBookingRequest: status.HTTP_400_BAD_REQUEST,
}


def api_exception_handler(exc, context):
    if isinstance(exc, BookingError):
        http_status = STATUS_FOR_ERROR.get(type(exc), status.HTTP_400_BAD_REQUEST)
        return Response({"detail": str(exc), "code": exc.code}, status=http_status)
    return drf_exception_handler(exc, context)
