import secrets
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError


class UserManager(BaseUserManager):
    """Manager for custom user where email is the unique identifier for auth."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_("Eine E-Mail-Adresse muss angegeben werden."))
        email = self.normalize_email(email.strip()).lower()
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("account_type", User.AccountType.MEMBER)
        extra_fields.setdefault("email_verified", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser muss is_staff=True haben."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser muss is_superuser=True haben."))

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Custom User model with email as username and tennis-specific fields."""

    class AccountType(models.TextChoices):
        GUEST = "GUEST", _("Gast")
        MEMBER = "MEMBER", _("Mitglied")

    username = None  # Using email instead
    email = models.EmailField(_("E-Mail-Adresse"), unique=True)

    phone = models.CharField(_("Telefonnummer"), max_length=50, blank=True)
    birth_date = models.DateField(_("Geburtsdatum"), null=True, blank=True)

    address_street = models.CharField(_("Straße & Hausnr."), max_length=150, blank=True)
    address_zip = models.CharField(_("PLZ"), max_length=20, blank=True)
    address_city = models.CharField(_("Ort"), max_length=100, blank=True)

    avatar = models.ImageField(
        _("Profilbild"), upload_to="avatars/", null=True, blank=True
    )

    account_type = models.CharField(
        _("Kontotyp"),
        max_length=20,
        choices=AccountType.choices,
        default=AccountType.GUEST,
    )

    email_verified = models.BooleanField(_("E-Mail bestätigt"), default=False)
    email_verification_token = models.CharField(
        _("Verifizierungs-Token"),
        max_length=64,
        blank=True,
    )

    consent_privacy_at = models.DateTimeField(
        _("Datenschutzeinwilligung erteilt am"),
        null=True,
        blank=True,
    )

    # Security & Rate limiting
    failed_login_attempts = models.PositiveIntegerField(
        _("Fehlgeschlagene Login-Versuche"),
        default=0,
    )
    locked_until = models.DateTimeField(
        _("Gesperrt bis"),
        null=True,
        blank=True,
    )
    last_failed_login_at = models.DateTimeField(null=True, blank=True, editable=False)
    failed_login_window_started_at = models.DateTimeField(
        null=True, blank=True, editable=False
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UserManager()

    class Meta:
        verbose_name = _("Benutzer")
        verbose_name_plural = _("Benutzer")
        ordering = ["last_name", "first_name", "email"]
        constraints = [
            models.UniqueConstraint(
                Lower("email"), name="accounts_user_email_ci_unique"
            )
        ]

    def __str__(self):
        full_name = self.get_full_name()
        return full_name if full_name else self.email

    @property
    def is_member(self) -> bool:
        """Check whether user has active member account type."""
        from .permissions import is_member

        return is_member(self)

    @property
    def is_guest(self) -> bool:
        """Check whether user is guest account type."""
        return self.account_type == self.AccountType.GUEST

    @property
    def is_locked(self) -> bool:
        """Check if account is temporarily locked due to failed attempts."""
        if self.locked_until and self.locked_until > timezone.now():
            return True
        return False

    def generate_verification_token(self) -> str:
        """Create a secure hex token for email verification."""
        token = secrets.token_urlsafe(32)
        self.email_verification_token = token
        self.save(update_fields=["email_verification_token"])
        return token

    def get_initials(self) -> str:
        """Returns initials for avatar display, e.g. ES."""
        first = self.first_name[:1].upper() if self.first_name else ""
        last = self.last_name[:1].upper() if self.last_name else ""
        if not first and not last:
            return self.email[:2].upper()
        return f"{first}{last}"

    def clean(self):
        super().clean()
        self.email = self.email.strip().lower()
        if self.birth_date and self.birth_date > timezone.localdate():
            raise ValidationError(
                {"birth_date": _("Das Geburtsdatum darf nicht in der Zukunft liegen.")}
            )
