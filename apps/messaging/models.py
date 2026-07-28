from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class MessageType(models.TextChoices):
    TEXT = "text", _("Text")
    SYSTEM = "system", _("System")


class ConsultationMessage(BaseModel):
    """A message sent within a consultation thread."""

    consultation = models.ForeignKey(
        "consultations.Consultation",
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name=_("consultation"),
    )
    sender = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_messages",
        verbose_name=_("sender"),
    )
    message_type = models.CharField(
        _("message type"),
        max_length=10,
        choices=MessageType.choices,
        default=MessageType.TEXT,
    )
    content = models.TextField(_("content"), max_length=5000)
    is_system_message = models.BooleanField(_("is system message"), default=False)
    sent_at = models.DateTimeField(_("sent at"), auto_now_add=True, db_index=True)
    edited_at = models.DateTimeField(_("edited at"), null=True, blank=True)
    client_request_id = models.UUIDField(
        _("client request ID"), null=True, blank=True
    )

    class Meta:
        verbose_name = _("consultation message")
        verbose_name_plural = _("consultation messages")
        ordering = ["sent_at"]
        indexes = [
            models.Index(fields=["consultation", "sent_at"]),
            models.Index(fields=["sender", "sent_at"]),
            models.Index(fields=["message_type"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["sender", "client_request_id"],
                name="message_unique_sender_request_id",
            ),
        ]

    def __str__(self) -> str:
        sender_str = self.sender.email if self.sender else "System"
        return f"Message by {sender_str} on {self.sent_at:%Y-%m-%d %H:%M}"


class MessageReadReceipt(BaseModel):
    """Tracks when a user read a message."""

    message = models.ForeignKey(
        ConsultationMessage,
        on_delete=models.CASCADE,
        related_name="read_receipts",
        verbose_name=_("message"),
    )
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="message_read_receipts",
        verbose_name=_("user"),
    )
    read_at = models.DateTimeField(_("read at"), auto_now_add=True)

    class Meta:
        verbose_name = _("message read receipt")
        verbose_name_plural = _("message read receipts")
        unique_together = [["message", "user"]]

    def __str__(self) -> str:
        return f"{self.user.email} read {self.message.id} at {self.read_at:%H:%M}"


class DoctorInternalNote(BaseModel):
    """An internal doctor note attached to a consultation (not patient-visible)."""

    consultation = models.ForeignKey(
        "consultations.Consultation",
        on_delete=models.CASCADE,
        related_name="internal_notes",
        verbose_name=_("consultation"),
    )
    author = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="internal_notes",
        verbose_name=_("author"),
    )
    content = models.TextField(_("content"), max_length=5000)

    class Meta:
        verbose_name = _("doctor internal note")
        verbose_name_plural = _("doctor internal notes")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["consultation"]),
            models.Index(fields=["author"]),
        ]

    def __str__(self) -> str:
        return f"Internal note by {self.author.email} on {self.created_at:%Y-%m-%d}"
