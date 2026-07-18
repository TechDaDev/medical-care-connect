from django.apps import AppConfig
from django.core.checks import Error, register
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class AttachmentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.attachments"
    verbose_name = _("Attachments")

    @staticmethod
    def check_clamav_config(app_configs, **kwargs):
        """System check: clamav mode requires CLAMAV_HOST."""
        errors = []
        scan_mode = getattr(settings, "ATTACHMENT_SCAN_MODE", "disabled")
        if scan_mode == "clamav" and not getattr(settings, "CLAMAV_HOST", None):
            errors.append(
                Error(
                    "CLAMAV_HOST must be set when ATTACHMENT_SCAN_MODE=clamav",
                    hint="Set CLAMAV_HOST environment variable or remove ATTACHMENT_SCAN_MODE.",
                    id="mcc.E001",
                )
            )
        return errors

    def ready(self):
        from django.core.checks import register as check_register
        check_register(self.check_clamav_config)
