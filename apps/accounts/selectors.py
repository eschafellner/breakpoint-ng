from typing import Optional
from .models import User

def get_user_by_email(email: str) -> Optional[User]:
    """Fetch user by case-insensitive email."""
    try:
        return User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return None

def get_active_members():
    """Return all verified active members."""
    return User.objects.filter(account_type=User.AccountType.MEMBER, is_active=True).order_by("last_name", "first_name")
