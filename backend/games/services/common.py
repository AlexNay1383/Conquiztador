from games.exceptions import InvalidStateError, NotFoundError
from games.models import Game, Player, Round


def lock_game(game_id):
    """Lock the game row for the rest of the transaction; every state-changing operation starts here."""
    try:
        return Game.objects.select_for_update().get(pk=game_id)
    except Game.DoesNotExist:
        raise NotFoundError("Играта не съществува.", "game_not_found") from None


def get_game_id_for_round(round_id):
    game_id = Round.objects.filter(pk=round_id).values_list("game_id", flat=True).first()
    if game_id is None:
        raise NotFoundError("Рундът не съществува.", "round_not_found")
    return game_id


def get_game_id_for_player(player_id):
    game_id = Player.objects.filter(pk=player_id).values_list("game_id", flat=True).first()
    if game_id is None:
        raise NotFoundError("Играчът не съществува.", "player_not_found")
    return game_id


def require_status(game, status, code, message):
    if game.status != status:
        raise InvalidStateError(message, code)


def require_active(game):
    require_status(game, Game.Status.ACTIVE, "game_not_active", "Играта не е активна.")


def require_waiting(game):
    require_status(game, Game.Status.WAITING, "game_not_waiting", "Играта вече е започнала.")
