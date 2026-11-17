from django.db import transaction
from django.db.models import F

from games.exceptions import InvalidInputError, InvalidStateError, NotFoundError
from games.models import CaptureRight, Player, Territory

from .common import lock_game, require_active
from .scoring import award_capture, free_territories, raise_territory_score


def pending_capture_rights(game):
    return CaptureRight.objects.filter(round__game=game, used__lt=F("allowed")).order_by("round__number", "order")


def require_no_pending_rights(game):
    if pending_capture_rights(game).exists():
        raise InvalidStateError("Има неизползвани права за избор на територия.", "capture_rights_pending")


def eligible_capture_targets(game, player):
    """Free territories adjacent to anything the player owns; any free territory if none is adjacent."""
    owned = Territory.objects.filter(game=game, owner=player).values("pk")
    free = free_territories(game)
    adjacent = free.filter(neighbors__in=owned).distinct()
    return adjacent if adjacent.exists() else free


def get_capture_options(game_id, player_id):
    """Read-only: the territories the player may pick right now, or an empty list when it is not their turn."""
    right = pending_capture_rights(game_id).first()
    if right is None or right.player_id != player_id:
        return []
    player = Player.objects.get(pk=player_id)
    return list(eligible_capture_targets(player.game, player).order_by("slug"))


def _get_player(game, player_id):
    player = Player.objects.filter(pk=player_id).first()
    if player is None:
        raise NotFoundError("Играчът не съществува.", "player_not_found")
    if player.game_id != game.pk:
        raise InvalidInputError("Играчът не участва в тази игра.", "player_not_in_game")
    return player


def _get_territory(game, territory_id):
    territory = Territory.objects.select_for_update().filter(pk=territory_id).first()
    if territory is None:
        raise NotFoundError("Територията не съществува.", "territory_not_found")
    if territory.game_id != game.pk:
        raise InvalidInputError("Територията не е от тази игра.", "territory_not_in_game")
    return territory


@transaction.atomic
def capture_territory(game_id, player_id, territory_id):
    """Use one capture right: take a free territory, raise its value and award the capture points."""
    game = lock_game(game_id)
    require_active(game)
    player = _get_player(game, player_id)

    right = pending_capture_rights(game).select_for_update(of=("self",)).first()
    if right is None or not pending_capture_rights(game).filter(player=player).exists():
        raise InvalidStateError("Нямате право да изберете територия.", "no_capture_right")
    if right.player_id != player.pk:
        raise InvalidStateError("Не е ваш ред да избирате.", "not_your_turn")

    territory = _get_territory(game, territory_id)
    if territory.owner_id is not None:
        raise InvalidStateError("Територията вече е завзета.", "territory_not_free")
    if not eligible_capture_targets(game, player).filter(pk=territory.pk).exists():
        raise InvalidInputError("Територията не е съседна на ваше владение.", "territory_not_adjacent")

    score_before = raise_territory_score(territory)
    territory.owner = player
    territory.save(update_fields=["owner", "score"])
    award_capture(right.round, player.pk, territory, score_before)
    right.used += 1
    right.save(update_fields=["used"])
    return territory
