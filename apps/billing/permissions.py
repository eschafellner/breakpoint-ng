from apps.accounts.permissions import is_cashier, is_club_admin

def can_access_billing(user) -> bool:
    """Check if user has cashier or administrator privileges."""
    return is_cashier(user) or is_club_admin(user)
