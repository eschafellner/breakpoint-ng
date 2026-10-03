from datetime import date, time, timedelta
from decimal import Decimal
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.conf import settings
from django.utils import timezone
from apps.accounts.models import User
from apps.accounts.services import create_standard_groups
from apps.core.models import ClubSettings
from apps.members.models import MembershipType, Membership
from apps.courts.models import Court, OpeningHours
from apps.billing.models import PriceRule, BookingExtra
from apps.news.models import Category, Article
from apps.news.services import create_article
from apps.tournaments.models import Tournament, Competition, Entry
from apps.tournaments.services import generate_knockout_draw

FIRST_NAMES = [
    "Alexander",
    "Anna",
    "Bernhard",
    "Birgit",
    "Christoph",
    "Claudia",
    "Daniel",
    "Doris",
    "Elias",
    "Elisabeth",
    "Fabian",
    "Franziska",
    "Georg",
    "Gerda",
    "Harald",
    "Helena",
    "Jakob",
    "Julia",
    "Klaus",
    "Katharina",
    "Lukas",
    "Lena",
    "Martin",
    "Monika",
    "Nikolaus",
    "Nina",
    "Oliver",
    "Petra",
    "Philipp",
    "Renate",
    "Robert",
    "Sabine",
    "Sebastian",
    "Sandra",
    "Thomas",
    "Tanja",
    "Ulrich",
    "Ursula",
    "Valentin",
    "Verena",
    "Wolfgang",
    "Viktoria",
    "Johannes",
    "Theresa",
    "Michael",
    "Maria",
    "Maximilian",
    "Sophie",
    "Florian",
    "Laura",
]

LAST_NAMES = [
    "Moser",
    "Gruber",
    "Bauer",
    "Huber",
    "Steiner",
    "Pichler",
    "Wagner",
    "Müller",
    "Schmidt",
    "Wallner",
    "Aigner",
    "Eder",
    "Fischer",
    "Fuchs",
    "Hofer",
    "Leitner",
    "Mayr",
    "Reiter",
    "Schmid",
    "Weber",
    "Wimmer",
    "Berger",
    "Wieser",
    "Kaufmann",
    "Brunner",
    "Ebner",
    "Haas",
    "Koller",
    "Lang",
    "Maier",
    "Ortner",
    "Rauch",
    "Schwarz",
    "Stadler",
    "Vogel",
    "Weiß",
    "Zimmermann",
    "Brandl",
    "Graf",
    "Hartl",
    "Kogler",
    "Kroll",
    "Lindner",
    "Mader",
    "Neuhauser",
    "Prinz",
    "Riedl",
    "Sailer",
    "Traxler",
    "Winter",
]


