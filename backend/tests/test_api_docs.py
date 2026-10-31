import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_swagger_ui_is_public(api_client):
    resp = api_client.get("/api/docs/")
    assert resp.status_code == 200
    assert b"swagger" in resp.content.lower()


def test_schema_documents_every_endpoint(api_client):
    resp = api_client.get(reverse("schema"), {"format": "json"})
    assert resp.status_code == 200
    schema = resp.json()
    paths = set(schema["paths"])
    assert {
        "/api/auth/register/",
        "/api/auth/login/",
        "/api/auth/refresh/",
        "/api/me/",
        "/api/businesses/",
        "/api/staff/",
        "/api/services/",
        "/api/working-hours/",
        "/api/availability/",
        "/api/bookings/",
        "/api/bookings/{id}/confirm/",
        "/api/bookings/{id}/cancel/",
    } <= paths


def test_booking_create_documents_the_409(api_client):
    schema = api_client.get(reverse("schema"), {"format": "json"}).json()
    responses = schema["paths"]["/api/bookings/"]["post"]["responses"]
    assert {"201", "400", "409"} <= set(responses)
