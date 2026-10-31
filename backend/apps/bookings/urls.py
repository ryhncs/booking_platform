from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("bookings", views.BookingViewSet, basename="booking")

urlpatterns = [
    path("availability/", views.AvailabilityView.as_view(), name="availability"),
    *router.urls,
]
