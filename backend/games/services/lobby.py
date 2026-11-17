from django.contrib.auth import get_user_model
from django.db import transaction

from games.exceptions import InvalidInputError, InvalidStateError, NotFoundError
from games.models import Game, Player

from .common import get_game_id_for_player, lock_game, require_active, require_waiting


def create_game():
    return Game.objects.create()


@transaction.atomic
def add_player(game_id, user_id, color=None):
    """Add a user to a waiting game. Without `color`, the first free color is assigned."""
    game = lock_game(game_id)
    require_waiting(game)

    if not get_user_model().objects.filter(pk=user_id).exists():
        raise NotFoundError("Потребителят не съществува.", "user_not_found")

    players = list(game.players.all())
    if len(players) >= Game.PLAYER_COUNT:
        raise InvalidStateError("Играта вече има трима играчи.", "game_full")
    if any(player.user_id == user_id for player in players):
        raise InvalidInputError("Потребителят вече участва в играта.", "user_already_joined")

    taken_colors = {player.color for player in players}
    if color is None:
        color = next(value for value in Player.Color.values if value not in taken_colors)
    elif color not in Player.Color.values:
        raise InvalidInputError("Невалиден цвят.", "invalid_color")
    elif color in taken_colors:
        raise InvalidInputError("Цветът вече е зает.", "color_taken")

    return Player.objects.create(game=game, user_id=user_id, color=color)


@transaction.atomic
def remove_player(player_id):
    game = lock_game(get_game_id_for_player(player_id))
    require_waiting(game)
    deleted, _ = Player.objects.filter(pk=player_id, game=game).delete()
    if not deleted:
        raise NotFoundError("Играчът не съществува.", "player_not_found")


@transaction.atomic
def complete_game(game_id):
    game = lock_game(game_id)
    require_active(game)
    if game.rounds.exclude(status="completed").exists():
        raise InvalidStateError("Има незавършен рунд.", "round_in_progress")
    game.status = Game.Status.COMPLETED
    game.save(update_fields=["status"])
    return game
