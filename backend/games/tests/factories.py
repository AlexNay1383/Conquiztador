import random
from datetime import UTC, datetime, timedelta
from unittest import mock

from django.contrib.auth import get_user_model

from games.map_definition import PROJECT_MAP
from games.models import Capital, Game, Player, Territory
from games.services import capture_territory, get_capture_options, initialize_game
from games.services.capture import pending_capture_rights
from questions.models import AnswerOption, Category, ChoiceQuestion, NumericQuestion

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


def use_capture_rights(game):
    """Spend every pending capture right on the first territory each player may pick."""
    while (right := pending_capture_rights(game).first()) is not None:
        target = get_capture_options(game.pk, right.player_id)[0]
        capture_territory(game.pk, right.player_id, target.pk)


def create_choice_questions(count, first_pk=None):
    """Choice questions whose options are "A".."D" with "A" correct."""
    category = Category.objects.get_or_create(name="Тестова")[0]
    questions = []
    for index in range(count):
        pk = None if first_pk is None else first_pk + index
        question = ChoiceQuestion.objects.create(pk=pk, category=category, text=f"Въпрос с избор {index + 1}?")
        for letter in "ABCD":
            AnswerOption.objects.create(question=question, text=letter, is_correct=letter == "A")
        questions.append(question)
    return questions


BATTLE_OWNERS = {
    0: ["skali", "dunavia", "sredets", "balkania", "pirina", "ezera"],
    1: ["kaliakra", "zhitno-pole", "madara", "zlaten-grozd", "pelikania", "tsarevo"],
    2: ["rozova-dolina", "leventa", "chuden-krai"],
}
BATTLE_CAPITALS = ["skali", "kaliakra", "rozova-dolina"]


def create_battle_game(prefix="player"):
    """An active game whose map is fully owned; players[i] owns BATTLE_OWNERS[i], capitals first."""
    game = create_game_with_players(3, prefix=prefix, status=Game.Status.ACTIVE)
    territories = build_map(game)
    assign_capitals(game, territories, BATTLE_CAPITALS)
    players = list(game.players.order_by("pk"))
    for index, slugs in BATTLE_OWNERS.items():
        Territory.objects.filter(game=game, slug__in=slugs).update(owner=players[index])
    return game, players
