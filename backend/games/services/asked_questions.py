"""Questions asked within rounds: drawing from the bank, snapshots, answer parsing and evaluation per kind."""

import re
from datetime import timedelta

from games.exceptions import InvalidInputError
from games.models import RoundQuestion, RoundQuestionOption
from games.ranking import NumericAnswer, rank_choice, rank_numeric
from questions.models import ChoiceQuestion, NumericQuestion

ANSWER_WINDOW = timedelta(seconds=10)
INTEGER_PATTERN = re.compile(r"[+-]?\d+")
MAX_ANSWER_MAGNITUDE = 2**63 - 1

NUMERIC = RoundQuestion.Kind.NUMERIC
CHOICE = RoundQuestion.Kind.CHOICE


def pick_question(game, kind, rng):
    """A random bank question of `kind` not yet asked in this game; the two kinds are tracked separately."""
    if kind == NUMERIC:
        used = RoundQuestion.objects.filter(game=game, numeric_question__isnull=False).values("numeric_question_id")
        candidates = NumericQuestion.objects.exclude(pk__in=used)
    else:
        used = RoundQuestion.objects.filter(game=game, choice_question__isnull=False).values("choice_question_id")
        candidates = ChoiceQuestion.objects.playable().exclude(pk__in=used)
    ids = list(candidates.values_list("pk", flat=True))
    if not ids:
        return None
    return candidates.model.objects.get(pk=rng.choice(ids))


def add_question(round_, sequence, kind, source, player_ids, first_place, place_count, start_at=None):
    fields = {"numeric_question": source, "correct_answer": source.correct_answer} if kind == NUMERIC else {
        "choice_question": source
    }
    question = RoundQuestion.objects.create(
        round=round_,
        game_id=round_.game_id,
        sequence=sequence,
        kind=kind,
        text=source.text,
        first_place=first_place,
        place_count=place_count,
        **fields,
    )
    question.participants.set(player_ids)
    if kind == CHOICE:
        RoundQuestionOption.objects.bulk_create(
            RoundQuestionOption(
                question=question,
                source_option=option,
                position=position,
                text=option.text,
                is_correct=option.is_correct,
            )
            for position, option in enumerate(source.options.order_by("pk"), start=1)
        )
    if start_at is not None:
        activate_question(question, start_at)
    return question


def activate_question(question, now):
    question.status = RoundQuestion.Status.ACTIVE
    question.started_at = now
    question.deadline = now + ANSWER_WINDOW
    question.save(update_fields=["status", "started_at", "deadline"])


def parse_integer(value, message):
    if isinstance(value, bool):
        value = None
    elif isinstance(value, str) and INTEGER_PATTERN.fullmatch(value.strip()):
        value = int(value.strip())
    if not isinstance(value, int) or abs(value) > MAX_ANSWER_MAGNITUDE:
        raise InvalidInputError(message, "invalid_answer")
    return value


def parse_answer(question, value):
    """Turn raw input into answer fields. A choice answer is the id of one of this question's bank options."""
    if question.kind == NUMERIC:
        return {"numeric_value": parse_integer(value, "Отговорът трябва да е цяло число.")}

    option_id = parse_integer(value, "Изберете един от отговорите.")
    option = question.options.filter(source_option_id=option_id).first()
    if option is None:
        raise InvalidInputError("Този отговор не е от текущия въпрос.", "invalid_option")
    return {"option": option}


def evaluate_question(question):
    group = list(question.participants.values_list("pk", flat=True))
    answers = list(question.answers.select_related("option"))
    if question.kind == CHOICE:
        correct = [answer.player_id for answer in answers if answer.option.is_correct]
        return rank_choice(correct, group, question.first_place)
    numeric = [NumericAnswer(answer.player_id, answer.numeric_value, answer.received_at) for answer in answers]
    return rank_numeric(numeric, question.correct_answer, group, question.first_place, question.place_count)


def describe_question(question, finished):
    """Serializable view of an asked question; answers and solutions are revealed only once it is finished."""
    answers = list(question.answers.all())
    item = {
        "sequence": question.sequence,
        "kind": question.kind,
        "text": question.text,
        "status": question.status,
        "participant_ids": sorted(player.pk for player in question.participants.all()),
        "places": list(range(question.first_place, question.last_place + 1)),
        "started_at": question.started_at,
        "deadline": question.deadline,
        "answered_player_ids": sorted(answer.player_id for answer in answers),
        "correct_answer": question.correct_answer if finished else None,
        "answers": None,
    }
    if question.kind == CHOICE:
        options = list(question.options.all())
        item["options"] = [{"id": option.source_option_id, "text": option.text} for option in options]
        if finished:
            item["correct_answer"] = next(option.source_option_id for option in options if option.is_correct)
    if finished:
        item["answers"] = [
            {
                "player_id": answer.player_id,
                "value": answer.numeric_value if answer.option_id is None else answer.option.source_option_id,
                "received_at": answer.received_at,
            }
            for answer in answers
        ]
    return item
