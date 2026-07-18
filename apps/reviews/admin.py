from django.contrib import admin

from apps.reviews.models import ConsultationReview, DoctorReviewResponse, ReviewReport


@admin.register(ConsultationReview)
class ConsultationReviewAdmin(admin.ModelAdmin):
    list_display = ["id", "consultation", "rating", "status", "has_response", "created_at"]
    list_filter = ["status", "rating", "has_response", "created_at"]
    search_fields = ["title", "body"]
    readonly_fields = ["edit_count", "last_edited_at", "created_at", "updated_at"]


@admin.register(DoctorReviewResponse)
class DoctorReviewResponseAdmin(admin.ModelAdmin):
    list_display = ["id", "review", "doctor", "created_at"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(ReviewReport)
class ReviewReportAdmin(admin.ModelAdmin):
    list_display = ["id", "review", "reporter", "reason", "resolved_at", "created_at"]
    list_filter = ["reason", "resolved_at"]
    readonly_fields = ["created_at", "updated_at"]
