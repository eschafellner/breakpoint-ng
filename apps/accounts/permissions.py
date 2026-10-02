from django.contrib.auth.models import Group
from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.exceptions import PermissionDenied

ROLE_REDAKTEUR = "Redakteur"
ROLE_PLATZWART = "Platzwart"
ROLE_KASSIER = "Kassier"
ROLE_TURNIERLEITER = "Turnierleiter"
ROLE_ADMINISTRATOR = "Administrator"

ALL_ROLES = [
    ROLE_REDAKTEUR,
    ROLE_PLATZWART,
    ROLE_KASSIER,
    ROLE_TURNIERLEITER,
    ROLE_ADMINISTRATOR,
]

def user_in_group(user, group_name: str) -> bool:
    """Check if user belongs to the given group or is superuser."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=group_name).exists()

def is_member(user) -> bool:
    """Active member check."""
    return bool(user and user.is_authenticated and user.account_type == "MEMBER")

def is_editor(user) -> bool:
    """Redakteur check."""
    return user_in_group(user, ROLE_REDAKTEUR) or user_in_group(user, ROLE_ADMINISTRATOR)

def is_court_manager(user) -> bool:
    """Platzwart check."""
    return user_in_group(user, ROLE_PLATZWART) or user_in_group(user, ROLE_ADMINISTRATOR)

def is_cashier(user) -> bool:
    """Kassier check."""
    return user_in_group(user, ROLE_KASSIER) or user_in_group(user, ROLE_ADMINISTRATOR)

def is_tournament_director(user) -> bool:
    """Turnierleiter check."""
    return user_in_group(user, ROLE_TURNIERLEITER) or user_in_group(user, ROLE_ADMINISTRATOR)

def is_club_admin(user) -> bool:
    """Club Admin check."""
    return user_in_group(user, ROLE_ADMINISTRATOR)

class MemberRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return is_member(self.request.user)

class EditorRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return is_editor(self.request.user)

class CashierRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return is_cashier(self.request.user)

class CourtManagerRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return is_court_manager(self.request.user)

class TournamentDirectorRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return is_tournament_director(self.request.user)

class ClubAdminRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return is_club_admin(self.request.user)
