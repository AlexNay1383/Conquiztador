from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from games.exceptions import InvalidInputError, InvalidStateError, NotFoundError
from games.models import Player, Round

from .common import get_game_id_for_round, lock_game, require_active


@transaction.atomic
def create_round(game_id, round_type):
    game = lock_game(game_id)
    require_active(game)
    if round_type not in Round.Type.values:
        raise InvalidInputError("Невалиден тип рунд.", "invalid_round_type")
    if game.rounds.exclude(status=Round.Status.COMPLETED).exists():
        raise InvalidStateError("Предишният рунд още не е завършен.", "round_in_progress")

    last_number = game.rounds.aggregate(last=Max("number"))["last"] or 0
    return Round.objects.create(game=game, number=last_number + 1, type=round_type)


def _lock_round(round_id):
    game = lock_game(get_game_id_for_round(round_id))
    require_active(game)
    return Round.objects.select_for_update().get(pk=round_id)


@transaction.atomic
def start_round(round_id):
    round_ = _lock_round(round_id)
    if round_.status != Round.Status.PENDING:
        raise InvalidStateError("Рундът вече е започнал.", "round_not_pending")
    round_.status = Round.Status.ACTIVE
    round_.save(update_fields=["status"])
    return round_


@transaction.atomic
def complete_round(round_id, winner_id):
    round_ = _lock_round(round_id)
    if round_.status != Round.Status.ACTIVE:
        raise InvalidStateError("Рундът не е активен.", "round_not_active")
    try:
        winner = Player.objects.get(pk=winner_id)
    except Player.DoesNotExist:
        raise NotFoundError("Играчът не съществува.", "player_not_found") from None
    if winner.game_id != round_.game_id:
        raise InvalidInputError("Победителят трябва да е играч от същата игра.", "winner_not_in_game")

    round_.status = Round.Status.COMPLETED
    round_.winner = winner
    round_.completed_at = timezone.now()
    round_.save(update_fields=["status", "winner", "completed_at"])
    return round_
