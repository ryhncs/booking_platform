from django.urls import path

from . import views

urlpatterns = [
    path("availability/", views.AvailabilityView.as_view(), name="availability"),
]
