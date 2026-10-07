from decimal import Decimal
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from apps.core.models import TimeStampedModel


class Charge(TimeStampedModel):
    class Kind(models.TextChoices):
        MEMBERSHIP_FEE = "MEMBERSHIP_FEE", _("Mitgliedsbeitrag")
        COURT_FEE = "COURT_FEE", _("Platzgebühr")
        GUEST_FEE = "GUEST_FEE", _("Gastgebühr")
        TOURNAMENT_FEE = "TOURNAMENT_FEE", _("Turnier-Startgebühr")
        OTHER = "OTHER", _("Sonstige Gebühr")

    class Status(models.TextChoices):
        OPEN = "OPEN", _("Offen")
        PARTIAL = "PARTIAL", _("Teilweise bezahlt")
        PAID = "PAID", _("Bezahlt")
        WAIVED = "WAIVED", _("Erlassen")
        CANCELLED = "CANCELLED", _("Storniert")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="charges",
        verbose_name=_("Benutzer"),
    )
    kind = models.CharField(
        _("Art"),
        max_length=30,
        choices=Kind.choices,
        default=Kind.OTHER,
    )
    amount = models.DecimalField(
        _("Gesamtbetrag (€)"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    due_date = models.DateField(_("Fälligkeitsdatum"))
    period_start = models.DateField(_("Periode von"), null=True, blank=True)
    period_end = models.DateField(_("Periode bis"), null=True, blank=True)

    status = models.CharField(
        _("Zahlungsstatus"),
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )
    description = models.CharField(_("Verwendungszweck / Beschreibung"), max_length=255)

    # Generic FK to the originating entity (e.g. Booking, Entry, Membership)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    source = GenericForeignKey("content_type", "object_id")

    dunning_level = models.PositiveIntegerField(_("Mahnstufe"), default=0)

    class Meta:
        verbose_name = _("Forderung")
        verbose_name_plural = _("Forderungen")
        ordering = ["-due_date", "-id"]

    def __str__(self):
        return f"#{self.pk} - {self.user} - {self.get_kind_display()} ({self.amount} €) [{self.get_status_display()}]"

    @property
    def total_paid(self) -> Decimal:
        """Sum of all recorded payments."""
        if hasattr(self, "_payment_total"):
            return self._payment_total
        prefetched = getattr(self, "_prefetched_objects_cache", {})
        if "payments" in prefetched:
            return sum((payment.amount for payment in prefetched["payments"]), Decimal("0.00"))
        agg = self.payments.aggregate(total=models.Sum("amount"))["total"]
        return agg or Decimal("0.00")

    @property
    def open_amount(self) -> Decimal:
        """Remaining balance."""
        if self.status in [self.Status.PAID, self.Status.WAIVED, self.Status.CANCELLED]:
            return Decimal("0.00")
        diff = self.amount - self.total_paid
        return max(diff, Decimal("0.00"))


class Payment(TimeStampedModel):
    class Method(models.TextChoices):
        TRANSFER = "TRANSFER", _("Überweisung")
        SEPA = "SEPA", _("SEPA-Lastschrift")
        CASH = "CASH", _("Barzahlung")

    charge = models.ForeignKey(
        Charge,
        on_delete=models.PROTECT,
        related_name="payments",
        verbose_name=_("Forderung"),
    )
    amount = models.DecimalField(_("Zahlbetrag (€)"), max_digits=10, decimal_places=2)
    paid_at = models.DateTimeField(_("Bezahlt am"), default=timezone.now)
    method = models.CharField(
        _("Zahlungsmethode"),
        max_length=20,
        choices=Method.choices,
        default=Method.TRANSFER,
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_payments",
        verbose_name=_("Erfasst von"),
    )
    reference = models.CharField(
        _("Zahlungsreferenz / Belegnummer"), max_length=100, blank=True
    )

    class Meta:
        verbose_name = _("Zahlung")
        verbose_name_plural = _("Zahlungen")
        ordering = ["-paid_at"]

    def __str__(self):
        return f"{self.amount} € ({self.get_method_display()}) für #{self.charge_id}"


class PriceRule(TimeStampedModel):
    class AppliesTo(models.TextChoices):
        MEMBER = "MEMBER", _("Mitglied")
        GUEST = "GUEST", _("Gast")
        GUEST_OF_MEMBER = "GUEST_OF_MEMBER", _("Gast eines Mitglieds")

    court = models.ForeignKey(
        "courts.Court",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="price_rules",
        verbose_name=_("Platz (leer = alle Plätze)"),
    )
    applies_to = models.CharField(
        _("Gilt für"),
        max_length=30,
        choices=AppliesTo.choices,
        default=AppliesTo.GUEST,
    )
    weekday_mask = models.CharField(
        _("Wochentage-Maske (Mo-So: 1111111)"),
        max_length=7,
        default="1111111",
    )
    time_from = models.TimeField(_("Gültig ab Uhrzeit"), null=True, blank=True)
    time_to = models.TimeField(_("Gültig bis Uhrzeit"), null=True, blank=True)
    season = models.ForeignKey(
        "courts.Season",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="price_rules",
        verbose_name=_("Saison (optional)"),
    )
    price_per_hour = models.DecimalField(
        _("Preis pro Stunde (€)"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    price_per_person = models.DecimalField(
        _("Preis pro Person/Gast (€)"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    class Meta:
        verbose_name = _("Preisregel")
        verbose_name_plural = _("Preisregeln")

    def __str__(self):
        court_label = self.court.name if self.court else "Alle Plätze"
        return f"{court_label} - {self.get_applies_to_display()}: {self.price_per_hour} €/h | {self.price_per_person} €/Person"

    def clean(self):
        if len(self.weekday_mask) != 7 or set(self.weekday_mask) - {"0", "1"}:
            raise ValidationError(
                {
                    "weekday_mask": _(
                        "Die Wochentagsmaske muss sieben Nullen oder Einsen enthalten."
                    )
                }
            )
        if self.time_from and self.time_to and self.time_from >= self.time_to:
            raise ValidationError(
                {"time_to": _("Das Tarifende muss nach dem Beginn liegen.")}
            )
        for field in ("price_per_hour", "price_per_person"):
            value = getattr(self, field)
            if value is not None and Decimal(value) < 0:
                raise ValidationError({field: _("Preise dürfen nicht negativ sein.")})


class BookingExtra(TimeStampedModel):
    class Unit(models.TextChoices):
        PER_HOUR = "PER_HOUR", _("Pro Stunde")
        PER_BOOKING = "PER_BOOKING", _("Pro Buchung")

    class Mode(models.TextChoices):
        AUTOMATIC = "AUTOMATIC", _("Automatisch (z.B. Halle)")
        OPTIONAL = "OPTIONAL", _("Optional wählbar (z.B. Flutlicht)")

    name = models.CharField(_("Bezeichnung"), max_length=100)
    price_member = models.DecimalField(
        _("Preis für Mitglieder (€)"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    price_guest = models.DecimalField(
        _("Preis für Gäste (€)"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    unit = models.CharField(
        _("Abrechnungseinheit"),
        max_length=20,
        choices=Unit.choices,
        default=Unit.PER_HOUR,
    )
    courts = models.ManyToManyField(
        "courts.Court",
        blank=True,
        related_name="extras",
        verbose_name=_("Gültig für Plätze (leer = alle)"),
    )
    mode = models.CharField(
        _("Modus"),
        max_length=20,
        choices=Mode.choices,
        default=Mode.OPTIONAL,
    )
    is_active = models.BooleanField(_("Aktiv"), default=True)

    class Meta:
        verbose_name = _("Buchungs-Extra")
        verbose_name_plural = _("Buchungs-Extras")

    def __str__(self):
        return f"{self.name} ({self.get_mode_display()}) – M: {self.price_member} €, G: {self.price_guest} €"

    def clean(self):
        for field in ("price_member", "price_guest"):
            value = getattr(self, field)
            if value is not None and Decimal(value) < 0:
                raise ValidationError({field: _("Preise dürfen nicht negativ sein.")})


class BookingExtraLine(TimeStampedModel):
    booking = models.ForeignKey(
        "courts.Booking",
        on_delete=models.CASCADE,
        related_name="extra_lines",
        verbose_name=_("Buchung"),
    )
    extra = models.ForeignKey(
        BookingExtra,
        on_delete=models.PROTECT,
        verbose_name=_("Extra"),
    )
    quantity = models.DecimalField(
        _("Menge"), max_digits=6, decimal_places=2, default=Decimal("1.00")
    )
    unit_price = models.DecimalField(
        _("Einzelpreis (€) [eingefroren]"), max_digits=10, decimal_places=2
    )
    total = models.DecimalField(_("Gesamtbetrag (€)"), max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = _("Buchungs-Extra-Posten")
        verbose_name_plural = _("Buchungs-Extra-Posten")

    def __str__(self):
        return f"{self.extra.name} x {self.quantity} = {self.total} € (Buchung #{self.booking_id})"
