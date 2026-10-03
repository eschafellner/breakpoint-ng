from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    verbose_name = _("Benutzerverwaltung & Authentifizierung")

    def ready(self):
        from django.db.models.signals import post_migrate
        from .signals import sync_role_permissions

        post_migrate.connect(
            sync_role_permissions, dispatch_uid="breakpoint.sync_role_permissions"
        )
