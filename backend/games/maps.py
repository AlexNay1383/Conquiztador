"""Validation of map definitions and per-game maps, plus read-only access to territories.

Nothing in this module creates or changes records.
"""

import itertools
import re
from collections import deque

from django.db.models import Q

from .map_definition import PROJECT_MAP
from .models import (
    SLUG_PATTERN,
    Capital,
    Game,
    Territory,
    normalize_territory_name,
    normalize_territory_slug,
    territory_name_key,
)

MIN_TERRITORIES = 9
MAX_TERRITORIES = 21
CAPITAL_COUNT = 3


class MapValidationError(Exception):
    def __init__(self, problems):
        super().__init__("; ".join(problems))
        self.problems = list(problems)


def edge_key(first, second):
    return frozenset((first, second))


def definition_adjacency(definition):
    """Adjacency sets of a definition, silently skipping edges that `check_definition` reports."""
    adjacency = {territory.slug: set() for territory in definition.territories}
    for first, second in definition.edges:
        if first in adjacency and second in adjacency and first != second:
            adjacency[first].add(second)
            adjacency[second].add(first)
    return adjacency


def find_capital_triples(adjacency):
    """All sets of three territories with no edge between any two of them."""
    return [
        triple
        for triple in itertools.combinations(sorted(adjacency), CAPITAL_COUNT)
        if all(second not in adjacency[first] for first, second in itertools.combinations(triple, 2))
    ]


def _is_connected(adjacency):
    start = next(iter(adjacency))
    seen = {start}
    queue = deque([start])
    while queue:
        for neighbor in adjacency[queue.popleft()]:
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    return len(seen) == len(adjacency)


def check_definition(definition=PROJECT_MAP):
    problems = []
    count = len(definition.territories)
    if not MIN_TERRITORIES <= count <= MAX_TERRITORIES or count % 3:
        problems.append(f"The map has {count} territories; expected 9-21 and a multiple of 3.")

    slugs, name_keys = set(), set()
    for territory in definition.territories:
        if not re.fullmatch(SLUG_PATTERN, territory.slug or "") or normalize_territory_slug(territory.slug) != territory.slug:
            problems.append(f"Invalid slug {territory.slug!r}.")
        if not territory.name or normalize_territory_name(territory.name) != territory.name:
            problems.append(f"Invalid name {territory.name!r}.")
        if territory.slug in slugs:
            problems.append(f"Duplicate slug {territory.slug!r}.")
        if territory_name_key(territory.name) in name_keys:
            problems.append(f"Duplicate name {territory.name!r}.")
        slugs.add(territory.slug)
        name_keys.add(territory_name_key(territory.name))

    seen_edges = set()
    for first, second in definition.edges:
        if first not in slugs or second not in slugs:
            problems.append(f"Edge {first}-{second} references an unknown territory.")
        elif first == second:
            problems.append(f"Territory {first!r} is listed as its own neighbour.")
        elif edge_key(first, second) in seen_edges:
            problems.append(f"Edge {first}-{second} is listed more than once.")
        seen_edges.add(edge_key(first, second))

    adjacency = definition_adjacency(definition)
    for slug, neighbors in adjacency.items():
        if len(neighbors) < 2:
            problems.append(f"Territory {slug!r} has fewer than two neighbours.")
    if adjacency and not _is_connected(adjacency):
        problems.append("The map is not connected.")
    if adjacency and not find_capital_triples(adjacency):
        problems.append("No three mutually non-adjacent territories exist for the capitals.")
    return problems


def validate_definition(definition=PROJECT_MAP):
    problems = check_definition(definition)
    if problems:
        raise MapValidationError(problems)


def check_game_map(game, definition=PROJECT_MAP):
    """Compare a game's records with the definition. An empty map is reported as incomplete."""
    territories = list(Territory.objects.filter(game=game))
    if not territories:
        return ["The game has no territories."]

    problems = []
    expected = {territory.slug: territory.name for territory in definition.territories}
    actual = {territory.slug: territory.name for territory in territories}
    for slug in sorted(expected.keys() - actual.keys()):
        problems.append(f"Territory {slug!r} is missing.")
    for slug in sorted(actual.keys() - expected.keys()):
        problems.append(f"Territory {slug!r} is not part of the map.")
    for slug in sorted(expected.keys() & actual.keys()):
        if expected[slug] != actual[slug]:
            problems.append(f"Territory {slug!r} is named {actual[slug]!r} instead of {expected[slug]!r}.")

    slug_by_id = {territory.pk: territory.slug for territory in territories}
    links = Territory.neighbors.through.objects.filter(
        Q(from_territory__game=game) | Q(to_territory__game=game)
    ).values_list("from_territory_id", "to_territory_id")
    directed = set()
    for from_id, to_id in links:
        if from_id not in slug_by_id or to_id not in slug_by_id:
            problems.append("A neighbour link points to a territory of another game.")
        elif from_id == to_id:
            problems.append(f"Territory {slug_by_id[from_id]!r} is its own neighbour.")
        else:
            directed.add((slug_by_id[from_id], slug_by_id[to_id]))
    for first, second in sorted(directed):
        if (second, first) not in directed:
            problems.append(f"Neighbour link {first}-{second} is not symmetric.")

    actual_edges = {edge_key(first, second) for first, second in directed}
    expected_edges = {edge_key(first, second) for first, second in definition.edges}
    for edge in sorted(expected_edges - actual_edges, key=sorted):
        problems.append(f"Edge {'-'.join(sorted(edge))} is missing.")
    for edge in sorted(actual_edges - expected_edges, key=sorted):
        problems.append(f"Edge {'-'.join(sorted(edge))} is not part of the map.")

    player_ids = set(game.players.values_list("pk", flat=True))
    for territory in territories:
        if territory.owner_id is not None and territory.owner_id not in player_ids:
            problems.append(f"Territory {territory.slug!r} is owned by a player of another game.")

    problems.extend(_check_capitals(game, player_ids, definition))
    return problems


def _check_capitals(game, player_ids, definition):
    problems = []
    capitals = list(
        Capital.objects.filter(Q(territory__game=game) | Q(player__game=game)).select_related("territory", "player")
    )
    for capital in capitals:
        if capital.territory.game_id != game.pk or capital.player.game_id != game.pk:
            problems.append(f"Capital {capital.pk} links records of different games.")
        elif capital.territory.owner_id != capital.player_id:
            problems.append(f"Capital {capital.territory.slug!r} is not owned by its player.")

    if game.status == Game.Status.WAITING:
        return problems
    if len(capitals) != CAPITAL_COUNT or {capital.player_id for capital in capitals} != player_ids:
        problems.append("Every player must have exactly one capital.")
        return problems
    adjacency = definition_adjacency(definition)
    capital_slugs = [capital.territory.slug for capital in capitals]
    for first, second in itertools.combinations(capital_slugs, 2):
        if second in adjacency.get(first, ()):
            problems.append(f"Capitals {first!r} and {second!r} are adjacent.")
    return problems


def validate_game_map(game, definition=PROJECT_MAP):
    problems = check_game_map(game, definition)
    if problems:
        raise MapValidationError(problems)


def get_game_territories(game):
    return Territory.objects.filter(game=game).select_related("owner").prefetch_related("neighbors")


def get_player_territories(player):
    return Territory.objects.filter(owner=player)


def get_player_capital(player):
    """The player's capital, or None when the player has none yet. Never creates one."""
    return Capital.objects.filter(player=player).select_related("territory").first()
