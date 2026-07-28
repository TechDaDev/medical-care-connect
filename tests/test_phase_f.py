import os
import tempfile
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.attachments.models import ConsultationAttachment
from apps.consultations.models import Consultation
from apps.core.models import AuditEvent
from apps.privacy.models import AccountDeletionRequest


@override_settings(
    DEBUG=True,
    ATTACHMENT_STORAGE_BACKEND="local",
    ATTACHMENT_RETENTION_DAYS=90,
)
class SyntheticFixtureTests(TestCase):
    def setUp(self):
        self.storage_root = tempfile.mkdtemp()
        self.settings_override = override_settings(ATTACHMENT_LOCAL_ROOT=self.storage_root)
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()

    @patch.dict(os.environ, {"E2E_TEST_PASSWORD": "synthetic-test-only"}, clear=False)
    def test_seed_and_cleanup_are_run_scoped(self):
        call_command("seed_e2e_data", run_id="phase-f-test")
        self.assertEqual(
            User.objects.filter(email__startswith="e2e+phase-f-test+").count(), 9
        )
        self.assertEqual(
            Consultation.objects.filter(
                description__startswith="e2e-phase-f-test"
            ).count(),
            4,
        )
        self.assertEqual(
            ConsultationAttachment.objects.filter(
                storage_key__startswith="e2e-phase-f-test/"
            ).count(),
            4,
        )
        self.assertEqual(
            AccountDeletionRequest.objects.filter(
                reason__startswith="e2e-phase-f-test"
            ).count(),
            2,
        )
        self.assertTrue(
            AuditEvent.objects.filter(request_id="e2e-phase-f-test").exists()
        )

        call_command("cleanup_e2e_data", run_id="phase-f-test")
        self.assertFalse(
            User.objects.filter(email__startswith="e2e+phase-f-test+").exists()
        )
        self.assertFalse(
            ConsultationAttachment.objects.filter(
                storage_key__startswith="e2e-phase-f-test/"
            ).exists()
        )

    @override_settings(DEBUG=False)
    @patch.dict(os.environ, {"E2E_TEST_PASSWORD": "synthetic-test-only"}, clear=False)
    def test_seed_refuses_non_debug_environment(self):
        with self.assertRaises(CommandError):
            call_command("seed_e2e_data", run_id="phase-f-test")

    def test_legacy_cleanup_dry_run_does_not_print_identity(self):
        email = "synthetic-phasef@e2e.mcc.dev"
        User.objects.create_user(email=email, password="synthetic-test-only")
        output = StringIO()

        call_command("cleanup_phase11_e2e", run_id="phasef", stdout=output)

        self.assertIn("Users to delete: 1", output.getvalue())
        self.assertNotIn(email, output.getvalue())

    @override_settings(DEBUG=False)
    def test_legacy_cleanup_refuses_non_debug_environment(self):
        with self.assertRaises(CommandError):
            call_command("cleanup_phase11_e2e", run_id="phasef")
