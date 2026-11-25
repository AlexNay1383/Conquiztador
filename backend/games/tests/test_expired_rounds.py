from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, TransactionTestCase

from games import services
from games.exceptions import InvalidStateError
from games.models import Round, RoundPlacement, RoundQuestion, ScoreEvent

from .concurrency import run_concurrently
from .factories import create_active_game, create_numeric_questions, use_fake_clock


class ExpiredRoundsTestCase:
    def setUp(self):
        self.game, players = create_active_game()
        self.a, self.b, self.c = (player.pk for player in players)
        self.clock = use_fake_clock(self)
        create_numeric_questions(100, 200, 300, 400)
        self.round = services.create_city_capture_round(self.game.pk)
        services.start_round(self.round.pk)
        self.question = self.round.get_current_question()

    def answer(self, player_id, offset):
        return services.submit_answer(self.round.pk, player_id, self.question.correct_answer + offset)

    def expired_ids(self):
        return list(services.expired_questions(self.clock()).values_list("pk", flat=True))

    def run_command(self, *args):
        out, err = StringIO(), StringIO()
        call_command("close_expired_rounds", *args, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()


class ExpiredQuestionQueryTests(ExpiredRoundsTestCase, TestCase):
    def test_question_is_expired_exactly_at_its_deadline(self):
        self.clock.advance(seconds=9.999)
        self.assertEqual(self.expired_ids(), [])

        self.clock.advance(seconds=0.001)
        self.assertEqual(self.expired_ids(), [self.question.pk])

    def test_questions_missed_long_ago_are_found(self):
        self.clock.advance(hours=5)
        self.assertEqual(self.expired_ids(), [self.question.pk])

    def test_closed_questions_are_not_found(self):
        self.answer(self.a, 0)
        self.answer(self.b, 1)
        self.answer(self.c, 2)
        self.clock.advance(seconds=30)
        self.assertEqual(self.expired_ids(), [])

    def test_pending_questions_are_not_found(self):
        other_game, _ = create_active_game(prefix="other")
        services.create_city_capture_round(other_game.pk)
        self.clock.advance(seconds=30)
        self.assertEqual(self.expired_ids(), [self.question.pk])


class CloseExpiredQuestionTests(ExpiredRoundsTestCase, TestCase):
    def test_closing_twice_applies_the_result_once(self):
        self.answer(self.a, 0)
        self.answer(self.b, 5)
        self.clock.advance(seconds=10)

        self.assertTrue(services.close_expired_question(self.question.pk))
        events = ScoreEvent.objects.count()
        self.assertFalse(services.close_expired_question(self.question.pk))

        self.round.refresh_from_db()
        self.assertEqual((self.round.status, self.round.winner_id), (Round.Status.COMPLETED, self.a))
        self.assertEqual(RoundPlacement.objects.filter(round=self.round).count(), 2)
        self.assertEqual(ScoreEvent.objects.count(), events)

    def test_question_closed_by_answers_before_the_deadline_is_skipped(self):
        for player_id, offset in ((self.a, 0), (self.b, 1), (self.c, 2)):
            self.answer(player_id, offset)
        events = ScoreEvent.objects.count()
        self.clock.advance(seconds=10)

        self.assertFalse(services.close_expired_question(self.question.pk))
        self.assertEqual(ScoreEvent.objects.count(), events)

    def test_early_close_is_refused(self):
        self.clock.advance(seconds=5)
        with self.assertRaises(InvalidStateError) as context:
            services.close_expired_question(self.question.pk)
        self.assertEqual(context.exception.code, "question_still_open")

    def test_tie_after_deadline_starts_a_follow_up_with_a_fresh_deadline(self):
        self.answer(self.a, 3)
        self.answer(self.b, -3)
        closed_at = self.clock.advance(minutes=2)

        self.assertTrue(services.close_expired_question(self.question.pk))

        follow_up = self.round.get_current_question()
        self.assertEqual((follow_up.sequence, follow_up.status), (2, RoundQuestion.Status.ACTIVE))
        self.assertEqual(follow_up.started_at, closed_at)
        self.assertEqual(self.expired_ids(), [])


class ConcurrentCloseTests(ExpiredRoundsTestCase, TransactionTestCase):
    def test_two_closers_at_once_apply_the_result_once(self):
        self.answer(self.a, 0)
        self.answer(self.b, 5)
        self.clock.advance(seconds=10)

        results = run_concurrently(
            lambda: services.close_expired_question(self.question.pk),
            lambda: services.close_expired_question(self.question.pk),
        )

        self.assertEqual(sorted(value for _, value in results), [False, True])
        self.assertEqual(RoundPlacement.objects.filter(round=self.round).count(), 2)
        self.assertEqual(ScoreEvent.objects.filter(round=self.round, kind="round_win").count(), 1)


class CommandTests(ExpiredRoundsTestCase, TestCase):
    def test_one_check_reports_processed_and_skipped(self):
        self.answer(self.a, 0)
        self.clock.advance(seconds=10)

        out, _ = self.run_command()
        self.assertIn("processed: 1, skipped: 0", out)
        self.round.refresh_from_db()
        self.assertEqual(self.round.status, Round.Status.COMPLETED)

        out, _ = self.run_command()
        self.assertIn("processed: 0, skipped: 0", out)

    def test_question_closed_meanwhile_is_counted_as_skipped(self):
        self.clock.advance(seconds=10)
        with mock.patch("games.services.close_expired_question", return_value=False):
            out, _ = self.run_command()
        self.assertIn("processed: 0, skipped: 1", out)

    def test_loop_stops_cleanly_on_ctrl_c(self):
        self.clock.advance(seconds=10)
        command = "games.management.commands.close_expired_rounds"
        with (
            mock.patch("time.sleep", side_effect=[None, KeyboardInterrupt]) as sleep,
            mock.patch(f"{command}.close_old_connections"),
        ):
            out, _ = self.run_command("--loop", "--interval", "2")

        self.assertEqual(sleep.call_args_list, [mock.call(2.0), mock.call(2.0)])
        self.assertEqual(out.count("processed:"), 2)
        self.assertIn("processed: 1, skipped: 0", out)
        self.assertTrue(out.rstrip().endswith("Stopped."))
