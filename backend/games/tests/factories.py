from django.contrib.auth import get_user_model

from games.map_definition import PROJECT_MAP
from games.models import Capital, Game, Player, Territory

COLORS = [Player.Color.RED, Player.Color.GREEN, Player.Color.BLUE]


def create_user(username):
    return get_user_model().objects.create_user(
        username=username, email=f"{username}@example.com", password="Strong-pass-2024"
    )


def create_game_with_players(count=3, prefix="player", status=Game.Status.WAITING):
    """Create a game with `count` players directly, bypassing the services under test."""
    game = Game.objects.create(status=status)
    for index in range(count):
        user = create_user(f"{prefix}{game.pk}_{index}")
        Player.objects.create(game=game, user=user, color=COLORS[index])
    return game


def build_map(game, definition=PROJECT_MAP):
    """Create the game's territories and edges directly; returns territories by slug."""
    territories = {
        item.slug: Territory.objects.create(game=game, slug=item.slug, name=item.name)
        for item in definition.territories
    }
    for first, second in definition.edges:
        territories[first].neighbors.add(territories[second])
    return territories


def assign_capitals(game, territories, slugs):
    for player, slug in zip(game.players.order_by("pk"), slugs):
        territory = territories[slug]
        territory.owner = player
        territory.save(update_fields=["owner"])
        Capital.objects.create(territory=territory, player=player)
