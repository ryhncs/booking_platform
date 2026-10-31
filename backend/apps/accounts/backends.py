from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    """Authenticate with ``email`` + ``password`` (case-insensitive email)."""

    def authenticate(self, request, email=None, password=None, **kwargs):
        if email is None or password is None:
            return None
        User = get_user_model()
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            # Run the hasher anyway so response time doesn't reveal which emails exist.
            User().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
