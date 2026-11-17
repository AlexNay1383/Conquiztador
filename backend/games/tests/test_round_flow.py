from datetime import timedelta

from django.db.models import ProtectedError
from django.test import TestCase

from games import services
from games.exceptions import InvalidInputError, InvalidStateError, NotFoundError
from games.models import Game, Round, RoundAnswer, RoundQuestion
from questions.models import NumericQuestion

from .factories import create_active_game, create_numeric_questions, use_capture_rights, use_fake_clock

TEN_SECONDS = timedelta(seconds=10)


class RoundFlowTestCase(TestCase):
    def setUp(self):
        self.game, self.players = create_active_game()
        self.a, self.b, self.c = (player.pk for player in self.players)
        self.clock = use_fake_clock(self)
        create_numeric_questions(100, 200, 300, 400, 500)

    def start_round(self):
        round_ = services.create_city_capture_round(self.game.pk)
        services.start_round(round_.pk)
        return round_

    def current(self, round_):
        return round_.get_current_question()

    def answer(self, round_, player_id, offset=0, after=0.0):
        """Answer `offset` away from the correct value, `after` seconds from now."""
        self.clock.advance(seconds=after)
        return services.submit_answer(round_.pk, player_id, self.current(round_).correct_answer + offset)

    def refreshed(self, round_):
        round_.refresh_from_db()
        return round_

    def ranking(self, round_):
        return dict(round_.placements.values_list("place", "player_id"))

    def assert_refused(self, error_class, code, func, *args):
        with self.assertRaises(error_class) as context:
            func(*args)
        self.assertEqual(context.exception.code, code)


class WorkflowTests(RoundFlowTestCase):
    def test_create_start_and_finish(self):
        round_ = services.create_city_capture_round(self.game.pk)
        question = self.current(round_)

        self.assertEqual((round_.number, round_.status, round_.places_needed), (1, "pending", 2))
        self.assertEqual(set(round_.participants.values_list("pk", flat=True)), {self.a, self.b, self.c})
        self.assertEqual((question.status, question.started_at, question.deadline), ("pending", None, None))

        start = self.clock()
        services.start_round(round_.pk)
        question.refresh_from_db()
        self.assertEqual(self.refreshed(round_).status, Round.Status.ACTIVE)
        self.assertEqual((question.started_at, question.deadline), (start, start + TEN_SECONDS))

        self.answer(round_, self.a, offset=0, after=1)
        self.answer(round_, self.b, offset=-5, after=1)
        self.answer(round_, self.c, offset=50, after=1)

        round_ = self.refreshed(round_)
        self.assertEqual(round_.status, Round.Status.COMPLETED)
        self.assertEqual(round_.winner_id, self.a)
        self.assertEqual(self.ranking(round_), {1: self.a, 2: self.b})
        self.assertEqual(round_.completed_at, start + timedelta(seconds=3))
        self.assertEqual(round_.unresolved_reason, "")
        self.assertEqual(self.game.get_current_round(), round_)

    def test_missing_initial_question_refuses_creation(self):
        NumericQuestion.objects.all().delete()

        self.assert_refused(InvalidStateError, "no_question_available", services.create_city_capture_round, self.game.pk)

        self.assertFalse(Round.objects.exists())

    def test_question_is_not_repeated_within_a_game(self):
        NumericQuestion.objects.exclude(pk__in=NumericQuestion.objects.order_by("pk")[:2].values("pk")).delete()
        asked = []
        for _ in range(2):
            round_ = self.start_round()
            asked.append(self.current(round_).numeric_question_id)
            for player_id in (self.a, self.b, self.c):
                self.answer(round_, player_id, offset=player_id, after=0.1)
            use_capture_rights(self.game)

        self.assertEqual(len(set(asked)), 2)
        self.assert_refused(InvalidStateError, "no_question_available", services.create_city_capture_round, self.game.pk)

        other_game, _ = create_active_game(prefix="other")
        services.create_city_capture_round(other_game.pk)

    def test_operations_require_an_active_game(self):
        round_ = self.start_round()
        Game.objects.filter(pk=self.game.pk).update(status=Game.Status.COMPLETED)

        self.assert_refused(InvalidStateError, "game_not_active", services.submit_answer, round_.pk, self.a, 1)
        self.assert_refused(InvalidStateError, "game_not_active", services.close_question, round_.pk)


