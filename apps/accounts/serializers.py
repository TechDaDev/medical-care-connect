from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.accounts.models import User, UserRole
from apps.patients.models import PatientProfile


class UserSerializer(serializers.ModelSerializer):
    """Serializer for the User model."""

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone_number",
            "role",
            "is_active",
            "date_joined",
        ]
        read_only_fields = ["id", "is_active", "date_joined", "full_name"]


class CurrentUserSerializer(serializers.ModelSerializer):
    """Read-only serializer for the current authenticated user."""

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone_number",
            "role",
            "is_active",
            "is_staff",
            "date_joined",
            "updated_at",
        ]
        read_only_fields = fields


class UpdateUserSerializer(serializers.ModelSerializer):
    """Serializer for partial updates to the current user's basic profile fields."""

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "phone_number",
        ]


class RegisterPatientSerializer(serializers.ModelSerializer):
    """Serializer for patient registration.

    Creates a User with role=patient and a linked PatientProfile.
    """

    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True, min_length=8)

    # Patient profile fields (optional)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    gender = serializers.ChoiceField(
        choices=PatientProfile._meta.get_field("gender").choices,
        required=False,
    )
    preferred_language = serializers.ChoiceField(
        choices=PatientProfile._meta.get_field("preferred_language").choices,
        required=False,
    )

    class Meta:
        model = User
        fields = [
            "email",
            "password",
            "password_confirm",
            "first_name",
            "last_name",
            "phone_number",
            "date_of_birth",
            "gender",
            "preferred_language",
        ]

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError(
                {"password_confirm": "Passwords do not match."}
            )
        return attrs

    def create(self, validated_data):
        profile_fields = {
            "date_of_birth": validated_data.pop("date_of_birth", None),
            "gender": validated_data.pop("gender", PatientProfile._meta.get_field("gender").default),
            "preferred_language": validated_data.pop(
                "preferred_language",
                PatientProfile._meta.get_field("preferred_language").default,
            ),
        }
        password = validated_data.pop("password")
        validated_data["role"] = UserRole.PATIENT
        user = User.objects.create_user(**validated_data, password=password)
        PatientProfile.objects.create(user=user, **{k: v for k, v in profile_fields.items() if v is not None})
        return user


class LoginSerializer(TokenObtainPairSerializer):
    """Extend the default token pair serializer to return user data."""

    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user
        if not user.is_active:
            raise serializers.ValidationError(
                {"detail": "Account is disabled."}
            )
        data["user"] = CurrentUserSerializer(user).data
        return data
