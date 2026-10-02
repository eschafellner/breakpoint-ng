import math
from datetime import timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from apps.accounts.models import User
from apps.billing.models import Charge
from apps.billing.services import create_charge
from apps.courts.models import Court, Booking, Blocking
from apps.core.services import log_audit
from .models import Tournament, Competition, Entry, Match

def validate_tennis_set(a: int, b: int, is_match_tiebreak: bool = False) -> bool:
    """
    Validate a single tennis set result.
    Valid standard sets: 6:0-6:4, 7:5, 7:6 (and inverted).
    Valid match tiebreak: winner >= 10 and diff >= 2.
    """
    if a < 0 or b < 0:
        return False
    if a == b:
        return False

    winner = max(a, b)
    loser = min(a, b)

    if is_match_tiebreak:
        return winner >= 10 and (winner - loser >= 2)

    # Standard set
    if winner == 6:
        return loser <= 4
    if winner == 7:
        return loser in (5, 6)
    return False

def validate_tennis_score(score: List[Dict[str, int]], is_final_set_tiebreak: bool = True) -> Tuple[bool, Optional[str]]:
    """Validate full match score (e.g. [{'a': 6, 'b': 4}, {'a': 7, 'b': 6}])."""
    if not score or len(score) < 2:
        return False, _("Ein Match muss aus mindestens zwei gespielten Sätzen bestehen.")

    sets_a = 0
    sets_b = 0
    total_sets = len(score)

    for i, s in enumerate(score):
        a = s.get("a", 0)
        b = s.get("b", 0)
        is_mtb = (i == 2 and total_sets == 3 and is_final_set_tiebreak)

        if not validate_tennis_set(a, b, is_match_tiebreak=is_mtb):
            return False, _(f"Ungültiger Satzstand im {i+1}. Satz: {a}:{b}.")

        if a > b:
            sets_a += 1
        else:
            sets_b += 1

    if max(sets_a, sets_b) < 2:
        return False, _("Ein Spieler muss mindestens 2 Gewinnsätze erzielen.")

    return True, None

@transaction.atomic
def register_for_competition(
    *,
    competition: Competition,
    player1: User,
    player2: Optional[User] = None,
) -> Entry:
    """Register participant(s) for a competition with eligibility, deadline, waitlist, and billing."""
    tournament = competition.tournament
    now = timezone.now()

    # 1. Registration deadline check
    if now > tournament.registration_deadline:
        raise ValidationError(_("Der Anmeldeschluss für dieses Turnier ist bereits abgelaufen."))

    # 2. Eligibility check
    if tournament.eligibility == Tournament.Eligibility.MEMBERS_ONLY:
        if player1.account_type != User.AccountType.MEMBER:
            raise ValidationError(_("Dieses Turnier ist ausschließlich für Vereinsmitglieder."))
        if player2 and player2.account_type != User.AccountType.MEMBER:
            raise ValidationError(_("Spieler 2 ist kein Vereinsmitglied."))

    # 3. Check for existing active registration
    existing = Entry.objects.filter(
        competition=competition,
        player1=player1,
    ).exclude(status=Entry.Status.WITHDRAWN).exists()
    if existing:
        raise ValidationError(_("Du bist für diese Konkurrenz bereits angemeldet."))

    # 4. Doubles partner requirement
    is_doubles = competition.discipline in [Competition.Discipline.DOUBLES, Competition.Discipline.MIXED]
    if is_doubles and not player2:
        raise ValidationError(_("Für Doppel/Mixed-Bewerbe muss ein Partner angegeben werden."))

    # 5. Capacity / Waitlist check
    confirmed_count = Entry.objects.filter(
        competition=competition,
        status=Entry.Status.CONFIRMED,
    ).count()

    initial_status = Entry.Status.CONFIRMED
    if is_doubles and player2 != player1:
        initial_status = Entry.Status.PENDING_PARTNER
    elif confirmed_count >= competition.max_entries:
        initial_status = Entry.Status.WAITLIST

    entry = Entry.objects.create(
        competition=competition,
        player1=player1,
        player2=player2,
        status=initial_status,
    )

    # 6. Central Billing Charge Creation (AP-08: Startgebühr)
    is_p1_member = (player1.account_type == User.AccountType.MEMBER)
    fee = tournament.fee_member if is_p1_member else tournament.fee_guest

    if fee > Decimal("0.00"):
        create_charge(
            user=player1,
            kind=Charge.Kind.TOURNAMENT_FEE,
            amount=fee,
            due_date=tournament.start_date,
            description=f"Startgebühr {tournament.name} ({competition.name})",
            source=entry,
        )

    log_audit(
        user=player1,
        action="REGISTER_TOURNAMENT",
        entity_type="Entry",
        entity_id=str(entry.pk),
        changes={"competition": competition.name, "status": entry.status},
    )

    return entry

