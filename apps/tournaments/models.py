from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from apps.core.models import TimeStampedModel

class Tournament(TimeStampedModel):
    class Eligibility(models.TextChoices):
        MEMBERS_ONLY = "MEMBERS_ONLY", _("Nur Mitglieder")
        MEMBERS_AND_GUESTS = "MEMBERS_AND_GUESTS", _("Mitglieder und Gäste")

    class Status(models.TextChoices):
        DRAFT = "DRAFT", _("Entwurf")
        OPEN = "OPEN", _("Anmeldung geöffnet")
        DRAWN = "DRAWN", _("Ausgelost")
        RUNNING = "RUNNING", _("Laufend")
        FINISHED = "FINISHED", _("Abgeschlossen")

    name = models.CharField(_("Turniername"), max_length=150)
    slug = models.SlugField(_("Slug"), max_length=150, unique=True, blank=True)
    description = models.TextField(_("Beschreibung / Ausschreibung"), blank=True)
    start_date = models.DateField(_("Beginn"))
    end_date = models.DateField(_("Ende"))
    registration_deadline = models.DateTimeField(_("Anmeldeschluss"))
    eligibility = models.CharField(
        _("Teilnahmeberechtigung"),
        max_length=30,
        choices=Eligibility.choices,
        default=Eligibility.MEMBERS_ONLY,
    )
    fee_member = models.DecimalField(
        _("Startgebühr Mitglieder (€)"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("15.00"),
    )
    fee_guest = models.DecimalField(
        _("Startgebühr Gäste (€)"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("25.00"),
    )
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    class Meta:
        verbose_name = _("Turnier")
        verbose_name_plural = _("Turniere")
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.name} ({self.start_date.year})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

class Competition(TimeStampedModel):
    class Discipline(models.TextChoices):
        SINGLES = "SINGLES", _("Einzel")
        DOUBLES = "DOUBLES", _("Doppel")
        MIXED = "MIXED", _("Mixed")

    class Format(models.TextChoices):
        KNOCKOUT = "KNOCKOUT", _("K.-o.-System")
        ROUND_ROBIN = "ROUND_ROBIN", _("Jeder gegen jeden")
        GROUPS_KO = "GROUPS_KO", _("Gruppenphase + K.-o.")

    tournament = models.ForeignKey(
        Tournament,
        on_delete=models.CASCADE,
        related_name="competitions",
        verbose_name=_("Turnier"),
    )
    name = models.CharField(_("Konkurrenz"), max_length=100)
    discipline = models.CharField(
        _("Disziplin"),
        max_length=20,
        choices=Discipline.choices,
        default=Discipline.SINGLES,
    )
    format = models.CharField(
        _("Spielsystem"),
        max_length=20,
        choices=Format.choices,
        default=Format.KNOCKOUT,
    )
    max_entries = models.PositiveIntegerField(_("Max. Teilnehmer"), default=16)
    age_class = models.CharField(_("Altersklasse"), max_length=50, blank=True)

    class Meta:
        verbose_name = _("Konkurrenz")
        verbose_name_plural = _("Konkurrenzen")
        ordering = ["name"]

    def __str__(self):
        return f"{self.tournament.name} - {self.name} ({self.get_discipline_display()})"

class Entry(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING_PARTNER = "PENDING_PARTNER", _("Wartet auf Partnerbestätigung")
        CONFIRMED = "CONFIRMED", _("Bestätigt")
        WAITLIST = "WAITLIST", _("Warteliste")
        WITHDRAWN = "WITHDRAWN", _("Zurückgezogen")

    competition = models.ForeignKey(
        Competition,
        on_delete=models.CASCADE,
        related_name="entries",
        verbose_name=_("Konkurrenz"),
    )
    player1 = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tournament_entries_p1",
        verbose_name=_("Spieler 1"),
    )
    player2 = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="tournament_entries_p2",
        verbose_name=_("Spieler 2 (Partner)"),
    )
    seed = models.PositiveIntegerField(_("Gesetzt (1, 2, ...)"), null=True, blank=True)
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=Status.choices,
        default=Status.CONFIRMED,
    )

    class Meta:
        verbose_name = _("Turnieranmeldung")
        verbose_name_plural = _("Turnieranmeldungen")
        ordering = ["competition", "seed", "created_at"]

    def __str__(self):
        if self.player2:
            return f"{self.player1.get_full_name()} / {self.player2.get_full_name()}"
        return self.player1.get_full_name()

    @property
    def display_name(self) -> str:
        if self.player2:
            return f"{self.player1.last_name} / {self.player2.last_name}"
        return f"{self.player1.last_name} {self.player1.first_name[:1]}."

