import json
import re
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.accounts.models import User, UserRole
from apps.attachments.services.base import AttachmentStorageBackend, StoredObject
from apps.attachments.services.factory import get_storage_backend
from apps.attachments.validators import AttachmentFileValidator
from apps.doctors.models import DoctorProfile, LicenseDocument, _license_storage_key


def _try_delete(backend: AttachmentStorageBackend, stored: StoredObject | None) -> None:
    """Safely delete a stored object if it exists. Never raises."""
    if stored is None:
        return
    try:
        backend.delete(stored.storage_key)
    except Exception:
        pass
from apps.patients.models import PatientProfile
from apps.specialties.models import Specialty


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


class PatientAccountUpdateSerializer(serializers.ModelSerializer):
    """Explicit mutable account fields; identity and authorization stay server-owned."""

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "phone_number",
        ]

    def _validate_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Enter at least 2 characters.")
        if value.isdigit():
            raise serializers.ValidationError("Name cannot contain only digits.")
        return value

    validate_first_name = _validate_name
    validate_last_name = _validate_name

    def validate_phone_number(self, value):
        value = value.strip()
        if value and not re.fullmatch(r"^\+?[0-9][0-9\s-]{5,19}$", value):
            raise serializers.ValidationError("Enter a valid phone number.")
        return value.replace(" ", "").replace("-", "")


class UpdateUserSerializer(PatientAccountUpdateSerializer):
    """Backward-compatible name used by current-user endpoint."""


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


class RegisterDoctorSerializer(serializers.ModelSerializer):
    """Public doctor application. Role and approval state are server-owned."""

    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True, min_length=8)
    specialty = serializers.PrimaryKeyRelatedField(
        queryset=Specialty.objects.filter(is_active=True)
    )
    medical_license_number = serializers.CharField(min_length=3, max_length=100)
    professional_bio = serializers.CharField(max_length=2000)
    workplace_name = serializers.CharField(max_length=255)
    years_of_experience = serializers.IntegerField(min_value=0, max_value=70)
    languages = serializers.JSONField(required=False)

    def validate_languages(self, value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, ValueError, json.JSONDecodeError):
                raise serializers.ValidationError("Provide languages as a valid list.")
        if not isinstance(value, list) or len(value) < 1:
            raise serializers.ValidationError("Provide at least one language.")
        seen = set()
        for lang in value:
            if lang not in ("ar", "en", "ckb"):
                raise serializers.ValidationError(f"Unsupported language: {lang}")
            if lang in seen:
                raise serializers.ValidationError(f"Duplicate language: {lang}")
            seen.add(lang)
        return value

    consultation_fee = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, min_value=Decimal("0")
    )
    education = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    certifications = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    medical_license_document = serializers.FileField(allow_empty_file=False)

    class Meta:
        model = User
        fields = [
            "first_name", "last_name", "email", "phone_number", "password",
            "password_confirm", "specialty", "medical_license_number",
            "years_of_experience", "workplace_name", "professional_bio", "languages",
            "consultation_fee", "education", "certifications",
            "medical_license_document",
        ]

    def validate_medical_license_number(self, value):
        value = value.strip()
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise serializers.ValidationError("Enter a valid license number.")
        if DoctorProfile.objects.filter(license_number__iexact=value).exists():
            raise serializers.ValidationError("This license number cannot be used.")
        return value

    def validate_medical_license_document(self, value):
        validator = AttachmentFileValidator(max_size_mb=5)
        is_valid, error_code, sha256 = validator(value)
        if not is_valid:
            error_map = {
                "empty_file": "File is empty.",
                "attachment_too_large": "File exceeds 5 MB limit.",
                "unsupported_extension": "Only PDF, JPEG, and PNG files are allowed.",
                "unsupported_media_type": "Only PDF, JPEG, and PNG files are allowed.",
                "invalid_file_signature": "File content does not match the declared format.",
                "content_type_mismatch": "File type does not match its content.",
                "unsafe_filename": "Filename contains unsafe characters.",
            }
            raise serializers.ValidationError(
                error_map.get(error_code, "Invalid file.")
            )
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        license_number = validated_data.pop("medical_license_number")
        professional_bio = validated_data.pop("professional_bio")
        education = validated_data.pop("education", "")
        certifications = validated_data.pop("certifications", "")
        qualifications = "\n".join(part for part in (education, certifications) if part)
        uploaded_file = validated_data.pop("medical_license_document")
        profile_fields = {
            key: validated_data.pop(key)
            for key in (
                "specialty", "years_of_experience", "workplace_name", "languages",
                "consultation_fee",
            )
            if key in validated_data
        }
        # Generate storage key before transaction so we can clean up on failure
        storage_key = _license_storage_key(uploaded_file.name)
        storage_backend = get_storage_backend()
        stored = None
        user = None
        profile = None
        try:
            # Persist file to storage backend
            stored = storage_backend.save(uploaded_file, storage_key)
        except Exception as exc:
            raise serializers.ValidationError(
                {"medical_license_document": "File storage is temporarily unavailable. Try again later."}
            ) from exc

        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    **validated_data,
                    password=password,
                    role=UserRole.DOCTOR,
                )
                profile = DoctorProfile.objects.create(
                    user=user,
                    license_number=license_number,
                    biography=professional_bio,
                    qualifications=qualifications,
                    is_approved=False,
                    is_accepting_consultations=False,
                    approval_status=DoctorProfile.ApprovalStatus.PENDING,
                    **profile_fields,
                )
                LicenseDocument.objects.create(
                    doctor_profile=profile,
                    storage_provider=stored.provider,
                    storage_key=stored.storage_key,
                    original_filename=uploaded_file.name,
                    extension=uploaded_file.name.rsplit(".", 1)[-1].lower() if "." in uploaded_file.name else "",
                    declared_mime_type=uploaded_file.content_type or "",
                    size_bytes=stored.size_bytes,
                )
                from apps.core.security_events import doctor_application_created
                from apps.notifications.services import notify_doctor_application

                doctor_application_created(str(user.id), str(profile.id))
                notify_doctor_application(profile)
        except IntegrityError as exc:
            # Clean up stored file on DB failure
            _try_delete(storage_backend, stored)
            if "license" in str(exc).lower():
                raise serializers.ValidationError(
                    {"medical_license_number": "This license number cannot be used."}
                ) from exc
            raise serializers.ValidationError(
                "Registration failed due to a database conflict. Try again."
            ) from exc
        except Exception as exc:
            # Clean up stored file on any unexpected DB failure
            _try_delete(storage_backend, stored)
            raise serializers.ValidationError(
                "Registration failed. Please try again later."
            ) from exc
        return user


class LoginSerializer(TokenObtainPairSerializer):
    """Extend the default token pair serializer to return user data.

    Stores tokens in ``self.tokens`` so the view can access them for
    setting HTTP-only cookies.
    """

    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user
        if not user.is_active:
            raise serializers.ValidationError(
                {"detail": "Account is disabled."}
            )
        # Store tokens for the view to set cookies
        self.tokens = {"access": data["access"], "refresh": data["refresh"]}
        data["user"] = CurrentUserSerializer(user).data
        return data