@transaction.atomic
def confirm_partner_entry(entry: Entry, partner: User) -> Entry:
    """Confirm participation by player 2."""
    if entry.player2 != partner:
        raise ValidationError(_("Du bist nicht der angegebene Partner für diese Anmeldung."))
    if entry.status != Entry.Status.PENDING_PARTNER:
        return entry

    confirmed_count = Entry.objects.filter(
        competition=entry.competition,
        status=Entry.Status.CONFIRMED,
    ).count()

    if confirmed_count >= entry.competition.max_entries:
        entry.status = Entry.Status.WAITLIST
    else:
        entry.status = Entry.Status.CONFIRMED
    entry.save(update_fields=["status"])
    return entry

@transaction.atomic
def withdraw_entry(entry: Entry) -> None:
    """Withdraw from tournament; advances first waitlist entry if applicable."""
    prev_status = entry.status
    entry.status = Entry.Status.WITHDRAWN
    entry.save(update_fields=["status"])

    if prev_status == Entry.Status.CONFIRMED:
        # Promote first waitlist entry
        next_waitlist = Entry.objects.filter(
            competition=entry.competition,
            status=Entry.Status.WAITLIST,
        ).order_by("created_at").first()

        if next_waitlist:
            next_waitlist.status = Entry.Status.CONFIRMED
            next_waitlist.save(update_fields=["status"])

