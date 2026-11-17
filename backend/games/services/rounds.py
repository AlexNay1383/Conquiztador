import random
import re
from datetime import timedelta

from django.db import transaction
from django.db.models import Max

from games import clock
from games.exceptions import InvalidInputError, InvalidStateError, NotFoundError
from games.models import Player, Round, RoundAnswer, RoundPlacement, RoundQuestion
from games.ranking import NumericAnswer, rank_numeric
from questions.models import NumericQuestion

from .capture import require_no_pending_rights
from .common import get_game_id_for_round, lock_game, require_active
from .scoring import apply_round_result, capture_picks, free_territories

ANSWER_WINDOW = timedelta(seconds=10)
MAX_QUESTIONS_PER_ROUND = 3
INTEGER_PATTERN = re.compile(r"[+-]?\d+")
MAX_ANSWER_MAGNITUDE = 2**63 - 1


def require_no_open_round(game):
    if game.rounds.exclude(status=Round.Status.COMPLETED).exists():
        raise InvalidStateError("Предишният рунд още не е завършен.", "round_in_progress")


def next_round_number(game):
    return (game.rounds.aggregate(last=Max("number"))["last"] or 0) + 1


def pick_numeric_question(game, rng):
    used = RoundQuestion.objects.filter(game=game, numeric_question__isnull=False).values("numeric_question_id")
    candidates = list(NumericQuestion.objects.exclude(pk__in=used).values_list("pk", flat=True))
    if not candidates:
        return None
    return NumericQuestion.objects.get(pk=rng.choice(candidates))


def add_numeric_question(round_, sequence, source, player_ids, first_place, place_count, start_at=None):
    question = RoundQuestion.objects.create(
        round=round_,
        game_id=round_.game_id,
        sequence=sequence,
        kind=RoundQuestion.Kind.NUMERIC,
        numeric_question=source,
        text=source.text,
        correct_answer=source.correct_answer,
        first_place=first_place,
        place_count=place_count,
    )
    question.participants.set(player_ids)
    if start_at is not None:
        activate_question(question, start_at)
    return question


def activate_question(question, now):
    question.status = RoundQuestion.Status.ACTIVE
    question.started_at = now
    question.deadline = now + ANSWER_WINDOW
    question.save(update_fields=["status", "started_at", "deadline"])


@transaction.atomic
def create_city_capture_round(game_id, rng=None):
    """Create a pending round for all three players with its first numeric question, without starting the clock.

    The number of free territories is frozen now; it decides how many places the round needs and,
    after it ends, how many territories each ranked player may pick.
    """
    rng = rng or random.Random()
    game = lock_game(game_id)
    require_active(game)
    require_no_open_round(game)
    require_no_pending_rights(game)
    free_count = free_territories(game).count()
    if free_count == 0:
        raise InvalidStateError("Всички територии вече са завзети.", "no_free_territories")
    source = pick_numeric_question(game, rng)
    if source is None:
        raise InvalidStateError("Няма неизползван числов въпрос.", "no_question_available")

    places_needed = 2 if capture_picks(free_count, 2) else 1
    player_ids = list(game.players.order_by("pk").values_list("pk", flat=True))
    round_ = Round.objects.create(
        game=game,
        number=next_round_number(game),
        type=Round.Type.CITY_CAPTURE,
        places_needed=places_needed,
        free_territories_at_creation=free_count,
    )
    round_.participants.set(player_ids)
    add_numeric_question(round_, 1, source, player_ids, first_place=1, place_count=places_needed)
    return round_


def lock_round(round_id):
    game = lock_game(get_game_id_for_round(round_id))
    require_active(game)
    return game, Round.objects.select_for_update().get(pk=round_id)


def require_open_question(round_):
    if round_.status == Round.Status.PENDING:
        raise InvalidStateError("Рундът още не е започнал.", "round_not_started")
    if round_.status == Round.Status.COMPLETED:
        raise InvalidStateError("Рундът вече е завършен.", "round_completed")
    question = round_.questions.select_for_update().filter(status=RoundQuestion.Status.ACTIVE).first()
    if question is None:
        raise InvalidStateError("Няма активен въпрос.", "no_active_question")
    return question


@transaction.atomic
def start_round(round_id):
    now = clock.now()
    _, round_ = lock_round(round_id)
    if round_.status != Round.Status.PENDING:
        raise InvalidStateError("Рундът вече е започнал.", "round_not_pending")
    activate_question(round_.questions.get(sequence=1), now)
    round_.status = Round.Status.ACTIVE
    round_.started_at = now
    round_.save(update_fields=["status", "started_at"])
    return round_


def parse_integer_answer(value):
    if isinstance(value, bool):
        value = None
    elif isinstance(value, str) and INTEGER_PATTERN.fullmatch(value.strip()):
        value = int(value.strip())
    if not isinstance(value, int) or abs(value) > MAX_ANSWER_MAGNITUDE:
        raise InvalidInputError("Отговорът трябва да е цяло число.", "invalid_answer")
    return value


def parse_answer(question, value):
    return {"numeric_value": parse_integer_answer(value)}


def require_participant(question, player_id):
    if not Player.objects.filter(pk=player_id).exists():
        raise NotFoundError("Играчът не съществува.", "player_not_found")
    if not question.participants.filter(pk=player_id).exists():
        raise InvalidInputError("Играчът не участва в текущия въпрос.", "player_not_participant")


