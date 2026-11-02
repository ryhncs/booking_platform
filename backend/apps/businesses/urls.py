from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("businesses", views.BusinessViewSet, basename="business")
router.register("staff", views.StaffViewSet, basename="staff")
router.register("services", views.ServiceViewSet, basename="service")
router.register("working-hours", views.WorkingHoursViewSet, basename="working-hours")

urlpatterns = [
    path("timezones/", views.TimezoneListView.as_view(), name="timezones"),
    *router.urls,
]
