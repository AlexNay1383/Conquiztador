import random
from datetime import UTC, datetime, timedelta
from unittest import mock

from django.contrib.auth import get_user_model

from games.map_definition import PROJECT_MAP
from games.models import Capital, Game, Player, Territory
from games.services import initialize_game
from questions.models import Category, NumericQuestion

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


def create_active_game(prefix="player"):
    """A game initialized through the real service, with its players ordered by primary key."""
    game = create_game_with_players(3, prefix=prefix)
    initialize_game(game.pk, rng=random.Random(0))
    game.refresh_from_db()
    return game, list(game.players.order_by("pk"))


def create_numeric_questions(*correct_answers):
    category = Category.objects.get_or_create(name="Тестова")[0]
    return [
        NumericQuestion.objects.create(category=category, text=f"Въпрос за {value}?", correct_answer=value)
        for value in correct_answers
    ]


class FakeClock:
    """Replacement for `games.clock.now` that only moves when told to."""

    def __init__(self, start=datetime(2026, 1, 1, 12, 0, tzinfo=UTC)):
        self.current = start

    def __call__(self):
        return self.current

    def advance(self, **delta):
        self.current += timedelta(**delta)
        return self.current


def use_fake_clock(test_case):
    fake = FakeClock()
    patcher = mock.patch("games.clock.now", fake)
    patcher.start()
    test_case.addCleanup(patcher.stop)
    return fake