class AnswerRuleTests(RoundFlowTestCase):
    def test_answers_before_the_start_are_refused(self):
        round_ = services.create_city_capture_round(self.game.pk)

        self.assert_refused(InvalidStateError, "round_not_started", services.submit_answer, round_.pk, self.a, 5)

    def test_players_outside_the_question_are_refused(self):
        round_ = self.start_round()
        _, (stranger, *_) = create_active_game(prefix="stranger")

        self.assert_refused(InvalidInputError, "player_not_participant", services.submit_answer, round_.pk, stranger.pk, 5)
        self.assert_refused(NotFoundError, "player_not_found", services.submit_answer, round_.pk, 999_999, 5)
        self.assert_refused(NotFoundError, "round_not_found", services.submit_answer, 999_999, self.a, 5)

    def test_second_answer_does_not_replace_the_first(self):
        round_ = self.start_round()
        self.answer(round_, self.a, offset=7)

        with self.assertRaises(InvalidStateError) as context:
            self.answer(round_, self.a, offset=0)

        self.assertEqual(context.exception.code, "already_answered")
        stored = RoundAnswer.objects.get(player_id=self.a)
        self.assertEqual(stored.numeric_value, self.current(round_).correct_answer + 7)

    def test_invalid_numbers_do_not_use_the_right_to_answer(self):
        round_ = self.start_round()
        for value in ("12.5", 12.5, 12.0, True, "abc", None, "1e3", "", 10**30):
            with self.subTest(value=value):
                self.assert_refused(InvalidInputError, "invalid_answer", services.submit_answer, round_.pk, self.a, value)

        services.submit_answer(round_.pk, self.a, " -42 ")
        self.assertEqual(RoundAnswer.objects.get(player_id=self.a).numeric_value, -42)

    def test_deadline_boundary(self):
        round_ = self.start_round()
        deadline = self.current(round_).deadline

        self.clock.current = deadline - timedelta(microseconds=1)
        services.submit_answer(round_.pk, self.a, 1)
        self.clock.current = deadline
        self.assert_refused(InvalidStateError, "deadline_passed", services.submit_answer, round_.pk, self.b, 1)
        self.clock.current = deadline + timedelta(seconds=5)
        self.assert_refused(InvalidStateError, "deadline_passed", services.submit_answer, round_.pk, self.c, 1)

        self.assertEqual(list(RoundAnswer.objects.values_list("player_id", flat=True)), [self.a])

    def test_unanswered_players_are_not_ranked(self):
        round_ = self.start_round()
        self.answer(round_, self.c, offset=1000, after=2)
        self.answer(round_, self.b, offset=900, after=1)

        self.clock.advance(seconds=10)
        services.close_question(round_.pk)

        self.assertEqual(self.ranking(round_), {1: self.b, 2: self.c})


class ClosingTests(RoundFlowTestCase):
    def test_early_close_is_refused(self):
        round_ = self.start_round()
        self.answer(round_, self.a, after=1)

        self.clock.advance(seconds=8.999)
        self.assert_refused(InvalidStateError, "question_still_open", services.close_question, round_.pk)

        self.clock.advance(seconds=0.001)
        services.close_question(round_.pk)
        self.assertEqual(self.refreshed(round_).status, Round.Status.COMPLETED)

    def test_completed_result_is_not_replaced(self):
        round_ = self.start_round()
        for player_id, offset in ((self.a, 3), (self.b, 1), (self.c, 2)):
            self.answer(round_, player_id, offset=offset, after=0.5)
        before = services.get_round_state(round_.pk)

        self.clock.advance(seconds=30)
        self.assert_refused(InvalidStateError, "round_completed", services.close_question, round_.pk)
        self.assert_refused(InvalidStateError, "round_completed", services.submit_answer, round_.pk, self.a, 1)

        self.assertEqual(services.get_round_state(round_.pk, now=before["completed_at"]), before)


