from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import TimeStampedModel


class Court(TimeStampedModel):
    class Surface(models.TextChoices):
        SAND = "SAND", _("Sandplatz")
        HARTPLATZ = "HARTPLATZ", _("Hartplatz")
        HALLE = "HALLE", _("Teppich / Halle")
        RASEN = "RASEN", _("Rasen")

    name = models.CharField(_("Platzname"), max_length=50)
    surface = models.CharField(
        _("Belag"),
        max_length=20,
        choices=Surface.choices,
        default=Surface.SAND,
    )
    is_indoor = models.BooleanField(_("Halle / Indoor"), default=False)
    has_floodlight = models.BooleanField(_("Flutlicht vorhanden"), default=False)
    is_active = models.BooleanField(_("Aktiv"), default=True)
    order = models.PositiveIntegerField(_("Reihenfolge"), default=0)

    class Meta:
        verbose_name = _("Platz")
        verbose_name_plural = _("Plätze")
        ordering = ["order", "id"]

    def __str__(self):
        type_str = _("Halle") if self.is_indoor else self.get_surface_display()
        return f"{self.name} ({type_str})"


class Season(TimeStampedModel):
    name = models.CharField(_("Saisonname"), max_length=100)
    start_date = models.DateField(_("Saisonbeginn"))
    end_date = models.DateField(_("Saisonende"))

    class Meta:
        verbose_name = _("Saison")
        verbose_name_plural = _("Saisons")
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.name} ({self.start_date:%d.%m.%Y} - {self.end_date:%d.%m.%Y})"

    def clean(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError(
                {"end_date": _("Das Saisonende muss nach dem Beginn liegen.")}
            )


class OpeningHours(TimeStampedModel):
    WEEKDAYS = (
        (0, _("Montag")),
        (1, _("Dienstag")),
        (2, _("Mittwoch")),
        (3, _("Donnerstag")),
        (4, _("Freitag")),
        (5, _("Samstag")),
        (6, _("Sonntag")),
    )

    court = models.ForeignKey(
        Court,
        on_delete=models.CASCADE,
        related_name="opening_hours",
        verbose_name=_("Platz"),
    )
    season = models.ForeignKey(
        Season,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="opening_hours",
        verbose_name=_("Saison (optional)"),
    )
    weekday = models.IntegerField(_("Wochentag"), choices=WEEKDAYS)
    open_time = models.TimeField(_("Öffnet um"))
    close_time = models.TimeField(_("Schließt um"))
    slot_minutes = models.PositiveIntegerField(_("Slot-Dauer (Minuten)"), default=60)

    class Meta:
        verbose_name = _("Öffnungszeit")
        verbose_name_plural = _("Öffnungszeiten")
        ordering = ["weekday", "open_time"]

    def __str__(self):
        return f"{self.court.name} - {self.get_weekday_display()}: {self.open_time:%H:%M} - {self.close_time:%H:%M}"

    def clean(self):
        if not self.slot_minutes or self.slot_minutes < 0:
            raise ValidationError(
                {"slot_minutes": _("Die Slot-Dauer muss größer als null sein.")}
            )
        if self.open_time and self.close_time and self.open_time >= self.close_time:
            raise ValidationError(
                {"close_time": _("Die Schließzeit muss nach der Öffnung liegen.")}
            )


class Blocking(TimeStampedModel):
    class Reason(models.TextChoices):
        TRAINING = "TRAINING", _("Training")
        TEAM_MATCH = "TEAM_MATCH", _("Mannschaftsspiel")
        TOURNAMENT = "TOURNAMENT", _("Turnier")
        MAINTENANCE = "MAINTENANCE", _("Platzpflege / Wartung")
        WEATHER = "WEATHER", _("Wetterbedingt gesperrt")

    court = models.ForeignKey(
        Court,
        on_delete=models.CASCADE,
        related_name="blockings",
        verbose_name=_("Platz"),
    )
    start = models.DateTimeField(_("Beginn"))
    end = models.DateTimeField(_("Ende"))
    reason = models.CharField(
        _("Grund"),
        max_length=20,
        choices=Reason.choices,
        default=Reason.TRAINING,
    )
    note = models.CharField(_("Bemerkung / Anmerkung"), max_length=255, blank=True)
    recurrence_rule = models.CharField(
        _("Wiederholung (z.B. WEEKLY)"),
        max_length=100,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Erstellt von"),
    )

    class Meta:
        verbose_name = _("Platzsperre")
        verbose_name_plural = _("Platzsperren")
        ordering = ["start"]

    def __str__(self):
        return f"Sperre: {self.court.name} ({self.get_reason_display()}) {self.start:%d.%m. %H:%M}–{self.end:%H:%M}"


class Booking(TimeStampedModel):
    class Status(models.TextChoices):
        CONFIRMED = "CONFIRMED", _("Bestätigt")
        CANCELLED = "CANCELLED", _("Storniert")

    court = models.ForeignKey(
        Court,
        on_delete=models.CASCADE,
        related_name="bookings",
        verbose_name=_("Platz"),
    )
    booked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="bookings",
        verbose_name=_("Gebucht von"),
    )
    start = models.DateTimeField(_("Beginn"))
    end = models.DateTimeField(_("Ende"))
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=Status.choices,
        default=Status.CONFIRMED,
    )
    cancelled_at = models.DateTimeField(_("Storniert am"), null=True, blank=True)
    reminder_sent_at = models.DateTimeField(
        _("Erinnerung versendet am"), null=True, blank=True, editable=False
    )
    total_price = models.DecimalField(
        _("Gesamtpreis (€)"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    class Meta:
        verbose_name = _("Buchung")
        verbose_name_plural = _("Buchungen")
        ordering = ["start"]

    def __str__(self):
        return f"Buchung #{self.pk}: {self.court.name} {self.start:%d.%m. %H:%M}–{self.end:%H:%M} ({self.booked_by})"

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.CONFIRMED

    @property
    def duration_minutes(self) -> int:
        return int((self.end - self.start).total_seconds() / 60)


class BookingParticipant(TimeStampedModel):
    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name="participants",
        verbose_name=_("Buchung"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="participations",
        verbose_name=_("Benutzer"),
    )
    guest_name = models.CharField(
        _("Gastname (falls kein Benutzerkonto)"), max_length=100, blank=True
    )
    is_guest = models.BooleanField(_("Ist Gast"), default=False)

    class Meta:
        verbose_name = _("Mitspieler")
        verbose_name_plural = _("Mitspieler")

    def __str__(self):
        if self.user:
            return f"{self.user.get_full_name()} ({'Gast' if self.is_guest else 'Mitglied'})"
        return f"{self.guest_name} (Gast)"
