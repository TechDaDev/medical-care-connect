from django.contrib import admin

from apps.messaging.models import ConsultationMessage, DoctorInternalNote, MessageReadReceipt


@admin.register(ConsultationMessage)
class ConsultationMessageAdmin(admin.ModelAdmin):
    list_display = ["id", "consultation", "sender", "message_type", "sent_at"]
    list_filter = ["message_type", "is_system_message", "sent_at"]
    search_fields = ["content", "sender__email", "consultation__id"]
    date_hierarchy = "sent_at"
    raw_id_fields = ["consultation", "sender"]


@admin.register(MessageReadReceipt)
class MessageReadReceiptAdmin(admin.ModelAdmin):
    list_display = ["message", "user", "read_at"]
    list_filter = ["read_at"]
    raw_id_fields = ["message", "user"]


@admin.register(DoctorInternalNote)
class DoctorInternalNoteAdmin(admin.ModelAdmin):
    list_display = ["id", "consultation", "author", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["content", "author__email"]
    raw_id_fields = ["consultation", "author"]