@transaction.atomic
def generate_knockout_draw(competition: Competition) -> List[Match]:
    """
    Generate single-elimination knockout tournament bracket (AP-09).
    - Seeds 1 and 2 are strictly on opposite sides (Pos 1 and Pos N).
    - Bracket size is next power of 2 >= number of entries (e.g. 11 entries -> 16 bracket).
    - Byes (Freilose) are allocated to top seeds.
    - Automatic progression for Bye matches.
    """
    entries = list(Entry.objects.filter(
        competition=competition,
        status=Entry.Status.CONFIRMED,
    ).order_by("seed", "id"))

    n = len(entries)
    if n < 2:
        raise ValidationError(_("Für eine Auslosung sind mindestens 2 Teilnehmer erforderlich."))

    # Clean existing matches
    competition.matches.all().delete()

    bracket_size = 2 ** math.ceil(math.log2(n)) if n > 2 else 2
    num_rounds = int(math.log2(bracket_size))
    m_count = bracket_size // 2
    num_byes = bracket_size - n

    # Priority of matches to receive a Bye (Seed 1 match 0, Seed 2 match M-1, etc.)
    priority_order = [0, m_count - 1]
    if m_count > 2:
        priority_order.extend([m_count // 2, (m_count // 2) - 1])
    for idx in range(m_count):
        if idx not in priority_order:
            priority_order.append(idx)
    bye_matches_set = set(priority_order[:num_byes])

    # Slots of size bracket_size
    slots = [None] * bracket_size

    seeded = [e for e in entries if e.seed]
    unseeded = [e for e in entries if not e.seed]

    seed_1 = seeded[0] if seeded else (entries[0] if entries else None)
    seed_2 = seeded[1] if len(seeded) > 1 else (entries[-1] if len(entries) > 1 else None)

    used_entries = set()
    if seed_1:
        slots[0] = seed_1
        used_entries.add(seed_1.id)
    if seed_2 and seed_2 != seed_1:
        slots[2 * (m_count - 1) + 1] = seed_2
        used_entries.add(seed_2.id)

    # Remaining entries to place
    rem_entries = [e for e in entries if e.id not in used_entries]

    # Collect available entry slot indices
    available_indices = []
    for k in range(m_count):
        has_bye = (k in bye_matches_set)
        if k == 0:
            if not has_bye:
                available_indices.append(1)
        elif k == m_count - 1:
            if not has_bye:
                available_indices.append(2 * (m_count - 1))
        else:
            available_indices.append(2 * k)
            if not has_bye:
                available_indices.append(2 * k + 1)

    for entry in rem_entries:
        if available_indices:
            idx = available_indices.pop(0)
            slots[idx] = entry

    # Create Match tree backwards from Final (Round N) down to Round 1
    # Round num_rounds = Final (1 match)
    # Round 1 = first round (bracket_size // 2 matches)
    round_matches = {}
    for r in range(num_rounds, 0, -1):
        num_matches = 2 ** (num_rounds - r)
        matches_in_r = []
        for p in range(1, num_matches + 1):
            next_m = None
            if r < num_rounds:
                parent_idx = (p - 1) // 2
                next_m = round_matches[r + 1][parent_idx]

            m = Match.objects.create(
                competition=competition,
                round=r,
                position=p,
                next_match=next_m,
            )
            matches_in_r.append(m)
        round_matches[r] = matches_in_r

    # Assign Round 1 entries and handle Byes
    round_1_matches = round_matches[1]
    for p, match in enumerate(round_1_matches):
        entry_a = slots[2 * p]
        entry_b = slots[2 * p + 1]

        match.entry_a = entry_a
        match.entry_b = entry_b

        # Bye handling: if one entry is None, automatic win for the other!
        if entry_a and not entry_b:
            match.winner = entry_a
            match.score = [{"a": "Bye", "b": ""}]
            if match.next_match:
                if (match.position % 2) == 1:
                    match.next_match.entry_a = entry_a
                else:
                    match.next_match.entry_b = entry_a
                match.next_match.save()
        elif entry_b and not entry_a:
            match.winner = entry_b
            match.score = [{"a": "", "b": "Bye"}]
            if match.next_match:
                if (match.position % 2) == 1:
                    match.next_match.entry_a = entry_b
                else:
                    match.next_match.entry_b = entry_b
                match.next_match.save()

        match.save()

    competition.tournament.status = Tournament.Status.DRAWN
    competition.tournament.save(update_fields=["status"])

    all_matches = list(competition.matches.all())
    return all_matches

@transaction.atomic
def generate_round_robin_draw(competition: Competition) -> List[Match]:
    """
    Generate Round Robin all-play-all match schedule (AP-09).
    N participants -> N*(N-1)/2 matches.
    """
    entries = list(Entry.objects.filter(
        competition=competition,
        status=Entry.Status.CONFIRMED,
    ).order_by("seed", "id"))

    n = len(entries)
    if n < 2:
        raise ValidationError(_("Für eine Auslosung sind mindestens 2 Teilnehmer erforderlich."))

    competition.matches.all().delete()

    created_matches = []
    pos = 1
    for i in range(n):
        for j in range(i + 1, n):
            m = Match.objects.create(
                competition=competition,
                round=1,
                position=pos,
                entry_a=entries[i],
                entry_b=entries[j],
            )
            created_matches.append(m)
            pos += 1

    competition.tournament.status = Tournament.Status.DRAWN
    competition.tournament.save(update_fields=["status"])

    return created_matches

@transaction.atomic
def record_match_result(
    *,
    match: Match,
    score: List[Dict[str, int]],
    winner: Entry,
    result_type: str = Match.ResultType.NORMAL,
) -> Match:
    """Record match scores, validate tennis rules, and advance winner in bracket."""
    if winner not in [match.entry_a, match.entry_b]:
        raise ValidationError(_("Der Sieger muss einer der beiden gemeldeten Spieler sein."))

    if result_type == Match.ResultType.NORMAL:
        is_valid, err = validate_tennis_score(score)
        if not is_valid:
            raise ValidationError(err)

    match.score = score
    match.winner = winner
    match.result_type = result_type
    match.save()

    # Advance winner into next match if Knockout
    if match.next_match:
        nm = match.next_match
        if (match.position % 2) == 1:
            nm.entry_a = winner
        else:
            nm.entry_b = winner
        nm.save(update_fields=["entry_a", "entry_b"])

    return match

@transaction.atomic
def schedule_tournament_match(
    *,
    match: Match,
    court: Court,
    start_dt,
    duration_minutes: int = 90,
) -> Blocking:
    """
    Assign a match to a court slot, creating a court Blocking.
    Detects and reports conflict with existing bookings (AP-09).
    """
    end_dt = start_dt + timedelta(minutes=duration_minutes)

    # Conflict check with existing confirmed bookings
    existing_booking = Booking.objects.filter(
        court=court,
        status=Booking.Status.CONFIRMED,
        start__lt=end_dt,
        end__gt=start_dt,
    ).first()
    if existing_booking:
        raise ValidationError(
            _("Terminkonflikt auf %(court)s: Es existiert bereits eine Buchung um %(time)s.")
            % {"court": court.name, "time": f"{existing_booking.start:%H:%M}"}
        )

    # Conflict with existing blockings (excluding previous blocking of same match)
    existing_blocking = Blocking.objects.filter(
        court=court,
        start__lt=end_dt,
        end__gt=start_dt,
    ).exclude(pk=getattr(match.blocking, "pk", None)).first()
    if existing_blocking:
        raise ValidationError(
            _("Terminkonflikt auf %(court)s: Der Platz ist zu dieser Zeit bereits gesperrt (%(reason)s).")
            % {"court": court.name, "reason": existing_blocking.get_reason_display()}
        )

    # Remove old blocking if rescheduling
    if match.blocking:
        match.blocking.delete()

    blocking = Blocking.objects.create(
        court=court,
        start=start_dt,
        end=end_dt,
        reason=Blocking.Reason.TOURNAMENT,
        note=f"Turnierspiel: {match.competition.name} ({match})",
    )

    match.scheduled_court = court
    match.scheduled_start = start_dt
    match.blocking = blocking
    match.save(update_fields=["scheduled_court", "scheduled_start", "blocking"])

    return blocking

def calculate_round_robin_standings(competition: Competition) -> List[Dict[str, Any]]:
    """Calculate tournament standings table for round-robin competitions (wins, sets, games)."""
    entries = Entry.objects.filter(competition=competition, status=Entry.Status.CONFIRMED)
    stats = {
        e.id: {
            "entry": e,
            "played": 0,
            "won": 0,
            "lost": 0,
            "sets_won": 0,
            "sets_lost": 0,
            "set_diff": 0,
            "games_won": 0,
            "games_lost": 0,
            "game_diff": 0,
        }
        for e in entries
    }

    matches = competition.matches.filter(winner__isnull=False)
    for m in matches:
        if m.entry_a_id in stats and m.entry_b_id in stats:
            stats[m.entry_a_id]["played"] += 1
            stats[m.entry_b_id]["played"] += 1

            if m.winner_id == m.entry_a_id:
                stats[m.entry_a_id]["won"] += 1
                stats[m.entry_b_id]["lost"] += 1
            else:
                stats[m.entry_b_id]["won"] += 1
                stats[m.entry_a_id]["lost"] += 1

            for s in m.score:
                if isinstance(s, dict):
                    ga = int(s.get("a", 0) or 0)
                    gb = int(s.get("b", 0) or 0)
                    stats[m.entry_a_id]["games_won"] += ga
                    stats[m.entry_a_id]["games_lost"] += gb
                    stats[m.entry_b_id]["games_won"] += gb
                    stats[m.entry_b_id]["games_lost"] += ga

                    if ga > gb:
                        stats[m.entry_a_id]["sets_won"] += 1
                        stats[m.entry_b_id]["sets_lost"] += 1
                    elif gb > ga:
                        stats[m.entry_b_id]["sets_won"] += 1
                        stats[m.entry_a_id]["sets_lost"] += 1

    table = list(stats.values())
    for row in table:
        row["set_diff"] = row["sets_won"] - row["sets_lost"]
        row["game_diff"] = row["games_won"] - row["games_lost"]

    # Sort primarily by matches won, then set diff, then game diff
    table.sort(key=lambda r: (r["won"], r["set_diff"], r["game_diff"]), reverse=True)
    return table
