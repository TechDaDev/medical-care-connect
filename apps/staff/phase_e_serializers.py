from django.db.models import Count, Q
from django.utils.text import slugify
from rest_framework import serializers

from apps.attachments.choices import AttachmentStatus, ScanStatus
from apps.attachments.models import ConsultationAttachment
from apps.consultations.models import ConsultationStatus
from apps.specialties.models import Specialty


OPEN_CONSULTATION_STATUSES = (
    ConsultationStatus.SUBMITTED,
    ConsultationStatus.ACCEPTED,
    ConsultationStatus.INTAKE_IN_PROGRESS,
    ConsultationStatus.INTAKE_COMPLETED,
    ConsultationStatus.DOCTOR_REVIEW,
    ConsultationStatus.AWAITING_PATIENT_RESPONSE,
    ConsultationStatus.AWAITING_DOCTOR_RESPONSE,
    ConsultationStatus.UNDER_REVIEW,
)


def specialty_admin_queryset():
    return Specialty.objects.annotate(
        doctor_count=Count("doctor_profiles", distinct=True),
        active_doctor_count=Count(
            "doctor_profiles",
            filter=Q(
                doctor_profiles__is_approved=True,
                doctor_profiles__user__is_active=True,
            ),
            distinct=True,
        ),
        active_consultation_count=Count(
            "consultations",
            filter=Q(consultations__status__in=OPEN_CONSULTATION_STATUSES),
            distinct=True,
        ),
    )


class SpecialtyAdminListSerializer(serializers.ModelSerializer):
    code = serializers.CharField(source="slug", read_only=True)
    doctor_count = serializers.IntegerField(read_only=True)
    active_doctor_count = serializers.IntegerField(read_only=True)
    active_consultation_count = serializers.IntegerField(read_only=True)
    available_actions = serializers.SerializerMethodField()

    class Meta:
        model = Specialty
        fields = [
            "id", "code", "name_en", "name_ar", "name_ckb", "is_active",
            "display_order", "doctor_count", "active_doctor_count",
            "active_consultation_count", "created_at", "updated_at",
            "available_actions",
        ]
        read_only_fields = fields

    def get_available_actions(self, obj) -> list[str]:
        actions = ["edit"]
        if obj.is_active:
            actions.append("deactivate")
        else:
            actions.append("activate")
        return actions


class SpecialtyAdminDetailSerializer(SpecialtyAdminListSerializer):
    description = serializers.CharField(read_only=True)

    class Meta(SpecialtyAdminListSerializer.Meta):
        fields = SpecialtyAdminListSerializer.Meta.fields + ["description"]


class SpecialtyAdminWriteSerializer(serializers.ModelSerializer):
    code = serializers.CharField(source="slug", min_length=1, max_length=255)
    expected_updated_at = serializers.DateTimeField(write_only=True, required=False)

    class Meta:
        model = Specialty
        fields = [
            "code", "name_en", "name_ar", "name_ckb", "description",
            "display_order", "expected_updated_at",
        ]
        extra_kwargs = {
            "name_en": {"required": True, "min_length": 1, "max_length": 255},
            "name_ar": {"required": True, "min_length": 1, "max_length": 255},
            "name_ckb": {"required": True, "min_length": 1, "max_length": 255},
            "description": {"required": False, "allow_blank": True, "max_length": 2000},
            "display_order": {"min_value": 0},
        }

    def validate(self, attrs):
        for field in ("name_en", "name_ar", "name_ckb", "description"):
            if field in attrs:
                attrs[field] = attrs[field].strip()
        raw_slug = attrs.get("slug")
        if raw_slug is not None:
            normalized = slugify(raw_slug.strip())
            if not normalized:
                raise serializers.ValidationError({"code": "Enter a valid code."})
            attrs["slug"] = normalized

        instance_id = self.instance.pk if self.instance else None
        if "slug" in attrs and Specialty.objects.filter(
            slug__iexact=attrs["slug"]
        ).exclude(pk=instance_id).exists():
            raise serializers.ValidationError({"code": "This code is already in use."})

        for field in ("name_en", "name_ar", "name_ckb"):
            if field in attrs and Specialty.objects.filter(
                **{f"{field}__iexact": attrs[field]}
            ).exclude(pk=instance_id).exists():
                raise serializers.ValidationError(
                    {field: "This translated name is already in use."}
                )
        return attrs

    def create(self, validated_data):
        validated_data.pop("expected_updated_at", None)
        validated_data["name"] = validated_data["name_en"]
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("expected_updated_at", None)
        if "name_en" in validated_data:
            validated_data["name"] = validated_data["name_en"]
        return super().update(instance, validated_data)


class SpecialtyReorderItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    display_order = serializers.IntegerField(min_value=0)


class SpecialtyReorderSerializer(serializers.Serializer):
    items = SpecialtyReorderItemSerializer(many=True, allow_empty=False)

    def validate_items(self, items):
        ids = [item["id"] for item in items]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Duplicate specialty IDs are not allowed.")
        existing = set(Specialty.objects.values_list("id", flat=True))
        supplied = set(ids)
        if supplied != existing:
            raise serializers.ValidationError(
                "Items must contain every specialty ID exactly once."
            )
        return items


def attachment_retention_eligible(obj: ConsultationAttachment) -> bool:
    from apps.attachments.services.retention import get_retention_cutoff

    cutoff = get_retention_cutoff()
    return bool(
        cutoff
        and obj.status == AttachmentStatus.DELETED
        and obj.is_deleted
        and obj.deleted_at
        and obj.deleted_at < cutoff
        and obj.storage_deleted_at is None
        and obj.consultation.status
        in (ConsultationStatus.COMPLETED, ConsultationStatus.CANCELLED)
    )


def attachment_available_actions(obj: ConsultationAttachment) -> list[str]:
    if obj.storage_deleted_at:
        return []
    actions: list[str] = []
    if obj.status in (
        AttachmentStatus.PENDING,
        AttachmentStatus.QUARANTINED,
        AttachmentStatus.AVAILABLE,
    ) and obj.scan_status != ScanStatus.PENDING:
        actions.append("rescan")
    if obj.status in (AttachmentStatus.PENDING, AttachmentStatus.QUARANTINED):
        actions.append("reject")
    if (
        obj.status == AttachmentStatus.QUARANTINED
        and obj.scan_status == ScanStatus.CLEAN
        and obj.scan_provider
        and obj.scan_provider != "disabled"
    ):
        actions.append("release")
    if attachment_retention_eligible(obj):
        actions.append("retention_delete")
    if obj.status == AttachmentStatus.AVAILABLE and not obj.is_deleted:
        actions.append("download")
    return actions


class AdminAttachmentListSerializer(serializers.ModelSerializer):
    filename = serializers.CharField(source="safe_display_name", read_only=True)
    mime_type = serializers.CharField(source="detected_mime_type", read_only=True)
    scanner_status = serializers.CharField(source="scan_status", read_only=True)
    scanner_provider = serializers.CharField(source="scan_provider", read_only=True)
    owner_type = serializers.SerializerMethodField()
    owner_reference = serializers.SerializerMethodField()
    retention_eligible = serializers.SerializerMethodField()
    available_actions = serializers.SerializerMethodField()

    class Meta:
        model = ConsultationAttachment
        fields = [
            "id", "filename", "mime_type", "size_bytes", "status",
            "scanner_status", "scanner_provider", "scan_completed_at",
            "owner_type", "owner_reference", "created_at", "updated_at",
            "retention_eligible", "available_actions",
        ]
        read_only_fields = fields

    def get_owner_type(self, obj) -> str:
        return "consultation"

    def get_owner_reference(self, obj) -> str:
        return str(obj.consultation_id)

    def get_retention_eligible(self, obj) -> bool:
        return attachment_retention_eligible(obj)

    def get_available_actions(self, obj) -> list[str]:
        return attachment_available_actions(obj)


class AdminAttachmentDetailSerializer(AdminAttachmentListSerializer):
    file_extension = serializers.CharField(source="extension", read_only=True)
    checksum = serializers.CharField(source="sha256", read_only=True)
    quarantine_reason = serializers.CharField(read_only=True)
    rejection_reason = serializers.CharField(read_only=True)
    action_history = serializers.SerializerMethodField()

    class Meta(AdminAttachmentListSerializer.Meta):
        fields = AdminAttachmentListSerializer.Meta.fields + [
            "file_extension", "checksum", "quarantine_reason",
            "rejection_reason", "action_history",
        ]

    def get_action_history(self, obj) -> list[dict]:
        return [
            {
                "id": str(event.id),
                "event_type": event.event_type,
                "created_at": event.created_at.isoformat(),
                "safe_metadata": event.safe_metadata,
            }
            for event in obj.audit_events.all()[:100]
        ]


class AttachmentAdminActionSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=3, max_length=500)
    expected_status = serializers.ChoiceField(choices=AttachmentStatus.choices)

    def validate_reason(self, value):
        return value.strip()
