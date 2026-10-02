from django.db import migrations

def create_standard_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    roles = ["Redakteur", "Platzwart", "Kassier", "Turnierleiter", "Administrator"]
    for role in roles:
        Group.objects.get_or_create(name=role)

def remove_standard_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    roles = ["Redakteur", "Platzwart", "Kassier", "Turnierleiter", "Administrator"]
    Group.objects.filter(name__in=roles).delete()

class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("auth", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_standard_groups, remove_standard_groups),
    ]