def submit_answer(round_id, player_id, value):
    """Accept one answer from a participant of the active question, strictly before its deadline."""
    received_at = clock.now()
    with transaction.atomic():
        _, round_ = lock_round(round_id)
        question = require_open_question(round_)
        require_participant(question, player_id)
        if received_at >= question.deadline:
            raise InvalidStateError("Времето за отговор изтече.", "deadline_passed")
        fields = parse_answer(question, value)
        if question.answers.filter(player_id=player_id).exists():
            raise InvalidStateError("Вече сте отговорили на този въпрос.", "already_answered")

        answer = RoundAnswer.objects.create(question=question, player_id=player_id, received_at=received_at, **fields)
        if question.answers.count() == question.participants.count():
            close_question_now(round_, question, received_at)
        return answer


@transaction.atomic
def close_question(round_id):
    """Process the active question once everyone has answered or its deadline has passed."""
    now = clock.now()
    _, round_ = lock_round(round_id)
    question = require_open_question(round_)
    if now < question.deadline and question.answers.count() < question.participants.count():
        raise InvalidStateError("Въпросът все още приема отговори.", "question_still_open")
    close_question_now(round_, question, now)
    return round_


def evaluate_question(question):
    answers = [
        NumericAnswer(answer.player_id, answer.numeric_value, answer.received_at) for answer in question.answers.all()
    ]
    group = list(question.participants.values_list("pk", flat=True))
    return rank_numeric(answers, question.correct_answer, group, question.first_place, question.place_count)


def pick_follow_up_question(game, kind, rng):
    return pick_numeric_question(game, rng)


def close_question_now(round_, question, now, rng=None):
    question.status = RoundQuestion.Status.COMPLETED
    question.completed_at = now
    question.save(update_fields=["status", "completed_at"])

    outcome = evaluate_question(question)
    RoundPlacement.objects.bulk_create(
        RoundPlacement(round=round_, place=place, player_id=player_id, decided_by=question)
        for place, player_id in outcome.placements
    )

    if outcome.follow_up is None:
        reason = Round.UnresolvedReason.NOT_ENOUGH_ANSWERS if outcome.unresolved else Round.UnresolvedReason.NONE
        finish_round(round_, now, reason)
        return
    if question.sequence >= MAX_QUESTIONS_PER_ROUND:
        finish_round(round_, now, Round.UnresolvedReason.QUESTION_LIMIT)
        return
    source = pick_follow_up_question(round_.game, outcome.follow_up_kind, rng or random.Random())
    if source is None:
        finish_round(round_, now, Round.UnresolvedReason.QUESTION_BANK_EXHAUSTED)
        return
    follow_up = outcome.follow_up
    add_numeric_question(
        round_, question.sequence + 1, source, follow_up.player_ids, follow_up.first_place, follow_up.place_count, now
    )


def finish_round(round_, now, reason):
    ranking = dict(round_.placements.values_list("place", "player_id"))
    complete = all(place in ranking for place in range(1, round_.places_needed + 1))
    round_.winner_id = ranking.get(1)
    round_.unresolved_reason = Round.UnresolvedReason.NONE if complete else (
        reason or Round.UnresolvedReason.NOT_ENOUGH_ANSWERS
    )
    round_.status = Round.Status.COMPLETED
    round_.completed_at = now
    round_.save(update_fields=["winner", "unresolved_reason", "status", "completed_at"])
    apply_round_result(round_)


def get_round_state(round_id, now=None):
    """Everything a client needs to restore a round after reloading: current question, time left, ranking."""
    now = now or clock.now()
    round_ = Round.objects.filter(pk=round_id).first()
    if round_ is None:
        raise NotFoundError("Рундът не съществува.", "round_not_found")

    questions = []
    current = None
    for question in round_.questions.prefetch_related("participants", "answers").order_by("sequence"):
        finished = question.status == RoundQuestion.Status.COMPLETED
        item = {
            "sequence": question.sequence,
            "kind": question.kind,
            "text": question.text,
            "status": question.status,
            "participant_ids": sorted(player.pk for player in question.participants.all()),
            "places": list(range(question.first_place, question.last_place + 1)),
            "started_at": question.started_at,
            "deadline": question.deadline,
            "answered_player_ids": sorted(answer.player_id for answer in question.answers.all()),
            "correct_answer": question.correct_answer if finished else None,
            "answers": [
                {"player_id": answer.player_id, "value": answer.numeric_value, "received_at": answer.received_at}
                for answer in question.answers.all()
            ]
            if finished
            else None,
        }
        if question.status == RoundQuestion.Status.ACTIVE:
            item["remaining"] = max(question.deadline - now, timedelta(0))
            current = item
        questions.append(item)

    return {
        "round_id": round_.pk,
        "number": round_.number,
        "type": round_.type,
        "status": round_.status,
        "participant_ids": sorted(round_.participants.values_list("pk", flat=True)),
        "places_needed": round_.places_needed,
        "ranking": dict(round_.placements.values_list("place", "player_id")),
        "winner_id": round_.winner_id,
        "unresolved_reason": round_.unresolved_reason,
        "completed_at": round_.completed_at,
        "current_question": current,
        "questions": questions,
    }
