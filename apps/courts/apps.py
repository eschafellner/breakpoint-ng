from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

class CourtsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.courts"
    verbose_name = _("Platzverwaltung & Buchungssystem")
