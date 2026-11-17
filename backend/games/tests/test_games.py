from django.db import IntegrityError
from django.test import TestCase

from games import services
from games.exceptions import InvalidStateError, NotFoundError
from games.models import Game, Round

from .factories import create_game_with_players, create_user


class GameCreationTests(TestCase):
    def test_new_game_is_waiting_with_creation_time(self):
        game = services.create_game()

        self.assertEqual(game.status, Game.Status.WAITING)
        self.assertIsNotNone(game.created_at)
        self.assertFalse(game.is_active())
        self.assertFalse(game.is_completed())

    def test_status_must_be_a_known_choice(self):
        with self.assertRaises(IntegrityError):
            Game.objects.create(status="paused")


class StartGameTests(TestCase):
    """Activation happens only through initialization; see test_initialization for the map details."""

    def test_game_starts_with_exactly_three_players(self):
        game = create_game_with_players(3)

        services.initialize_game(game.pk)

        game.refresh_from_db()
        self.assertEqual(game.status, Game.Status.ACTIVE)
        self.assertTrue(game.is_active())

    def test_game_does_not_start_with_fewer_players(self):
        game = create_game_with_players(2)

        with self.assertRaises(InvalidStateError) as context:
            services.initialize_game(game.pk)

        self.assertEqual(context.exception.code, "wrong_player_count")
        game.refresh_from_db()
        self.assertEqual(game.status, Game.Status.WAITING)

    def test_game_starts_only_once(self):
        game = create_game_with_players(3)
        services.initialize_game(game.pk)

        with self.assertRaises(InvalidStateError) as context:
            services.initialize_game(game.pk)

        self.assertEqual(context.exception.code, "game_not_waiting")

    def test_missing_game(self):
        with self.assertRaises(NotFoundError):
            services.initialize_game(999_999)


class CompleteGameTests(TestCase):
    def test_active_game_can_be_completed(self):
        game = create_game_with_players(3, status=Game.Status.ACTIVE)

        services.complete_game(game.pk)

        game.refresh_from_db()
        self.assertTrue(game.is_completed())

    def test_completed_game_accepts_no_players_or_rounds(self):
        game = create_game_with_players(2, status=Game.Status.COMPLETED)
        user = create_user("late")

        with self.assertRaises(InvalidStateError):
            services.add_player(game.pk, user.pk)
        with self.assertRaises(InvalidStateError):
            services.create_city_capture_round(game.pk)

    def test_game_with_unfinished_round_cannot_be_completed(self):
        game = create_game_with_players(3, status=Game.Status.ACTIVE)
        Round.objects.create(game=game, number=1, type=Round.Type.CITY_CAPTURE)

        with self.assertRaises(InvalidStateError) as context:
            services.complete_game(game.pk)

        self.assertEqual(context.exception.code, "round_in_progress")
