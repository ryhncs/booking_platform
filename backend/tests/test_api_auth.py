import pytest
from django.urls import reverse

from apps.accounts.models import User

REGISTER = "auth-register"
LOGIN = "auth-login"
REFRESH = "auth-refresh"
ME = "me"

PASSWORD = "correct-horse-battery-9"


def register(api_client, **overrides):
    payload = {"email": "Ann@Example.com", "password": PASSWORD, **overrides}
    return api_client.post(reverse(REGISTER), payload, format="json")


@pytest.mark.django_db
class TestRegister:
    def test_creates_customer_with_normalised_email(self, api_client):
        resp = register(api_client)
        assert resp.status_code == 201
        assert resp.data["email"] == "ann@example.com"
        assert resp.data["role"] == "customer"
        assert "password" not in resp.data
        user = User.objects.get(email="ann@example.com")
        assert user.check_password(PASSWORD)

    def test_owner_role_allowed(self, api_client):
        assert register(api_client, role="owner").data["role"] == "owner"

    def test_cannot_self_register_as_staff_or_superuser(self, api_client):
        assert register(api_client, role="staff").status_code == 400
        resp = register(api_client, is_superuser=True, is_staff=True)
        assert resp.status_code == 201
        user = User.objects.get(email="ann@example.com")
        assert not user.is_superuser and not user.is_staff

    def test_duplicate_email_is_case_insensitive(self, api_client):
        register(api_client)
        resp = register(api_client, email="ann@EXAMPLE.com")
        assert resp.status_code == 400
        assert "email" in resp.data

    def test_weak_password_rejected(self, api_client):
        resp = register(api_client, password="12345678")
        assert resp.status_code == 400
        assert "password" in resp.data


@pytest.mark.django_db
class TestLogin:
    def test_login_returns_token_pair(self, api_client):
        register(api_client)
        resp = api_client.post(
            reverse(LOGIN), {"email": "ANN@example.com", "password": PASSWORD}, format="json"
        )
        assert resp.status_code == 200
        assert {"access", "refresh"} <= set(resp.data)

    def test_wrong_password_is_401(self, api_client):
        register(api_client)
        resp = api_client.post(
            reverse(LOGIN), {"email": "ann@example.com", "password": "nope"}, format="json"
        )
        assert resp.status_code == 401

    def test_unknown_email_is_401(self, api_client):
        resp = api_client.post(
            reverse(LOGIN), {"email": "ghost@example.com", "password": PASSWORD}, format="json"
        )
        assert resp.status_code == 401

    def test_refresh_issues_new_access_token(self, api_client):
        register(api_client)
        tokens = api_client.post(
            reverse(LOGIN), {"email": "ann@example.com", "password": PASSWORD}, format="json"
        ).data
        resp = api_client.post(reverse(REFRESH), {"refresh": tokens["refresh"]}, format="json")
        assert resp.status_code == 200
        assert "access" in resp.data

    def test_access_token_is_not_accepted_as_refresh(self, api_client):
        register(api_client)
        tokens = api_client.post(
            reverse(LOGIN), {"email": "ann@example.com", "password": PASSWORD}, format="json"
        ).data
        resp = api_client.post(reverse(REFRESH), {"refresh": tokens["access"]}, format="json")
        assert resp.status_code == 401


@pytest.mark.django_db
class TestMe:
    def test_requires_authentication(self, api_client):
        assert api_client.get(reverse(ME)).status_code == 401

    def test_bearer_token_flow(self, api_client):
        register(api_client)
        tokens = api_client.post(
            reverse(LOGIN), {"email": "ann@example.com", "password": PASSWORD}, format="json"
        ).data
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        resp = api_client.get(reverse(ME))
        assert resp.status_code == 200
        assert resp.data["email"] == "ann@example.com"

    def test_patch_updates_name_but_not_role_or_email(self, customer, auth_client):
        client = auth_client(customer)
        resp = client.patch(
            reverse(ME),
            {"first_name": "Cy", "role": "owner", "email": "evil@example.com"},
            format="json",
        )
        assert resp.status_code == 200
        customer.refresh_from_db()
        assert customer.first_name == "Cy"
        assert customer.role == "customer"
        assert customer.email == "cust@example.com"
