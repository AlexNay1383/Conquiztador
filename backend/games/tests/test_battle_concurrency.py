from django.test import TransactionTestCase

from games import services
from games.models import RoundQuestion, Territory

from .concurrency import run_concurrently
from .factories import create_battle_game, create_choice_questions, create_numeric_questions, use_fake_clock


class ConcurrentFollowUpTests(TransactionTestCase):
    def setUp(self):
        self.game, players = create_battle_game()
        self.a, self.b, _ = (player.pk for player in players)
        self.clock = use_fake_clock(self)
        create_choice_questions(3)
        create_numeric_questions(100, 200)
        target = Territory.objects.get(game=self.game, slug="zhitno-pole")
        self.round = services.create_battle(self.game.pk, self.a, target.pk)
        services.start_round(self.round.pk)
        self.correct_option = self.round.get_current_question().options.get(is_correct=True).source_option_id

    def test_tying_answer_and_explicit_close_create_one_numeric_question(self):
        services.submit_answer(self.round.pk, self.a, self.correct_option)

        results = run_concurrently(
            lambda: services.submit_answer(self.round.pk, self.b, self.correct_option),
            lambda: services.close_question(self.round.pk),
        )

        self.assertEqual(results[0][0], "ok")
        self.assertEqual((results[1][0], results[1][1].code), ("error", "question_still_open"))
        kinds = list(RoundQuestion.objects.filter(round=self.round).order_by("sequence").values_list("kind", flat=True))
        self.assertEqual(kinds, ["choice", "numeric"])

    def test_simultaneous_correct_answers_create_one_numeric_question(self):
        results = run_concurrently(
            lambda: services.submit_answer(self.round.pk, self.a, self.correct_option),
            lambda: services.submit_answer(self.round.pk, self.b, self.correct_option),
        )

        self.assertEqual([kind for kind, _ in results], ["ok", "ok"])
        kinds = list(RoundQuestion.objects.filter(round=self.round).order_by("sequence").values_list("kind", flat=True))
        self.assertEqual(kinds, ["choice", "numeric"])
