from django.core.management.base import BaseCommand
from django.db import transaction
from apps.members.models import MembershipApplication


class Command(BaseCommand):
    help = "SEPA-Daten mit dem aktuellen SECRET_KEY neu verschlüsseln; alte Schlüssel müssen als Fallback konfiguriert sein."

    @transaction.atomic
    def handle(self, *args, **options):
        count = 0
        for application in MembershipApplication.objects.select_for_update().all():
            if application.sepa_iban:
                application.save(update_fields=["sepa_iban"])
                count += 1
        self.stdout.write(
            self.style.SUCCESS(f"{count} SEPA-Datensätze neu verschlüsselt.")
        )