class FollowUpQuestionTests(RoundFlowTestCase):
    def test_equal_closeness_on_both_sides_is_decided_by_time(self):
        round_ = self.start_round()
        self.answer(round_, self.a, offset=0, after=1)
        self.answer(round_, self.b, offset=10, after=1)
        self.answer(round_, self.c, offset=-10, after=1)

        self.assertEqual(self.ranking(round_), {1: self.a, 2: self.b})
        self.assertEqual(self.refreshed(round_).questions.count(), 1)

    def test_full_tie_starts_a_new_question_for_the_tied_group(self):
        round_ = self.start_round()
        first = self.current(round_)
        self.answer(round_, self.a, offset=0, after=1)
        self.clock.advance(seconds=1)
        services.submit_answer(round_.pk, self.b, first.correct_answer + 10)
        services.submit_answer(round_.pk, self.c, first.correct_answer - 10)
        closed_at = self.clock()

        second = self.current(round_)
        self.assertEqual(second.sequence, 2)
        self.assertNotEqual(second.numeric_question_id, first.numeric_question_id)
        self.assertEqual(set(second.participants.values_list("pk", flat=True)), {self.b, self.c})
        self.assertEqual((second.first_place, second.place_count), (2, 1))
        self.assertEqual((second.status, second.started_at, second.deadline), ("active", closed_at, closed_at + TEN_SECONDS))
        self.assertEqual(self.ranking(round_), {1: self.a})
        self.assertEqual(self.refreshed(round_).number, 1)

        self.assert_refused(InvalidInputError, "player_not_participant", services.submit_answer, round_.pk, self.a, 1)
        self.answer(round_, self.c, offset=1, after=2)
        self.answer(round_, self.b, offset=2, after=1)

        round_ = self.refreshed(round_)
        self.assertEqual(self.ranking(round_), {1: self.a, 2: self.c})
        self.assertEqual((round_.winner_id, round_.unresolved_reason), (self.a, ""))
        self.assertEqual(RoundAnswer.objects.filter(question=first).count(), 3)

    def test_no_answers_asks_the_same_group_again(self):
        round_ = self.start_round()

        self.clock.advance(seconds=10)
        services.close_question(round_.pk)

        second = self.current(round_)
        self.assertEqual(set(second.participants.values_list("pk", flat=True)), {self.a, self.b, self.c})
        self.assertEqual((second.first_place, second.place_count), (1, 2))

    def test_limit_of_three_questions_without_a_winner(self):
        round_ = self.start_round()
        for _ in range(3):
            self.clock.advance(seconds=10)
            services.close_question(round_.pk)

        round_ = self.refreshed(round_)
        self.assertEqual(round_.questions.count(), 3)
        self.assertEqual(round_.status, Round.Status.COMPLETED)
        self.assertIsNone(round_.winner)
        self.assertIsNotNone(round_.completed_at)
        self.assertEqual(round_.unresolved_reason, Round.UnresolvedReason.QUESTION_LIMIT)

    def test_winner_decided_on_the_third_question_is_kept(self):
        round_ = self.start_round()
        for _ in range(2):
            self.clock.advance(seconds=10)
            services.close_question(round_.pk)

        self.answer(round_, self.b, offset=1, after=1)
        self.answer(round_, self.a, offset=3, after=1)
        self.clock.advance(seconds=10)
        services.close_question(round_.pk)

        round_ = self.refreshed(round_)
        self.assertEqual(round_.questions.count(), 3)
        self.assertEqual(self.ranking(round_), {1: self.b, 2: self.a})
        self.assertEqual((round_.winner_id, round_.unresolved_reason), (self.b, ""))

    def tie_b_and_c(self, round_):
        self.clock.advance(seconds=1)
        correct = self.current(round_).correct_answer
        services.submit_answer(round_.pk, self.b, correct + 4)
        services.submit_answer(round_.pk, self.c, correct - 4)

    def test_tie_on_the_third_question_keeps_decided_places(self):
        round_ = self.start_round()
        self.answer(round_, self.a, offset=0, after=1)
        self.tie_b_and_c(round_)
        self.clock.advance(seconds=10)
        services.close_question(round_.pk)
        self.tie_b_and_c(round_)

        round_ = self.refreshed(round_)
        self.assertEqual(round_.questions.count(), 3)
        self.assertEqual(round_.status, Round.Status.COMPLETED)
        self.assertEqual(self.ranking(round_), {1: self.a})
        self.assertEqual((round_.winner_id, round_.unresolved_reason), (self.a, Round.UnresolvedReason.QUESTION_LIMIT))

    def test_limit_takes_precedence_over_an_exhausted_bank(self):
        round_ = self.start_round()
        self.answer(round_, self.a, offset=0, after=1)
        self.tie_b_and_c(round_)
        self.clock.advance(seconds=10)
        services.close_question(round_.pk)
        NumericQuestion.objects.exclude(asked_in__isnull=False).delete()
        self.tie_b_and_c(round_)

        self.assertEqual(self.refreshed(round_).unresolved_reason, Round.UnresolvedReason.QUESTION_LIMIT)

    def test_exhausted_bank_keeps_the_decided_result(self):
        round_ = self.start_round()
        NumericQuestion.objects.exclude(asked_in__isnull=False).delete()
        self.answer(round_, self.a, offset=0, after=1)
        self.tie_b_and_c(round_)

        round_ = self.refreshed(round_)
        self.assertEqual(round_.status, Round.Status.COMPLETED)
        self.assertEqual(self.ranking(round_), {1: self.a})
        self.assertEqual(round_.winner_id, self.a)
        self.assertEqual(round_.unresolved_reason, Round.UnresolvedReason.QUESTION_BANK_EXHAUSTED)

    def test_single_answer_leaves_second_place_open(self):
        round_ = self.start_round()
        self.answer(round_, self.c, offset=99, after=4)
        self.clock.advance(seconds=10)
        services.close_question(round_.pk)

        round_ = self.refreshed(round_)
        self.assertEqual(round_.questions.count(), 1)
        self.assertEqual(self.ranking(round_), {1: self.c})
        self.assertEqual((round_.winner_id, round_.unresolved_reason), (self.c, Round.UnresolvedReason.NOT_ENOUGH_ANSWERS))


