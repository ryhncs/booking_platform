from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()

# Staff accounts are created by a business owner, never by self-registration.
SELF_REGISTER_ROLES = [User.Role.CUSTOMER, User.Role.OWNER]


class RegisterSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(max_length=150)
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    role = serializers.ChoiceField(choices=SELF_REGISTER_ROLES, default=User.Role.CUSTOMER)

    class Meta:
        model = User
        fields = ["id", "email", "password", "first_name", "last_name", "role"]
        read_only_fields = ["id"]

    def validate_email(self, value: str) -> str:
        value = value.lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs):
        candidate = User(
            email=attrs["email"],
            first_name=attrs.get("first_name", ""),
            last_name=attrs.get("last_name", ""),
        )
        try:
            validate_password(attrs["password"], candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs

    def create(self, validated_data):
        email = validated_data.pop("email")
        password = validated_data.pop("password")
        # The email doubles as the username so the admin login keeps working.
        return User.objects.create_user(
            username=email, email=email, password=password, **validated_data
        )


class LoginSerializer(TokenObtainPairSerializer):
    username_field = "email"


class MeSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "role"]
        read_only_fields = ["id", "email", "role"]
