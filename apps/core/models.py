from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

class TimeStampedModel(models.Model):
    """Abstract base model with created and updated timestamps."""
    created_at = models.DateTimeField(_("Erstellt am"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Aktualisiert am"), auto_now=True)

    class Meta:
        abstract = True

class ClubSettings(models.Model):
    """Singleton model holding global club settings, banking info, and booking rules."""
    name = models.CharField(_("Vereinsname"), max_length=150, default="TC Musterdorf")
    short_name = models.CharField(_("Kürzel"), max_length=20, default="TCM")
    tagline = models.CharField(_("Slogan"), max_length=255, default="Spiel, Satz und Verein.")
    logo = models.ImageField(_("Logo"), upload_to="club/", blank=True, null=True)

    # Contact
    email = models.EmailField(_("Kontakt E-Mail"), default="kontakt@tc-musterdorf.at")
    phone = models.CharField(_("Telefon"), max_length=50, blank=True, default="+43 123 456789")
    address = models.TextField(_("Adresse"), default="Tennisweg 1, 1234 Musterdorf")

    # Bank Details (for wire transfer in billing & bookings)
    bank_name = models.CharField(_("Bankname"), max_length=100, default="Musterbank")
    iban = models.CharField(_("IBAN"), max_length=34, default="AT000000000000000000")
    bic = models.CharField(_("BIC"), max_length=11, default="MUSTAT2X")
    payment_reference_prefix = models.CharField(_("Zahlungsreferenz-Präfix"), max_length=20, default="TCM-")

    # Legal Texts
    imprint_text = models.TextField(
        _("Impressum (HTML/Text)"),
        default="<h2>TC Musterdorf</h2><p>ZVR-Zahl: 123456789</p><p>Vertreten durch den Vorstand.</p>",
    )
    privacy_text = models.TextField(
        _("Datenschutzerklärung (HTML/Text)"),
        default="<h2>Datenschutzerklärung</h2><p>Wir verarbeiten personenbezogene Daten nach DSGVO Art. 6.</p>",
    )

    # Booking Rules (P-6)
    advance_days_member = models.PositiveIntegerField(_("Max. Vorlauf Mitglieder (Tage)"), default=7)
    advance_days_guest = models.PositiveIntegerField(_("Max. Vorlauf Gäste (Tage)"), default=2)
    max_open_bookings = models.PositiveIntegerField(_("Max. offene Buchungen pro Mitglied"), default=2)
    max_duration_minutes = models.PositiveIntegerField(_("Max. Dauer pro Buchung (Min.)"), default=120)
    free_cancel_hours = models.PositiveIntegerField(_("Kostenlose Stornierung bis X Std. vorher"), default=4)

    # Billing Rules (M-9)
    prorated_membership_fees = models.BooleanField(
        _("Anteilige Beitragsberechnung bei unterjährigem Eintritt"),
        default=True,
    )

    class Meta:
        verbose_name = _("Vereinseinstellungen")
        verbose_name_plural = _("Vereinseinstellungen")

    def __str__(self):
        return f"{self.name} ({self.short_name})"

    @classmethod
    def get_settings(cls):
        """Fetch the singleton instance or create default if not existing."""
        settings_obj = cls.objects.first()
        if not settings_obj:
            settings_obj = cls.objects.create()
        return settings_obj

    def save(self, *args, **kwargs):
        """Ensure singleton in DB: only one row exists."""
        if not self.pk and ClubSettings.objects.exists():
            self.pk = ClubSettings.objects.first().pk
        super().save(*args, **kwargs)

class AuditLog(models.Model):
    """Audit log for security-relevant events and data changes."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        verbose_name=_("Benutzer"),
    )
    action = models.CharField(_("Aktion"), max_length=50)
    entity_type = models.CharField(_("Entitätstyp"), max_length=50)
    entity_id = models.CharField(_("Entitäts-ID"), max_length=100)
    changes = models.JSONField(_("Änderungen / Details"), default=dict, blank=True)
    ip_address = models.GenericIPAddressField(_("IP-Adresse"), null=True, blank=True)
    created_at = models.DateTimeField(_("Zeitstempel"), auto_now_add=True)

    class Meta:
        verbose_name = _("Änderungsprotokoll")
        verbose_name_plural = _("Änderungsprotokolle")
        ordering = ["-created_at"]

    def __str__(self):
        user_display = self.user.email if self.user else "System"
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {user_display}: {self.action} on {self.entity_type}#{self.entity_id}"
