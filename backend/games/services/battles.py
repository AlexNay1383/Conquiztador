import random

from django.db import transaction

from games.exceptions import InvalidInputError, InvalidStateError, NotFoundError
from games.models import Capital, Player, Round, Territory

from .asked_questions import CHOICE, add_question, pick_question
from .capture import require_no_pending_rights
from .common import lock_game, require_active
from .rounds import next_round_number, require_no_open_round
from .scoring import free_territories


def _get_attacker(game, attacker_id):
    attacker = Player.objects.filter(pk=attacker_id).first()
    if attacker is None:
        raise NotFoundError("Играчът не съществува.", "player_not_found")
    if attacker.game_id != game.pk:
        raise InvalidInputError("Играчът не участва в тази игра.", "player_not_in_game")
    return attacker


def _get_target(game, attacker, target_id, defender_id):
    target = Territory.objects.select_for_update().filter(pk=target_id).first()
    if target is None:
        raise NotFoundError("Територията не съществува.", "territory_not_found")
    if target.game_id != game.pk:
        raise InvalidInputError("Територията не е от тази игра.", "territory_not_in_game")
    if target.owner_id is None:
        raise InvalidInputError("Свободна територия не може да бъде атакувана.", "target_is_free")
    if target.owner_id == attacker.pk:
        raise InvalidInputError("Не можете да атакувате своя територия.", "target_is_own")
    if defender_id is not None and defender_id != target.owner_id:
        raise InvalidInputError("Защитникът е собственикът на целта.", "defender_mismatch")
    if not target.neighbors.filter(owner=attacker).exists():
        raise InvalidInputError("Целта не е съседна на ваше владение.", "target_not_adjacent")
    return target


@transaction.atomic
def create_battle(game_id, attacker_id, target_id, defender_id=None, rng=None):
    """Create a pending battle against an adjacent territory of another player.

    The target's owner is the defender; a capital as target makes it a capital attack. The first
    question is a random unused choice question for the attacker and the defender.
    """
    rng = rng or random.Random()
    game = lock_game(game_id)
    require_active(game)
    require_no_open_round(game)
    require_no_pending_rights(game)
    attacker = _get_attacker(game, attacker_id)
    target = _get_target(game, attacker, target_id, defender_id)
    if free_territories(game).exists():
        raise InvalidStateError("Битките започват след завземането на всички територии.", "map_not_full")
    source = pick_question(game, CHOICE, rng)
    if source is None:
        raise InvalidStateError("Няма неизползван въпрос с избор.", "no_question_available")

    is_capital = Capital.objects.filter(territory=target).exists()
    round_ = Round.objects.create(
        game=game,
        number=next_round_number(game),
        type=Round.Type.CAPITAL_ATTACK if is_capital else Round.Type.BATTLE,
        places_needed=1,
        attacker=attacker,
        defender_id=target.owner_id,
        target=target,
    )
    player_ids = [attacker.pk, target.owner_id]
    round_.participants.set(player_ids)
    add_question(round_, 1, CHOICE, source, player_ids, first_place=1, place_count=1)
    return round_
