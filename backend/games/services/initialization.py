import random

from django.db import transaction
from django.db.models import Q

from games.exceptions import InvalidStateError
from games.map_definition import PROJECT_MAP
from games.maps import check_definition, definition_adjacency, find_capital_triples, validate_game_map
from games.models import Capital, Game, Player, Territory

from .common import lock_game, require_waiting


def _check_players(players):
    if len(players) != Game.PLAYER_COUNT:
        raise InvalidStateError("Играта започва само с точно трима играчи.", "wrong_player_count")
    users = {player.user_id for player in players}
    colors = {player.color for player in players}
    if (
        len(users) != len(players)
        or len(colors) != len(players)
        or not colors <= set(Player.Color.values)
        or any(player.score < 0 for player in players)
    ):
        raise InvalidStateError("Играчите на играта са невалидни.", "invalid_players")


def _check_no_map(game):
    has_territories = Territory.objects.filter(game=game).exists()
    has_capitals = Capital.objects.filter(Q(player__game=game) | Q(territory__game=game)).exists()
    if has_territories or has_capitals:
        raise InvalidStateError("Играта вече има (частично) създадена карта.", "map_already_exists")


def _create_map(game, definition):
    territories = Territory.objects.bulk_create(
        Territory(game=game, slug=item.slug, name=item.name) for item in definition.territories
    )
    by_slug = {territory.slug: territory for territory in territories}
    Link = Territory.neighbors.through
    Link.objects.bulk_create(
        Link(from_territory=by_slug[a], to_territory=by_slug[b])
        for first, second in definition.edges
        for a, b in ((first, second), (second, first))
    )
    return by_slug


@transaction.atomic
def initialize_game(game_id, definition=PROJECT_MAP, rng=None):
    """Build the game's map, place three capitals at random and activate the game, all or nothing.

    This is the only operation that moves a game from `waiting` to `active`.
    """
    rng = rng or random.Random()
    game = lock_game(game_id)
    require_waiting(game)
    players = list(Player.objects.select_for_update().filter(game=game).order_by("pk"))
    _check_players(players)
    _check_no_map(game)

    problems = check_definition(definition)
    if problems:
        raise InvalidStateError("Дефиницията на картата е невалидна.", "invalid_map_definition")
    triples = find_capital_triples(definition_adjacency(definition))

    territories = _create_map(game, definition)

    capital_slugs = rng.choice(triples)
    assigned_players = rng.sample(players, len(players))
    capital_territories = []
    for player, slug in zip(assigned_players, capital_slugs):
        territory = territories[slug]
        territory.owner = player
        capital_territories.append(territory)
    Territory.objects.bulk_update(capital_territories, ["owner"])
    Capital.objects.bulk_create(
        Capital(territory=territory, player=territory.owner) for territory in capital_territories
    )

    game.status = Game.Status.ACTIVE
    game.save(update_fields=["status"])
    validate_game_map(game, definition)
    return game