class StoredDataTests(RoundFlowTestCase):
    def test_state_can_be_restored_after_reload(self):
        round_ = self.start_round()
        question = self.current(round_)
        self.answer(round_, self.b, offset=5, after=3)

        state = services.get_round_state(round_.pk)
        current = state["current_question"]
        self.assertEqual(current["text"], question.text)
        self.assertEqual(current["deadline"], question.deadline)
        self.assertEqual(current["remaining"], timedelta(seconds=7))
        self.assertEqual(current["answered_player_ids"], [self.b])
        self.assertIsNone(current["correct_answer"])
        self.assertEqual(services.get_round_state(round_.pk), state)

        self.answer(round_, self.a, offset=1, after=1)
        self.answer(round_, self.c, offset=9, after=1)
        state = services.get_round_state(round_.pk)
        self.assertIsNone(state["current_question"])
        self.assertEqual(state["ranking"], {1: self.a, 2: self.b})
        self.assertEqual(state["questions"][0]["correct_answer"], question.correct_answer)

    def test_editing_the_bank_does_not_change_an_asked_question(self):
        round_ = self.start_round()
        question = self.current(round_)
        original = (question.text, question.correct_answer)
        NumericQuestion.objects.filter(pk=question.numeric_question_id).update(text="Променен", correct_answer=0)

        self.answer(round_, self.a, offset=0, after=1)
        self.answer(round_, self.b, offset=-original[1], after=1)
        self.answer(round_, self.c, offset=2, after=1)

        question.refresh_from_db()
        self.assertEqual((question.text, question.correct_answer), original)
        self.assertEqual(self.ranking(round_), {1: self.a, 2: self.c})

    def test_asked_bank_question_cannot_be_deleted(self):
        round_ = services.create_city_capture_round(self.game.pk)
        source = self.current(round_).numeric_question

        with self.assertRaises(ProtectedError):
            source.delete()

        self.assertTrue(RoundQuestion.objects.filter(numeric_question=source).exists())
