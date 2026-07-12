from django.contrib import admin

from apps.ai_intake.models import AIIntakeMessage, AIIntakeSession


@admin.register(AIIntakeSession)
class AIIntakeSessionAdmin(admin.ModelAdmin):
    list_display = [
        "id", "consultation", "status", "language", "question_count",
        "emergency_level", "created_at",
    ]
    list_filter = ["status", "emergency_level", "language"]
    search_fields = ["consultation__id"]
    readonly_fields = ["created_at", "updated_at"]
    fieldsets = [
        ("Session", {"fields": ["consultation", "status", "language"]}),
        ("Progress", {"fields": [
            "current_question", "question_count",
            "collected_data", "missing_fields",
        ]}),
        ("Emergency", {"fields": [
            "emergency_detected", "emergency_level", "emergency_reasons",
        ]}),
        ("AI Provider", {"fields": [
            "ai_provider", "ai_model", "prompt_version",
            "input_tokens", "output_tokens", "total_tokens",
        ]}),
        ("Timestamps", {"fields": [
            "started_at", "completed_at", "confirmed_at",
            "last_ai_request_at",
        ]}),
        ("Errors", {"fields": ["error_code", "error_message"]}),
    ]


@admin.register(AIIntakeMessage)
class AIIntakeMessageAdmin(admin.ModelAdmin):
    list_display = ["session", "sequence_number", "role", "created_at"]
    list_filter = ["role"]
    search_fields = ["session__id", "content"]
