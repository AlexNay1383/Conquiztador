from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from games import services
from games.exceptions import InvalidStateError
from games.models import Game, Round

from .factories import create_active_game, create_game_with_players, create_numeric_questions, use_capture_rights


class RoundLifecycleTests(TestCase):
    def setUp(self):
        self.game, self.players = create_active_game()
        create_numeric_questions(10, 20, 30)

    def finish(self, round_):
        services.start_round(round_.pk)
        for offset, player in enumerate(self.players):
            question = round_.get_current_question()
            services.submit_answer(round_.pk, player.pk, question.correct_answer + offset)

    def test_create_round(self):
        round_ = services.create_city_capture_round(self.game.pk)

        self.assertEqual((round_.game, round_.number, round_.type), (self.game, 1, Round.Type.CITY_CAPTURE))
        self.assertEqual(round_.status, Round.Status.PENDING)
        self.assertIsNone(round_.winner)
        self.assertIsNone(round_.completed_at)

    def test_next_round_gets_the_next_number(self):
        first = services.create_city_capture_round(self.game.pk)
        self.finish(first)
        use_capture_rights(self.game)

        second = services.create_city_capture_round(self.game.pk)

        self.assertEqual(second.number, 2)

    def test_new_round_waits_for_the_previous_one(self):
        services.create_city_capture_round(self.game.pk)

        with self.assertRaises(InvalidStateError) as context:
            services.create_city_capture_round(self.game.pk)

        self.assertEqual(context.exception.code, "round_in_progress")

    def test_rounds_require_an_active_game(self):
        waiting = create_game_with_players(3, prefix="waiting")

        with self.assertRaises(InvalidStateError) as context:
            services.create_city_capture_round(waiting.pk)

        self.assertEqual(context.exception.code, "game_not_active")

    def test_lifecycle_order_is_enforced(self):
        round_ = services.create_city_capture_round(self.game.pk)
        services.start_round(round_.pk)

        with self.assertRaises(InvalidStateError) as context:
            services.start_round(round_.pk)

        self.assertEqual(context.exception.code, "round_not_pending")


class RoundWinnerTests(TestCase):
    def test_model_validation_rejects_winner_from_another_game(self):
        game = create_game_with_players(3, status=Game.Status.ACTIVE)
        stranger = create_game_with_players(3, prefix="other").players.first()
        round_ = Round(
            game=game,
            number=1,
            type=Round.Type.BONUS,
            status=Round.Status.COMPLETED,
            winner=stranger,
            started_at=timezone.now(),
            completed_at=timezone.now(),
        )

        with self.assertRaises(ValidationError) as context:
            round_.full_clean()

        self.assertIn("winner", context.exception.message_dict)


class CurrentRoundTests(TestCase):
    def test_current_round_has_the_highest_number(self):
        game = create_game_with_players(3, status=Game.Status.ACTIVE)
        winner = game.players.first()
        now = timezone.now()
        done = dict(status="completed", winner=winner, started_at=now, completed_at=now)
        Round.objects.create(game=game, number=2, type=Round.Type.BONUS, **done)
        latest = Round.objects.create(game=game, number=3, type=Round.Type.BONUS)
        Round.objects.create(game=game, number=1, type=Round.Type.CITY_CAPTURE, **done)

        self.assertEqual(game.get_current_round(), latest)

    def test_game_without_rounds_has_no_current_round(self):
        game = create_game_with_players(3, status=Game.Status.ACTIVE)

        self.assertIsNone(game.get_current_round())


class RoundConstraintTests(TestCase):
    def setUp(self):
        self.game = create_game_with_players(3, status=Game.Status.ACTIVE)
        self.winner = self.game.players.first()
        self.now = timezone.now()

    def assert_rejected(self, **fields):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Round.objects.create(game=self.game, **fields)

    def test_number_is_unique_per_game(self):
        Round.objects.create(game=self.game, number=1, type=Round.Type.CITY_CAPTURE)

        self.assert_rejected(number=1, type=Round.Type.BONUS)

    def test_at_most_one_unfinished_round(self):
        Round.objects.create(game=self.game, number=1, type=Round.Type.CITY_CAPTURE)

        self.assert_rejected(number=2, type=Round.Type.BONUS)
        self.assert_rejected(number=2, type=Round.Type.BONUS, status="active", started_at=self.now)

    def test_lifecycle_fields_match_status(self):
        cases = [
            dict(status="completed", started_at=self.now, winner=self.winner),
            dict(completed_at=self.now),
            dict(winner=self.winner),
            dict(started_at=self.now),
            dict(status="active"),
            dict(unresolved_reason="question_limit"),
        ]
        for fields in cases:
            with self.subTest(**{key: str(value) for key, value in fields.items()}):
                self.assert_rejected(number=1, type=Round.Type.BONUS, **fields)

    def test_completed_round_without_winner_needs_a_reason(self):
        completed = dict(status="completed", started_at=self.now, completed_at=self.now)
        self.assert_rejected(number=1, type=Round.Type.BONUS, **completed)

        Round.objects.create(
            game=self.game, number=1, type=Round.Type.BONUS, unresolved_reason="question_limit", **completed
        )

    def test_unknown_choices_are_rejected(self):
        self.assert_rejected(number=1, type="duel")
        self.assert_rejected(number=1, type=Round.Type.BONUS, status="paused")
        self.assert_rejected(number=1, type=Round.Type.BONUS, unresolved_reason="bored")
