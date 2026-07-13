"""
Process pending data exports.

Usage:
  python manage.py process_data_exports            # list only (dry-run)
  python manage.py process_data_exports --execute   # process pending
  python manage.py process_data_exports --batch-size 10
"""

import io
import json
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.privacy.models import DataExportRequest, ExportStatus


class Command(BaseCommand):
    help = "Process pending data export requests."

    def add_arguments(self, parser):
        parser.add_argument("--execute", action="store_true", default=False)
        parser.add_argument("--batch-size", type=int, default=10)

    def handle(self, *args, **options):
        execute = options["execute"]
        batch_size = options["batch_size"]

        pending = DataExportRequest.objects.filter(status=ExportStatus.PENDING)[:batch_size]
        total = pending.count()

        if total == 0:
            self.stdout.write("No pending exports.")
            return

        self.stdout.write(f"Pending exports: {total}")
        self.stdout.write(f"Dry-run:         {'YES' if not execute else 'NO'}")

        if not execute:
            for exp in pending:
                self.stdout.write(f"  {exp.id} — user {exp.subject_user_id}")
            self.stdout.write(self.style.WARNING("Use --execute to process."))
            return

        export_root = Path(getattr(settings, "DATA_EXPORT_ROOT", "exports"))
        export_root.mkdir(parents=True, exist_ok=True)

        for exp in pending:
            self.stdout.write(f"Processing: {exp.id}")
            exp.status = ExportStatus.PROCESSING
            exp.started_at = timezone.now()
            exp.save(update_fields=["status", "started_at"])

            try:
                self._build_export(exp, export_root)
                exp.status = ExportStatus.COMPLETED
                exp.completed_at = timezone.now()
                exp.expires_at = timezone.now() + timedelta(
                    days=getattr(settings, "DATA_EXPORT_EXPIRY_DAYS", 7)
                )
                exp.save(update_fields=["status", "completed_at", "expires_at",
                                         "storage_key", "checksum", "size_bytes"])
                self.stdout.write(self.style.SUCCESS(f"  Completed: {exp.id}"))
            except Exception as e:
                exp.status = ExportStatus.FAILED
                exp.failure_code = str(e)[:100]
                exp.save(update_fields=["status", "failure_code"])
                self.stdout.write(self.style.ERROR(f"  Failed: {exp.id} — {e}"))

    def _build_export(self, exp, export_root: Path):
        """Build ZIP archive with user data."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.get(id=exp.subject_user_id)

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            # Account profile
            profile = {
                "id": str(user.id),
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "phone_number": user.phone_number,
                "role": user.role,
                "is_active": user.is_active,
                "date_joined": user.date_joined.isoformat() if user.date_joined else "",
            }
            zf.writestr("account.json", json.dumps(profile, indent=2))

            # Patient profile
            if hasattr(user, "patient_profile") and user.patient_profile:
                pp = {
                    "date_of_birth": str(user.patient_profile.date_of_birth) if user.patient_profile.date_of_birth else "",
                }
                zf.writestr("patient_profile.json", json.dumps(pp, indent=2))

            # Consultations (metadata only)
            from apps.consultations.models import Consultation
            consultations = []
            for c in Consultation.objects.filter(patient=user):
                consultations.append({
                    "id": str(c.id),
                    "status": c.status,
                    "priority": c.priority,
                    "created_at": c.created_at.isoformat() if c.created_at else "",
                    "doctor_name": c.doctor.full_name if c.doctor else "",
                    "specialty": c.specialty.name if c.specialty else "",
                })
            zf.writestr("consultations.json", json.dumps(consultations, indent=2))

            # Messages (metadata + content the user sent/received)
            from apps.messaging.models import Message
            msgs = []
            for m in Message.objects.filter(consultation__patient=user):
                msgs.append({
                    "id": str(m.id),
                    "consultation_id": str(m.consultation_id),
                    "sender_id": str(m.sender_id),
                    "content": m.content,
                    "created_at": m.created_at.isoformat() if m.created_at else "",
                })
            zf.writestr("messages.json", json.dumps(msgs, indent=2))

            # Notifications
            from apps.notifications.models import Notification
            notifs = []
            for n in Notification.objects.filter(recipient=user):
                notifs.append({
                    "id": str(n.id),
                    "notification_type": n.notification_type,
                    "title": n.title,
                    "created_at": n.created_at.isoformat() if n.created_at else "",
                })
            zf.writestr("notifications.json", json.dumps(notifs, indent=2))

            # Attachments metadata
            from apps.attachments.models import ConsultationAttachment
            atts = []
            for a in ConsultationAttachment.objects.filter(uploaded_by=user):
                atts.append({
                    "id": str(a.id),
                    "consultation_id": str(a.consultation_id),
                    "category": a.category,
                    "filename": a.filename,
                    "size": a.size,
                    "created_at": a.created_at.isoformat() if a.created_at else "",
                })
                # Include file content if available
                if a.status == "available":
                    try:
                        from apps.attachments.services.factory import get_storage_backend
                        backend = get_storage_backend()
                        f = backend.open(a.storage_key)
                        if f:
                            zf.writestr(f"attachments/{a.id}_{a.filename}", f.read())
                            f.close()
                    except Exception:
                        pass
            zf.writestr("attachments.json", json.dumps(atts, indent=2))

            # Sanitized audit records
            from apps.attachments.models import AttachmentAuditEvent
            audits = []
            for ae in AttachmentAuditEvent.objects.filter(actor=user):
                audits.append({
                    "id": str(ae.id),
                    "event_type": ae.event_type,
                    "timestamp": ae.created_at.isoformat() if ae.created_at else "",
                })
            zf.writestr("audit_log.json", json.dumps(audits, indent=2))

        # Store through attachment backend for protected download
        import hashlib
        content = buffer.getvalue()
        checksum = hashlib.sha256(content).hexdigest()

        # Write to local export directory
        safe_name = f"export_{exp.id}.zip"
        local_path = export_root / safe_name
        with open(local_path, "wb") as f:
            f.write(content)

        exp.storage_provider = "local"
        exp.storage_key = str(local_path)
        exp.checksum = checksum
        exp.size_bytes = len(content)
