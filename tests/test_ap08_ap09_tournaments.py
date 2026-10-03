import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.utils import timezone
from apps.accounts.models import User
from apps.billing.models import Charge
from apps.courts.models import Booking
from apps.tournaments.models import Tournament, Competition, Entry, Match
from apps.tournaments.services import (
    register_for_competition,
    confirm_partner_entry,
    withdraw_entry,
    generate_knockout_draw,
    generate_round_robin_draw,
    validate_tennis_set,
    validate_tennis_score,
    record_match_result,
    schedule_tournament_match,
    calculate_round_robin_standings,
)


@pytest.fixture
def open_tournament(db):
    now = timezone.now()
    return Tournament.objects.create(
        name="Ortsmeisterschaft 2027",
        start_date=date(2027, 7, 10),
        end_date=date(2027, 7, 12),
        registration_deadline=now + timedelta(days=10),
        eligibility=Tournament.Eligibility.MEMBERS_ONLY,
        fee_member=Decimal("20.00"),
        fee_guest=Decimal("30.00"),
        status=Tournament.Status.OPEN,
    )


@pytest.mark.django_db
def test_guest_registration_eligibility_enforced(open_tournament, guest_user):
    """AP-08: Gast kann sich nur bei Turnieren mit Berechtigung „Mitglieder und Gäste“ anmelden."""
    comp = Competition.objects.create(
        tournament=open_tournament,
        name="Herren Einzel",
        discipline=Competition.Discipline.SINGLES,
    )
    # Open tournament has MEMBERS_ONLY eligibility -> guest registration fails
    with pytest.raises(ValidationError):
        register_for_competition(competition=comp, player1=guest_user)

    # Change to MEMBERS_AND_GUESTS -> succeeds
    open_tournament.eligibility = Tournament.Eligibility.MEMBERS_AND_GUESTS
    open_tournament.save()

    entry = register_for_competition(competition=comp, player1=guest_user)
    assert entry.status == Entry.Status.CONFIRMED

    # Charge created
    chg = Charge.objects.get(object_id=entry.id)
    assert chg.amount == Decimal("30.00")
    assert chg.kind == Charge.Kind.TOURNAMENT_FEE


@pytest.mark.django_db
def test_doubles_partner_confirmation(open_tournament, member_user, member_user2):
    """AP-08: Doppelanmeldung erfordert Bestätigung durch Partner."""
    comp = Competition.objects.create(
        tournament=open_tournament,
        name="Herren Doppel",
        discipline=Competition.Discipline.DOUBLES,
        max_entries=8,
    )

    entry = register_for_competition(
        competition=comp,
        player1=member_user,
        player2=member_user2,
    )
    assert entry.status == Entry.Status.PENDING_PARTNER

    # Partner confirms
    confirm_partner_entry(entry, partner=member_user2)
    entry.refresh_from_db()
    assert entry.status == Entry.Status.CONFIRMED


@pytest.mark.django_db
def test_waitlist_and_withdrawal_promotion(open_tournament, member_user):
    """AP-08: Bei Erreichen von max_entries -> Warteliste; Abmeldung rückt nächsten nach."""
    comp = Competition.objects.create(
        tournament=open_tournament,
        name="Einzel",
        discipline=Competition.Discipline.SINGLES,
        max_entries=2,
    )

    u1 = member_user
    u2 = User.objects.create_user(
        email="u2@test.at",
        password="p",
        account_type=User.AccountType.MEMBER,
        email_verified=True,
    )
    u3 = User.objects.create_user(
        email="u3@test.at",
        password="p",
        account_type=User.AccountType.MEMBER,
        email_verified=True,
    )
    from apps.members.models import Membership

    for index, user in enumerate([u2, u3], start=2):
        Membership.objects.create(
            user=user,
            type=member_user.memberships.get().type,
            member_number=f"TCM-{index:04d}",
            start_date=timezone.localdate(),
        )

    e1 = register_for_competition(competition=comp, player1=u1)
    e2 = register_for_competition(competition=comp, player1=u2)
    e3 = register_for_competition(competition=comp, player1=u3)

    assert e1.status == Entry.Status.CONFIRMED
    assert e2.status == Entry.Status.CONFIRMED
    assert e3.status == Entry.Status.WAITLIST

    # Withdraw e1 -> e3 promoted to CONFIRMED!
    withdraw_entry(e1)
    e1.refresh_from_db()
    e3.refresh_from_db()
    assert e1.status == Entry.Status.WITHDRAWN
    assert e3.status == Entry.Status.CONFIRMED


