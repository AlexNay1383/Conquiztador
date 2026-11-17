from django.test import TransactionTestCase

from games import services
from games.exceptions import InvalidStateError
from games.models import Capital, CaptureRight, Territory

from .concurrency import run_concurrently
from .factories import create_active_game, create_numeric_questions


class ConcurrentCaptureTests(TransactionTestCase):
    def setUp(self):
        self.game, players = create_active_game()
        self.a, self.b, _ = (player.pk for player in players)
        create_numeric_questions(100)
        round_ = services.create_city_capture_round(self.game.pk)
        services.start_round(round_.pk)
        for offset, player in enumerate(players):
            services.submit_answer(round_.pk, player.pk, 100 + offset)

    def free_neighbors(self, player_id):
        capital = Capital.objects.get(player_id=player_id).territory
        return list(capital.neighbors.filter(owner__isnull=True).order_by("slug"))

    def test_same_free_territory_is_captured_once(self):
        target = self.free_neighbors(self.a)[0]

        results = run_concurrently(
            lambda: services.capture_territory(self.game.pk, self.a, target.pk),
            lambda: services.capture_territory(self.game.pk, self.a, target.pk),
        )

        self.assertEqual(sorted(kind for kind, _ in results), ["error", "ok"])
        error = next(value for kind, value in results if kind == "error")
        self.assertIsInstance(error, InvalidStateError)
        self.assertEqual(error.code, "territory_not_free")
        self.assertEqual(CaptureRight.objects.get(player_id=self.a).used, 1)
        self.assertEqual(Territory.objects.get(pk=target.pk).score, 100)

    def test_last_right_is_used_once(self):
        for target in self.free_neighbors(self.a)[:2]:
            services.capture_territory(self.game.pk, self.a, target.pk)
        first, second = self.free_neighbors(self.b)[:2]

        results = run_concurrently(
            lambda: services.capture_territory(self.game.pk, self.b, first.pk),
            lambda: services.capture_territory(self.game.pk, self.b, second.pk),
        )

        self.assertEqual(sorted(kind for kind, _ in results), ["error", "ok"])
        error = next(value for kind, value in results if kind == "error")
        self.assertEqual(error.code, "no_capture_right")
        self.assertEqual(Territory.objects.filter(game=self.game, owner_id=self.b).count(), 2)
