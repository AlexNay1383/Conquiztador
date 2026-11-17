from django.contrib.auth import get_user_model

from games.models import Game, Player

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
