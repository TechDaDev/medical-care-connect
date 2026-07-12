from django.contrib import admin

from apps.specialties.models import Specialty


@admin.register(Specialty)
class SpecialtyAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "display_order", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    ordering = ("display_order", "name")
    prepopulated_fields = {"slug": ("name",)}
