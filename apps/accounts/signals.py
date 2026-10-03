from django.contrib.auth.models import Group, Permission


def sync_role_permissions(sender, using, **kwargs):
    """Populate each role after Django has created model permissions."""
    from .permissions import ALL_ROLES

    rules = {
        "Redakteur": {"news": None},
        "Platzwart": {"courts": None},
        "Kassier": {"billing": None},
        "Turnierleiter": {"tournaments": None},
    }
    for name in ALL_ROLES:
        group, _ = Group.objects.using(using).get_or_create(name=name)
        permissions = Permission.objects.using(using).all()
        if name != "Administrator":
            permissions = permissions.filter(content_type__app_label__in=rules[name])
        group.permissions.add(*permissions)
