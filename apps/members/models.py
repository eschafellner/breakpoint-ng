from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from apps.core.models import TimeStampedModel
from apps.core.fields import EncryptedCharField


class MembershipType(TimeStampedModel):
    class BillingInterval(models.TextChoices):
        YEARLY = "YEARLY", _("Jährlich")
        MONTHLY = "MONTHLY", _("Monatlich")

    name = models.CharField(_("Bezeichnung"), max_length=100)
    fee_amount = models.DecimalField(
        _("Beitrag (€)"), max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    billing_interval = models.CharField(
        _("Abrechnungsintervall"),
        max_length=20,
        choices=BillingInterval.choices,
        default=BillingInterval.YEARLY,
    )
    min_age = models.PositiveIntegerField(_("Mindestalter"), null=True, blank=True)
    max_age = models.PositiveIntegerField(_("Höchstalter"), null=True, blank=True)
    is_active = models.BooleanField(_("Aktiv"), default=True)

    class Meta:
        verbose_name = _("Mitgliedschaftsart")
        verbose_name_plural = _("Mitgliedschaftsarten")
        ordering = ["name"]

    def __str__(self):
        return (
            f"{self.name} ({self.fee_amount} € / {self.get_billing_interval_display()})"
        )

    def clean(self):
        if self.fee_amount is not None and Decimal(self.fee_amount) < 0:
            raise ValidationError(
                {"fee_amount": _("Der Beitrag darf nicht negativ sein.")}
            )
        if (
            self.min_age is not None
            and self.max_age is not None
            and self.min_age > self.max_age
        ):
            raise ValidationError(
                {
                    "max_age": _(
                        "Das Höchstalter muss mindestens dem Mindestalter entsprechen."
                    )
                }
            )


class MembershipApplication(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", _("Ausstehend")
        APPROVED = "APPROVED", _("Genehmigt")
        REJECTED = "REJECTED", _("Abgelehnt")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="membership_applications",
        verbose_name=_("Antragsteller"),
    )
    requested_type = models.ForeignKey(
        MembershipType,
        on_delete=models.PROTECT,
        verbose_name=_("Gewünschte Mitgliedschaftsart"),
    )
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_applications",
        verbose_name=_("Geprüft von"),
    )
    reviewed_at = models.DateTimeField(_("Geprüft am"), null=True, blank=True)
    rejection_reason = models.TextField(_("Ablehnungsgrund"), blank=True)
    sepa_iban = EncryptedCharField(_("SEPA IBAN"), max_length=255, blank=True)
    sepa_mandate_date = models.DateField(_("SEPA Mandatsdatum"), null=True, blank=True)

    class Meta:
        verbose_name = _("Mitgliedsantrag")
        verbose_name_plural = _("Mitgliedsanträge")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Antrag #{self.pk}: {self.user} ({self.requested_type.name}) - {self.get_status_display()}"


class Membership(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", _("Aktiv")
        PAUSED = "PAUSED", _("Pausiert")
        ENDED = "ENDED", _("Beendet")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name=_("Mitglied"),
    )
    type = models.ForeignKey(
        MembershipType,
        on_delete=models.PROTECT,
        verbose_name=_("Mitgliedschaftsart"),
    )
    member_number = models.CharField(_("Mitgliedsnummer"), max_length=30, unique=True)
    start_date = models.DateField(_("Beginn"))
    end_date = models.DateField(_("Enddatum"), null=True, blank=True)
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    class Meta:
        verbose_name = _("Mitgliedschaft")
        verbose_name_plural = _("Mitgliedschaften")
        ordering = ["member_number"]

    def __str__(self):
        return f"{self.member_number} - {self.user.get_full_name()} ({self.type.name})"

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError(
                {"end_date": _("Das Enddatum muss nach dem Beginn liegen.")}
            )
