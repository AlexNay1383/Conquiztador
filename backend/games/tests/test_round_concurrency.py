from django.test import TransactionTestCase

from games import services
from games.exceptions import InvalidStateError
from games.models import RoundAnswer

from .concurrency import run_concurrently
from .factories import create_active_game, create_numeric_questions


class ConcurrentAnswerTests(TransactionTestCase):
    def setUp(self):
        self.game, self.players = create_active_game()
        create_numeric_questions(100, 200, 300)
        self.round = services.create_city_capture_round(self.game.pk)
        services.start_round(self.round.pk)

    def test_one_player_answering_twice_at_once_gets_one_answer(self):
        player = self.players[0]

        results = run_concurrently(
            lambda: services.submit_answer(self.round.pk, player.pk, 1),
            lambda: services.submit_answer(self.round.pk, player.pk, 2),
        )

        self.assertEqual(sorted(kind for kind, _ in results), ["error", "ok"])
        error = next(value for kind, value in results if kind == "error")
        self.assertIsInstance(error, InvalidStateError)
        self.assertEqual(error.code, "already_answered")
        self.assertEqual(RoundAnswer.objects.filter(player=player).count(), 1)

    def test_last_two_answers_at_once_close_the_question_once(self):
        services.submit_answer(self.round.pk, self.players[0].pk, 5)

        results = run_concurrently(
            lambda: services.submit_answer(self.round.pk, self.players[1].pk, 6),
            lambda: services.submit_answer(self.round.pk, self.players[2].pk, 7),
        )

        self.assertEqual([kind for kind, _ in results], ["ok", "ok"])
        self.round.refresh_from_db()
        self.assertEqual(self.round.status, "completed")
        self.assertEqual(self.round.questions.count(), 1)
        self.assertEqual(self.round.placements.count(), 2)
