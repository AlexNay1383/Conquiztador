from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from games import services
from games.exceptions import InvalidInputError, InvalidStateError
from games.models import Game, Round

from .factories import create_game_with_players


class RoundLifecycleTests(TestCase):
    def setUp(self):
        self.game = create_game_with_players(3, status=Game.Status.ACTIVE)
        self.player = self.game.players.first()

    def test_create_round(self):
        round_ = services.create_round(self.game.pk, Round.Type.CITY_CAPTURE)

        self.assertEqual(round_.game, self.game)
        self.assertEqual(round_.number, 1)
        self.assertEqual(round_.type, Round.Type.CITY_CAPTURE)
        self.assertEqual(round_.status, Round.Status.PENDING)
        self.assertIsNone(round_.winner)
        self.assertIsNone(round_.completed_at)

    def test_complete_round(self):
        round_ = services.create_round(self.game.pk, Round.Type.CITY_CAPTURE)
        services.start_round(round_.pk)

        services.complete_round(round_.pk, self.player.pk)

        round_.refresh_from_db()
        self.assertEqual(round_.status, Round.Status.COMPLETED)
        self.assertEqual(round_.winner, self.player)
        self.assertIsNotNone(round_.completed_at)

    def test_next_round_gets_the_next_number(self):
        first = services.create_round(self.game.pk, Round.Type.CITY_CAPTURE)
        services.start_round(first.pk)
        services.complete_round(first.pk, self.player.pk)

        second = services.create_round(self.game.pk, Round.Type.BATTLE)

        self.assertEqual(second.number, 2)

    def test_new_round_waits_for_the_previous_one(self):
        services.create_round(self.game.pk, Round.Type.CITY_CAPTURE)

        with self.assertRaises(InvalidStateError) as context:
            services.create_round(self.game.pk, Round.Type.CITY_CAPTURE)

        self.assertEqual(context.exception.code, "round_in_progress")

    def test_rounds_require_an_active_game(self):
        waiting = create_game_with_players(3, prefix="waiting")

        with self.assertRaises(InvalidStateError) as context:
            services.create_round(waiting.pk, Round.Type.CITY_CAPTURE)

        self.assertEqual(context.exception.code, "game_not_active")

    def test_lifecycle_order_is_enforced(self):
        round_ = services.create_round(self.game.pk, Round.Type.CITY_CAPTURE)

        with self.assertRaises(InvalidStateError):
            services.complete_round(round_.pk, self.player.pk)
        services.start_round(round_.pk)
        with self.assertRaises(InvalidStateError):
            services.start_round(round_.pk)

    def test_unknown_round_type_is_refused(self):
        with self.assertRaises(InvalidInputError):
            services.create_round(self.game.pk, "duel")


class RoundWinnerTests(TestCase):
    def test_winner_from_another_game_is_refused(self):
        game = create_game_with_players(3, status=Game.Status.ACTIVE)
        stranger = create_game_with_players(3, prefix="other", status=Game.Status.ACTIVE).players.first()
        round_ = services.create_round(game.pk, Round.Type.CITY_CAPTURE)
        services.start_round(round_.pk)

        with self.assertRaises(InvalidInputError) as context:
            services.complete_round(round_.pk, stranger.pk)

        self.assertEqual(context.exception.code, "winner_not_in_game")
        round_.refresh_from_db()
        self.assertEqual(round_.status, Round.Status.ACTIVE)
        self.assertIsNone(round_.winner)

    def test_model_validation_rejects_winner_from_another_game(self):
        game = create_game_with_players(3, status=Game.Status.ACTIVE)
        stranger = create_game_with_players(3, prefix="other").players.first()
        round_ = Round(
            game=game,
            number=1,
            type=Round.Type.BATTLE,
            status=Round.Status.COMPLETED,
            winner=stranger,
            completed_at=timezone.now(),
        )

        with self.assertRaises(ValidationError) as context:
            round_.full_clean()

        self.assertIn("winner", context.exception.message_dict)


class CurrentRoundTests(TestCase):
    def test_current_round_has_the_highest_number(self):
        game = create_game_with_players(3, status=Game.Status.ACTIVE)
        now = timezone.now()
        Round.objects.create(game=game, number=2, type=Round.Type.BATTLE, status="completed", completed_at=now)
        latest = Round.objects.create(game=game, number=3, type=Round.Type.BONUS)
        Round.objects.create(game=game, number=1, type=Round.Type.CITY_CAPTURE, status="completed", completed_at=now)

        self.assertEqual(game.get_current_round(), latest)

    def test_game_without_rounds_has_no_current_round(self):
        game = create_game_with_players(3, status=Game.Status.ACTIVE)

        self.assertIsNone(game.get_current_round())


class RoundConstraintTests(TestCase):
    def setUp(self):
        self.game = create_game_with_players(3, status=Game.Status.ACTIVE)

    def assert_rejected(self, **fields):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Round.objects.create(game=self.game, **fields)

    def test_number_is_unique_per_game(self):
        Round.objects.create(game=self.game, number=1, type=Round.Type.CITY_CAPTURE)

        self.assert_rejected(number=1, type=Round.Type.BATTLE)

    def test_at_most_one_active_round(self):
        Round.objects.create(game=self.game, number=1, type=Round.Type.CITY_CAPTURE, status="active")

        self.assert_rejected(number=2, type=Round.Type.BATTLE, status="active")

    def test_completion_fields_match_status(self):
        winner = self.game.players.first()
        self.assert_rejected(number=1, type=Round.Type.BATTLE, status="completed")
        self.assert_rejected(number=1, type=Round.Type.BATTLE, completed_at=timezone.now())
        self.assert_rejected(number=1, type=Round.Type.BATTLE, winner=winner)

    def test_unknown_choices_are_rejected(self):
        self.assert_rejected(number=1, type="duel")
        self.assert_rejected(number=1, type=Round.Type.BATTLE, status="paused")
