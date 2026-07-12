from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class Specialty(BaseModel):
    """Medical specialty that a doctor can belong to."""

    name = models.CharField(_("name"), max_length=255, unique=True)
    slug = models.SlugField(
        _("slug"), max_length=255, unique=True, blank=True,
        help_text=_("Auto-generated from name if omitted."),
    )
    description = models.TextField(_("description"), blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    display_order = models.IntegerField(_("display order"), default=0)

    class Meta:
        verbose_name = _("specialty")
        verbose_name_plural = _("specialties")
        ordering = ["display_order", "name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