class Command(BaseCommand):
    help = "Seed database with demo data: 50 members, 10 guests, 4 courts, 2 tournaments, news"

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Demodaten dürfen nur mit DEBUG=True erzeugt werden.")
        self.stdout.write("Erstelle Standard-Gruppen und Rollen...")
        create_standard_groups()

        # 1. Club Settings
        club_settings = ClubSettings.get_settings()
        club_settings.name = "TC Musterdorf"
        club_settings.short_name = "TCM"
        club_settings.tagline = "Spiel, Satz und Verein seit 1974."
        club_settings.email = "vorstand@tc-musterdorf.at"
        club_settings.phone = "+43 123 456789"
        club_settings.address = "Tennisplatzweg 4, 3002 Musterdorf"
        club_settings.bank_name = "Raiffeisenbank Musterdorf"
        club_settings.iban = "AT483200000012345678"
        club_settings.bic = "RLBAT2W1XXX"
        club_settings.save()
        self.stdout.write("[OK] Vereins-Einstellungen konfiguriert.")

        # 2. Staff & Role Accounts
        admin_group = Group.objects.get(name="Administrator")
        kassier_group = Group.objects.get(name="Kassier")
        platzwart_group = Group.objects.get(name="Platzwart")
        redakteur_group = Group.objects.get(name="Redakteur")
        turnier_group = Group.objects.get(name="Turnierleiter")

        admin, _ = User.objects.get_or_create(
            email="admin@tc-musterdorf.at",
            defaults={
                "first_name": "Edgar",
                "last_name": "Vorstand",
                "account_type": User.AccountType.MEMBER,
                "is_staff": True,
                "is_superuser": True,
                "email_verified": True,
            },
        )
        admin.set_password("admin1234")
        admin.groups.add(admin_group)
        admin.save()

        kassier, _ = User.objects.get_or_create(
            email="kassier@tc-musterdorf.at",
            defaults={
                "first_name": "Karl",
                "last_name": "Kassier",
                "account_type": User.AccountType.MEMBER,
                "is_staff": True,
                "email_verified": True,
            },
        )
        kassier.set_password("kassier1234")
        kassier.groups.add(kassier_group)
        kassier.save()

        platzwart, _ = User.objects.get_or_create(
            email="platzwart@tc-musterdorf.at",
            defaults={
                "first_name": "Peter",
                "last_name": "Platzwart",
                "account_type": User.AccountType.MEMBER,
                "is_staff": True,
                "email_verified": True,
            },
        )
        platzwart.set_password("platzwart1234")
        platzwart.groups.add(platzwart_group)
        platzwart.save()

        redakteur, _ = User.objects.get_or_create(
            email="redakteur@tc-musterdorf.at",
            defaults={
                "first_name": "Rita",
                "last_name": "Redakteur",
                "account_type": User.AccountType.MEMBER,
                "is_staff": True,
                "email_verified": True,
            },
        )
        redakteur.set_password("redakteur1234")
        redakteur.groups.add(redakteur_group)
        redakteur.save()

        turnierleiter, _ = User.objects.get_or_create(
            email="turnierleiter@tc-musterdorf.at",
            defaults={
                "first_name": "Tobias",
                "last_name": "Turnierleiter",
                "account_type": User.AccountType.MEMBER,
                "is_staff": True,
                "email_verified": True,
            },
        )
        turnierleiter.set_password("turnier1234")
        turnierleiter.groups.add(turnier_group)
        turnierleiter.save()

        self.stdout.write(
            "[OK] Rollenkonten (Admin, Kassier, Platzwart, Redakteur, Turnierleiter) erstellt."
        )

        # 3. Membership Types
        t_erw, _ = MembershipType.objects.get_or_create(
            name="Erwachsener",
            defaults={
                "fee_amount": Decimal("180.00"),
                "billing_interval": MembershipType.BillingInterval.YEARLY,
            },
        )
        t_jug, _ = MembershipType.objects.get_or_create(
            name="Jugendlicher (U18)",
            defaults={
                "fee_amount": Decimal("80.00"),
                "billing_interval": MembershipType.BillingInterval.YEARLY,
                "max_age": 18,
            },
        )
        t_fam, _ = MembershipType.objects.get_or_create(
            name="Familie",
            defaults={
                "fee_amount": Decimal("320.00"),
                "billing_interval": MembershipType.BillingInterval.YEARLY,
            },
        )
        t_mon, _ = MembershipType.objects.get_or_create(
            name="Monatsbeitrag",
            defaults={
                "fee_amount": Decimal("20.00"),
                "billing_interval": MembershipType.BillingInterval.MONTHLY,
            },
        )

        # 4. 50 Members
        members_created = []
        for i in range(50):
            fn = FIRST_NAMES[i % len(FIRST_NAMES)]
            ln = LAST_NAMES[i % len(LAST_NAMES)]
            email = f"mitglied{i+1:02d}@example.com"
            user, _ = User.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": fn,
                    "last_name": ln,
                    "phone": f"+43 664 {1000000 + i}",
                    "account_type": User.AccountType.MEMBER,
                    "email_verified": True,
                },
            )
            if _:
                user.set_password("pass1234")
                user.save()

            m_type = t_erw if (i % 3 == 0) else (t_jug if (i % 3 == 1) else t_fam)
            mem_num = f"TCM-{i+1:04d}"
            if not Membership.objects.filter(member_number=mem_num).exists():
                Membership.objects.create(
                    user=user,
                    type=m_type,
                    member_number=mem_num,
                    start_date=date(2026, 1, 1),
                    status=Membership.Status.ACTIVE,
                )
            members_created.append(user)

        self.stdout.write(f"[OK] {len(members_created)} Mitglieder angelegt.")

        # 5. 10 Guests
        for i in range(1, 11):
            email = f"gast{i:02d}@example.com"
            u, _ = User.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": f"Gast_{i}",
                    "last_name": f"Besucher_{i}",
                    "phone": f"+43 699 {2000000 + i}",
                    "account_type": User.AccountType.GUEST,
                    "email_verified": True,
                },
            )
            if _:
                u.set_password("gast1234")
                u.save()

        self.stdout.write("[OK] 10 Gäste angelegt.")

        # 6. 4 Courts
        courts = [
            ("Platz 1 (Centrecourt)", Court.Surface.SAND, False, True, 1),
            ("Platz 2", Court.Surface.SAND, False, True, 2),
            ("Platz 3", Court.Surface.SAND, False, False, 3),
            ("Halle 1 (Teppich)", Court.Surface.HALLE, True, True, 4),
        ]
        created_courts = []
        for name, surface, indoor, floodlight, ord_num in courts:
            court, _ = Court.objects.get_or_create(
                name=name,
                defaults={
                    "surface": surface,
                    "is_indoor": indoor,
                    "has_floodlight": floodlight,
                    "is_active": True,
                    "order": ord_num,
                },
            )
            created_courts.append(court)

            # Opening hours 08:00 - 22:00
            for w in range(7):
                OpeningHours.objects.get_or_create(
                    court=court,
                    weekday=w,
                    defaults={
                        "open_time": time(8, 0),
                        "close_time": time(22, 0),
                        "slot_minutes": 60,
                    },
                )

        # Price rules & Extras
        PriceRule.objects.get_or_create(
            court=None,
            applies_to=PriceRule.AppliesTo.GUEST,
            defaults={"price_per_hour": Decimal("16.00")},
        )
        PriceRule.objects.get_or_create(
            court=None,
            applies_to=PriceRule.AppliesTo.GUEST_OF_MEMBER,
            defaults={"price_per_person": Decimal("5.00")},
        )
        BookingExtra.objects.get_or_create(
            name="Flutlicht",
            defaults={
                "price_member": Decimal("4.00"),
                "price_guest": Decimal("6.00"),
                "unit": BookingExtra.Unit.PER_HOUR,
                "mode": BookingExtra.Mode.OPTIONAL,
                "is_active": True,
            },
        )
        halle_court = next(c for c in created_courts if c.is_indoor)
        extra_halle, _ = BookingExtra.objects.get_or_create(
            name="Hallenaufschlag",
            defaults={
                "price_member": Decimal("10.00"),
                "price_guest": Decimal("14.00"),
                "unit": BookingExtra.Unit.PER_HOUR,
                "mode": BookingExtra.Mode.AUTOMATIC,
                "is_active": True,
            },
        )
        extra_halle.courts.add(halle_court)
        self.stdout.write(
            "[OK] 4 Plätze, Öffnungszeiten, Preisregeln und Extras angelegt."
        )

        # 7. 2 Tournaments
        now = timezone.now()
        t1, _ = Tournament.objects.get_or_create(
            slug="ortsmeisterschaft-2027",
            defaults={
                "name": "Ortsmeisterschaft 2027",
                "description": "Die traditionelle Ortsmeisterschaft des TC Musterdorf im K.-o.-System.",
                "start_date": date(2027, 7, 10),
                "end_date": date(2027, 7, 12),
                "registration_deadline": now + timedelta(days=60),
                "eligibility": Tournament.Eligibility.MEMBERS_ONLY,
                "fee_member": Decimal("15.00"),
                "fee_guest": Decimal("25.00"),
                "status": Tournament.Status.OPEN,
            },
        )
        c1, _ = Competition.objects.get_or_create(
            tournament=t1,
            name="Herren Einzel",
            defaults={
                "discipline": Competition.Discipline.SINGLES,
                "format": Competition.Format.KNOCKOUT,
                "max_entries": 16,
                "age_class": "Allgemeine Klasse",
            },
        )
        # Register 11 entries and draw bracket
        for idx in range(11):
            seed = (idx + 1) if idx < 2 else None
            Entry.objects.get_or_create(
                competition=c1,
                player1=members_created[idx],
                defaults={"seed": seed, "status": Entry.Status.CONFIRMED},
            )
        generate_knockout_draw(c1)

        t2, _ = Tournament.objects.get_or_create(
            slug="sommer-cup-2027",
            defaults={
                "name": "Sommer-Cup 2027",
                "description": "Offenes Freundschaftsturnier für Mitglieder und Gäste im Gruppenmodus.",
                "start_date": date(2027, 8, 14),
                "end_date": date(2027, 8, 15),
                "registration_deadline": now + timedelta(days=90),
                "eligibility": Tournament.Eligibility.MEMBERS_AND_GUESTS,
                "fee_member": Decimal("12.00"),
                "fee_guest": Decimal("18.00"),
                "status": Tournament.Status.OPEN,
            },
        )
        Competition.objects.get_or_create(
            tournament=t2,
            name="Mixed Doppel",
            defaults={
                "discipline": Competition.Discipline.MIXED,
                "format": Competition.Format.ROUND_ROBIN,
                "max_entries": 8,
            },
        )
        self.stdout.write(
            "[OK] 2 Turniere mit Konkurrenzen und K.-o.-Tableau angelegt."
        )

        # 8. News Articles
        cat_verein, _ = Category.objects.get_or_create(name="Verein", slug="verein")
        cat_turniere, _ = Category.objects.get_or_create(
            name="Turniere", slug="turniere"
        )

        if not Article.objects.filter(slug="saisoneroeffnung-2027").exists():
            create_article(
                title="Saisoneröffnung 2027",
                teaser="Die Freiplätze sind ab sofort bespielbar! Wir freuen uns auf eine erfolgreiche Tennissaison.",
                body="<p>Liebe Mitglieder und Tennisfreunde,</p><p>unsere Sandplätze wurden in den vergangenen Wochen aufbereitet und sind ab sofort für den Spielbetrieb freigegeben. Wir bitten alle Spielerinnen und Spieler, die Plätze nach dem Spiel sorgfältig abzuziehen und bei Trockenheit zu wässern.</p>",
                category=cat_verein,
                author=redakteur,
                is_pinned=True,
            )

        if not Article.objects.filter(
            slug="ausschreibung-ortsmeisterschaft-2027"
        ).exists():
            create_article(
                title="Ausschreibung Ortsmeisterschaft 2027",
                teaser="Die Anmeldung für die diesjährige Ortsmeisterschaft ist ab sofort online geöffnet.",
                body="<p>Ab sofort könnt ihr euch im Turniermenü direkt für die Einzel- und Doppelbewerbe anmelden. Wir freuen uns auf spannende Matches!</p>",
                category=cat_turniere,
                author=redakteur,
            )

        self.stdout.write(
            self.style.SUCCESS("[OK] Seed-Daten erfolgreich vollständig eingespielt!")
        )