@pytest.mark.django_db
def test_knockout_draw_11_players_16_bracket_seeds_and_byes(open_tournament):
    """
    AP-09:
    - K.-o.-Auslosung für 11 Teilnehmer erzeugt 16er-Tableau mit 5 Freilosen.
    - Gesetzte 1 und 2 können sich erst im Finale treffen.
    """
    comp = Competition.objects.create(
        tournament=open_tournament,
        name="Herren Einzel 16",
        discipline=Competition.Discipline.SINGLES,
        format=Competition.Format.KNOCKOUT,
        max_entries=16,
    )

    # Create 11 confirmed entries with Seed 1 and Seed 2
    entries = []
    for i in range(1, 12):
        u = User.objects.create_user(
            email=f"p{i}@test.at", password="p", account_type=User.AccountType.MEMBER
        )
        seed = 1 if i == 1 else (2 if i == 2 else None)
        e = Entry.objects.create(
            competition=comp, player1=u, seed=seed, status=Entry.Status.CONFIRMED
        )
        entries.append(e)

    matches = generate_knockout_draw(comp)

    # 16 bracket: R1 has 8 matches, R2 has 4, R3 (SF) has 2, R4 (Final) has 1 => Total 15 matches
    assert len(matches) == 15

    round_1_matches = [m for m in matches if m.round == 1]
    assert len(round_1_matches) == 8

    # Seed 1 must be in match 1 (top of bracket)
    # Seed 2 must be in match 8 (bottom of bracket)
    first_match = round_1_matches[0]
    last_match = round_1_matches[7]

    assert entries[0] in [first_match.entry_a, first_match.entry_b]
    assert entries[1] in [last_match.entry_a, last_match.entry_b]

    # Byes: 16 - 11 = 5 matches in Round 1 had a Bye (single entry with automatic progression)
    bye_matches = [m for m in round_1_matches if m.winner is not None]
    assert len(bye_matches) == 5


@pytest.mark.django_db
def test_round_robin_5_players_10_matches_and_standings(open_tournament):
    """
    AP-09:
    - Jeder-gegen-jeden mit 5 Teilnehmern erzeugt 10 Spiele.
    - Tabelle nach Siegen, Satz- und Spieldifferenz.
    """
    comp = Competition.objects.create(
        tournament=open_tournament,
        name="Round Robin 5",
        discipline=Competition.Discipline.SINGLES,
        format=Competition.Format.ROUND_ROBIN,
        max_entries=10,
    )

    entries = []
    for i in range(1, 6):
        u = User.objects.create_user(
            email=f"rr{i}@test.at",
            password="p",
            first_name=f"Spieler {i}",
            account_type=User.AccountType.MEMBER,
        )
        e = Entry.objects.create(
            competition=comp, player1=u, status=Entry.Status.CONFIRMED
        )
        entries.append(e)

    matches = generate_round_robin_draw(comp)
    # N * (N-1) / 2 = 5 * 4 / 2 = 10 matches
    assert len(matches) == 10

    # Record a result: entry 0 beats entry 1: 6:4, 6:3
    m = matches[0]
    record_match_result(
        match=m,
        score=[{"a": 6, "b": 4}, {"a": 6, "b": 3}],
        winner=m.entry_a,
    )

    table = calculate_round_robin_standings(comp)
    assert len(table) == 5
    leader = table[0]
    assert leader["entry"] == m.entry_a
    assert leader["won"] == 1
    assert leader["set_diff"] == 2
    assert leader["game_diff"] == 5


@pytest.mark.django_db
def test_tennis_score_validation():
    """AP-09: Ergebniseingabe validiert Tennis-Ergebnisse (z. B. 6:4, 7:6, MTB 10:8; 6:5 ungültig)."""
    assert validate_tennis_set(6, 4) is True
    assert validate_tennis_set(7, 6) is True
    assert validate_tennis_set(7, 5) is True
    assert validate_tennis_set(6, 5) is False
    assert validate_tennis_set(7, 4) is False
    assert validate_tennis_set(6, 6) is False
    assert validate_tennis_set(10, 8, is_match_tiebreak=True) is True
    assert validate_tennis_set(9, 7, is_match_tiebreak=True) is False

    valid, _ = validate_tennis_score([{"a": 6, "b": 4}, {"a": 7, "b": 6}])
    assert valid is True

    invalid, err = validate_tennis_score([{"a": 6, "b": 5}, {"a": 6, "b": 4}])
    assert invalid is False


@pytest.mark.django_db
def test_schedule_match_creates_blocking_and_detects_conflict(
    open_tournament, court_sand, member_user
):
    """
    AP-09:
    - Zuweisung von Platz/Zeit erzeugt Blocking in der Platzbuchung.
    - Konflikt mit bestehender Buchung wird gemeldet.
    """
    comp = Competition.objects.create(
        tournament=open_tournament,
        name="Einzel",
        discipline=Competition.Discipline.SINGLES,
    )
    u1 = member_user
    u2 = User.objects.create_user(
        email="gegner@test.at", password="p", account_type=User.AccountType.MEMBER
    )
    e1 = Entry.objects.create(
        competition=comp, player1=u1, status=Entry.Status.CONFIRMED
    )
    e2 = Entry.objects.create(
        competition=comp, player1=u2, status=Entry.Status.CONFIRMED
    )

    match = Match.objects.create(
        competition=comp, round=1, position=1, entry_a=e1, entry_b=e2
    )

    start = timezone.now() + timedelta(days=2, hours=10)

    # 1. Existing regular booking creates conflict
    Booking.objects.create(
        court=court_sand,
        booked_by=member_user,
        start=start,
        end=start + timedelta(hours=1),
        status=Booking.Status.CONFIRMED,
    )

    with pytest.raises(ValidationError) as exc:
        schedule_tournament_match(match=match, court=court_sand, start_dt=start)
    assert "Terminkonflikt" in str(exc.value)

    # 2. Rescheduling without conflict succeeds and creates Blocking
    clear_start = timezone.now() + timedelta(days=3, hours=14)
    blocking = schedule_tournament_match(
        match=match, court=court_sand, start_dt=clear_start
    )
    assert blocking.pk is not None
    assert blocking.court == court_sand
    assert match.blocking == blocking
