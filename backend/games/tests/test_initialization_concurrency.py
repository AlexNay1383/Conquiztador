from django.test import TransactionTestCase

from games import services
from games.exceptions import InvalidStateError
from games.models import Capital, Game, Territory

from .concurrency import run_concurrently
from .factories import create_game_with_players


class ConcurrentInitializationTests(TransactionTestCase):
    def test_two_simultaneous_starts_activate_the_game_once(self):
        game = create_game_with_players(3)

        results = run_concurrently(
            lambda: services.initialize_game(game.pk),
            lambda: services.initialize_game(game.pk),
        )

        outcomes = sorted(kind for kind, _ in results)
        self.assertEqual(outcomes, ["error", "ok"])
        error = next(value for kind, value in results if kind == "error")
        self.assertIsInstance(error, InvalidStateError)
        self.assertEqual(error.code, "game_not_waiting")
        self.assertEqual(Territory.objects.filter(game=game).count(), 15)
        self.assertEqual(Capital.objects.filter(player__game=game).count(), 3)

    def test_leaving_player_and_start_cannot_both_succeed(self):
        game = create_game_with_players(3)
        leaving = game.players.first()

        results = run_concurrently(
            lambda: services.initialize_game(game.pk),
            lambda: services.remove_player(leaving.pk),
        )

        game.refresh_from_db()
        started, left = (kind == "ok" for kind, _ in results)
        self.assertNotEqual(started, left)
        if started:
            self.assertEqual(game.status, Game.Status.ACTIVE)
            self.assertEqual(game.players.count(), 3)
            self.assertEqual(Capital.objects.filter(player__game=game).count(), 3)
        else:
            self.assertEqual(game.status, Game.Status.WAITING)
            self.assertEqual(game.players.count(), 2)
            self.assertFalse(Territory.objects.filter(game=game).exists())