class Match(TimeStampedModel):
    class ResultType(models.TextChoices):
        NORMAL = "NORMAL", _("Regulär beendet")
        RETIRED = "RETIRED", _("Aufgabe (w.o. / ret.)")
        WALKOVER = "WALKOVER", _("Nicht angetreten (w.o.)")

    competition = models.ForeignKey(
        Competition,
        on_delete=models.CASCADE,
        related_name="matches",
        verbose_name=_("Konkurrenz"),
    )
    round = models.PositiveIntegerField(_("Runde"), default=1)
    position = models.PositiveIntegerField(_("Position im Raster"), default=1)
    
    entry_a = models.ForeignKey(
        Entry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="matches_as_a",
        verbose_name=_("Spieler / Paar A"),
    )
    entry_b = models.ForeignKey(
        Entry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="matches_as_b",
        verbose_name=_("Spieler / Paar B"),
    )
    winner = models.ForeignKey(
        Entry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="matches_won",
        verbose_name=_("Sieger"),
    )
    score = models.JSONField(_("Ergebnis (Satzliste)"), default=list, blank=True)
    result_type = models.CharField(
        _("Ergebnistyp"),
        max_length=20,
        choices=ResultType.choices,
        default=ResultType.NORMAL,
    )

    scheduled_court = models.ForeignKey(
        "courts.Court",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Angesetzter Platz"),
    )
    scheduled_start = models.DateTimeField(_("Spieltermin"), null=True, blank=True)
    blocking = models.ForeignKey(
        "courts.Blocking",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Zugehörige Platzsperre"),
    )
    next_match = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prev_matches",
        verbose_name=_("Nächstes Spiel im K.-o.-Baum"),
    )

    class Meta:
        verbose_name = _("Match / Spiel")
        verbose_name_plural = _("Matches")
        ordering = ["competition", "round", "position"]

    def __str__(self):
        a_str = self.entry_a.display_name if self.entry_a else "TBD"
        b_str = self.entry_b.display_name if self.entry_b else "TBD"
        return f"R{self.round} #{self.position}: {a_str} vs {b_str}"

    @property
    def score_display(self) -> str:
        """Format score list e.g. '6:4, 7:6'."""
        if not self.score:
            return ""
        return ", ".join([f"{s.get('a')}:{s.get('b')}" for s in self.score if isinstance(s, dict)])

class HonorRollEntry(TimeStampedModel):
    year = models.PositiveIntegerField(_("Jahr"))
    competition_name = models.CharField(_("Bewerb"), max_length=100)
    winner_name = models.CharField(_("Ortsmeister / Sieger"), max_length=150)
    runner_up_name = models.CharField(_("Zweitplatzierter"), max_length=150, blank=True)
    score = models.CharField(_("Finalergebnis"), max_length=50, blank=True)

    class Meta:
        verbose_name = _("Ehrentafel-Eintrag")
        verbose_name_plural = _("Ehrentafel (Ortsmeister)")
        ordering = ["-year", "competition_name"]

    def __str__(self):
        return f"{self.year} - {self.competition_name}: {self.winner_name}"
