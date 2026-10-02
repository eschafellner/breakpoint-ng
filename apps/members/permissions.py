from apps.accounts.permissions import is_member, is_club_admin

def can_view_member_directory(user) -> bool:
    """M-12a: Only active members may see other members' contact details."""
    return is_member(user)

def can_manage_members(user) -> bool:
    """Only administrators may review applications or import CSV."""
    return is_club_admin(user)
