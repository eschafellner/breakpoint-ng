# Generated for PWA offline capability

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="clubsettings",
            name="offline_emergency_info",
            field=models.TextField(
                blank=True,
                default=(
                    "Die Tennisanlage ist für Mitglieder regulär zugänglich. "
                    "Bei unklarer Witterung, Platzsperren oder Notfällen wende dich bitte "
                    "direkt an die Platzverwaltung oder den Vorstand."
                ),
                help_text=(
                    "Wird auf der Offline-Notfallseite der PWA angezeigt, "
                    "wenn keine Internetverbindung besteht."
                ),
                verbose_name="Notfall- & Offline-Hinweise",
            ),
        ),
    ]
