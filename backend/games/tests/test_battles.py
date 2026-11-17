from datetime import timedelta
from unittest import mock

from django.test import TestCase

from games import services
from games.exceptions import InvalidInputError, InvalidStateError, NotFoundError
from games.models import Capital, CaptureRight, Round, RoundAnswer, RoundQuestion, ScoreEvent, Territory
from questions.models import AnswerOption, ChoiceQuestion, NumericQuestion

from .factories import (
    create_active_game,
    create_battle_game,
    create_choice_questions,
    create_numeric_questions,
    use_fake_clock,
)


class BattleTestCase(TestCase):
    def setUp(self):
        self.game, self.players = create_battle_game()
        self.a, self.b, self.c = (player.pk for player in self.players)
        self.clock = use_fake_clock(self)
        create_choice_questions(6)
        create_numeric_questions(100, 200, 300)

    def territory(self, slug):
        return Territory.objects.get(game=self.game, slug=slug)

    def battle(self, slug="zhitno-pole", attacker=None, **kwargs):
        round_ = services.create_battle(self.game.pk, attacker or self.a, self.territory(slug).pk, **kwargs)
        services.start_round(round_.pk)
        return round_

    def current(self, round_):
        return round_.get_current_question()

    def choose(self, round_, player_id, correct, after=1.0):
        self.clock.advance(seconds=after)
        option = self.current(round_).options.filter(is_correct=correct).first()
        return services.submit_answer(round_.pk, player_id, option.source_option_id)

    def guess(self, round_, player_id, offset, after=1.0):
        self.clock.advance(seconds=after)
        return services.submit_answer(round_.pk, player_id, self.current(round_).correct_answer + offset)

    def expire(self, round_):
        self.clock.advance(seconds=10)
        return services.close_question(round_.pk)

    def refreshed(self, round_):
        round_.refresh_from_db()
        return round_

    def score(self, player_id):
        return self.game.players.get(pk=player_id).score

    def assert_refused(self, error_class, code, func, *args, **kwargs):
        with self.assertRaises(error_class) as context:
            func(*args, **kwargs)
        self.assertEqual(context.exception.code, code)


class TargetTests(BattleTestCase):
    def test_ordinary_target_creates_a_battle(self):
        round_ = services.create_battle(self.game.pk, self.a, self.territory("zhitno-pole").pk)

        self.assertEqual(round_.type, Round.Type.BATTLE)
        self.assertEqual((round_.attacker_id, round_.defender_id, round_.target.slug), (self.a, self.b, "zhitno-pole"))
        self.assertEqual(set(round_.participants.values_list("pk", flat=True)), {self.a, self.b})
        self.assertEqual(round_.places_needed, 1)
        question = self.current(round_)
        self.assertEqual((question.kind, question.status, question.options.count()), ("choice", "pending", 4))

    def test_capital_target_creates_a_capital_attack(self):
        round_ = services.create_battle(self.game.pk, self.a, self.territory("rozova-dolina").pk)

        self.assertEqual((round_.type, round_.defender_id), (Round.Type.CAPITAL_ATTACK, self.c))

    def test_invalid_targets(self):
        other_game, _ = create_battle_game(prefix="other")
        foreign = Territory.objects.get(game=other_game, slug="zhitno-pole")
        cases = [
            ("target_is_own", self.territory("dunavia").pk, {}),
            ("target_not_adjacent", self.territory("tsarevo").pk, {}),
            ("territory_not_in_game", foreign.pk, {}),
            ("defender_mismatch", self.territory("zhitno-pole").pk, {"defender_id": self.c}),
        ]
        for code, target_id, kwargs in cases:
            with self.subTest(code=code):
                self.assert_refused(InvalidInputError, code, services.create_battle, self.game.pk, self.a, target_id, **kwargs)
        self.assert_refused(NotFoundError, "territory_not_found", services.create_battle, self.game.pk, self.a, 999_999)
        self.assertFalse(Round.objects.filter(game=self.game).exists())

    def test_free_target_and_unfinished_map(self):
        Territory.objects.filter(pk=self.territory("tsarevo").pk).update(owner=None)

        self.assert_refused(InvalidInputError, "target_is_free", services.create_battle, self.game.pk, self.c, self.territory("tsarevo").pk)
        self.assert_refused(InvalidStateError, "map_not_full", services.create_battle, self.game.pk, self.a, self.territory("zhitno-pole").pk)

    def test_open_round_or_pending_rights_block_battles(self):
        first = services.create_battle(self.game.pk, self.a, self.territory("zhitno-pole").pk)
        self.assert_refused(InvalidStateError, "round_in_progress", services.create_battle, self.game.pk, self.a, self.territory("zhitno-pole").pk)

        Round.objects.filter(pk=first.pk).update(status="completed", started_at=self.clock(), completed_at=self.clock(), winner=self.a)
        CaptureRight.objects.create(round=first, player_id=self.a, order=1, allowed=1)
        self.assert_refused(InvalidStateError, "capture_rights_pending", services.create_battle, self.game.pk, self.a, self.territory("zhitno-pole").pk)

    def test_missing_choice_question_refuses_creation(self):
        ChoiceQuestion.objects.all().delete()

        self.assert_refused(InvalidStateError, "no_question_available", services.create_battle, self.game.pk, self.a, self.territory("zhitno-pole").pk)
        self.assertFalse(Round.objects.filter(game=self.game).exists())


class ChoiceAnswerTests(BattleTestCase):
    def test_option_must_belong_to_the_current_question(self):
        round_ = self.battle()
        foreign_option = AnswerOption.objects.exclude(question=self.current(round_).choice_question).first()

        self.assert_refused(InvalidInputError, "invalid_option", services.submit_answer, round_.pk, self.a, foreign_option.pk)
        self.assert_refused(InvalidInputError, "invalid_option", services.submit_answer, round_.pk, self.a, 999_999)
        self.assert_refused(InvalidInputError, "invalid_answer", services.submit_answer, round_.pk, self.a, "A")

        self.choose(round_, self.a, correct=True)
        self.assertEqual(RoundAnswer.objects.get(player_id=self.a).option.is_correct, True)

    def test_third_player_cannot_answer(self):
        round_ = self.battle()
        option = self.current(round_).options.first()

        self.assert_refused(InvalidInputError, "player_not_participant", services.submit_answer, round_.pk, self.c, option.source_option_id)


class BattleResultTests(BattleTestCase):
    def test_single_correct_attacker_conquers_the_target(self):
        Territory.objects.filter(pk=self.territory("zhitno-pole").pk).update(score=100)
        round_ = self.battle()
        self.choose(round_, self.b, correct=False)
        self.choose(round_, self.a, correct=True)

        round_ = self.refreshed(round_)
        target = self.territory("zhitno-pole")
        self.assertEqual((round_.status, round_.winner_id), ("completed", self.a))
        self.assertEqual((target.owner_id, target.score), (self.a, 200))
        self.assertEqual((self.score(self.a), self.score(self.b)), (300, 0))
        events = list(ScoreEvent.objects.filter(round=round_).values_list("kind", "points"))
        self.assertEqual(events, [("battle_win", 100), ("conquest", 200)])

    def test_successful_defense_keeps_the_territory(self):
        round_ = self.battle()
        self.choose(round_, self.a, correct=False)
        self.choose(round_, self.b, correct=True)

        target = self.territory("zhitno-pole")
        self.assertEqual((self.refreshed(round_).winner_id, target.owner_id, target.score), (self.b, self.b, 0))
        self.assertEqual((self.score(self.a), self.score(self.b)), (0, 100))
        self.assertEqual(list(ScoreEvent.objects.values_list("kind", flat=True)), ["defense_win"])

    def test_two_correct_answers_lead_to_a_numeric_question(self):
        round_ = self.battle()
        first = self.current(round_)
        self.choose(round_, self.b, correct=True, after=1)
        self.choose(round_, self.a, correct=True, after=4)
        closed_at = self.clock()

        second = self.current(round_)
        self.assertEqual((second.sequence, second.kind), (2, "numeric"))
        self.assertEqual(set(second.participants.values_list("pk", flat=True)), {self.a, self.b})
        self.assertEqual((second.started_at, second.deadline), (closed_at, closed_at + timedelta(seconds=10)))
        self.assertEqual(first.answers.count(), 2)

        self.guess(round_, self.b, offset=30)
        self.guess(round_, self.a, offset=-2)
        self.assertEqual(self.refreshed(round_).winner_id, self.a)

    def test_no_correct_answer_leads_to_another_choice_question(self):
        round_ = self.battle()
        self.choose(round_, self.a, correct=False)
        self.expire(round_)

        second = self.current(round_)
        self.assertEqual((second.kind, second.sequence), ("choice", 2))
        self.assertEqual(set(second.participants.values_list("pk", flat=True)), {self.a, self.b})

    def test_numeric_follow_up_stays_numeric(self):
        round_ = self.battle()
        self.choose(round_, self.a, correct=True)
        self.choose(round_, self.b, correct=True)
        self.expire(round_)

        third = self.current(round_)
        self.assertEqual((third.sequence, third.kind), (3, "numeric"))

    def test_winner_on_the_third_question_without_a_fourth(self):
        round_ = self.battle()
        self.choose(round_, self.a, correct=False)
        self.choose(round_, self.b, correct=False)
        self.choose(round_, self.a, correct=True)
        self.choose(round_, self.b, correct=True)
        self.clock.advance(seconds=1)
        correct = self.current(round_).correct_answer
        services.submit_answer(round_.pk, self.a, correct + 5)
        services.submit_answer(round_.pk, self.b, correct - 9)

        round_ = self.refreshed(round_)
        self.assertEqual(round_.questions.count(), 3)
        self.assertEqual(list(round_.questions.values_list("kind", flat=True)), ["choice", "choice", "numeric"])
        self.assertEqual((round_.winner_id, round_.unresolved_reason), (self.a, ""))

    def test_limit_ends_the_battle_without_a_winner(self):
        round_ = self.battle()
        for _ in range(3):
            self.expire(round_)

        round_ = self.refreshed(round_)
        self.assertEqual((round_.status, round_.winner_id), ("completed", None))
        self.assertEqual(round_.unresolved_reason, Round.UnresolvedReason.QUESTION_LIMIT)
        self.assertEqual(self.territory("zhitno-pole").owner_id, self.b)
        self.assertFalse(ScoreEvent.objects.exists())

    def test_exhausted_numeric_bank_ends_without_a_winner(self):
        round_ = self.battle()
        NumericQuestion.objects.all().delete()
        self.choose(round_, self.a, correct=True)
        self.choose(round_, self.b, correct=True)

        round_ = self.refreshed(round_)
        self.assertEqual((round_.winner_id, round_.unresolved_reason), (None, Round.UnresolvedReason.QUESTION_BANK_EXHAUSTED))

    def test_capital_attack_rewards_without_changing_the_capital(self):
        capital = Capital.objects.get(territory__slug="rozova-dolina", territory__game=self.game)
        round_ = self.battle("rozova-dolina")
        self.choose(round_, self.a, correct=True)
        self.choose(round_, self.c, correct=False)

        capital.refresh_from_db()
        self.assertEqual((self.refreshed(round_).winner_id, self.score(self.a)), (self.a, 100))
        self.assertEqual((capital.player_id, capital.territory.owner_id, capital.health), (self.c, self.c, 3))
        self.assertEqual(capital.territory.score, 0)
        self.assertEqual(list(ScoreEvent.objects.values_list("kind", flat=True)), ["battle_win"])


class BattleIntegrityTests(BattleTestCase):
    def test_repeated_completion_changes_nothing(self):
        round_ = self.battle()
        self.choose(round_, self.a, correct=True)
        self.choose(round_, self.b, correct=False)
        scores = (self.score(self.a), self.score(self.b))

        self.assert_refused(InvalidStateError, "round_completed", services.close_question, round_.pk)

        self.assertEqual((self.score(self.a), self.score(self.b)), scores)
        self.assertEqual(ScoreEvent.objects.count(), 2)

    def test_changed_target_owner_blocks_the_result_but_keeps_answers(self):
        round_ = self.battle()
        Territory.objects.filter(pk=self.territory("zhitno-pole").pk).update(owner=self.c)
        self.choose(round_, self.a, correct=True)
        self.choose(round_, self.b, correct=False)

        self.assertEqual(self.refreshed(round_).status, Round.Status.ACTIVE)
        self.assertEqual(RoundAnswer.objects.filter(question__round=round_).count(), 2)
        self.assert_refused(InvalidStateError, "battle_target_changed", services.close_question, round_.pk)
        self.assertEqual(self.territory("zhitno-pole").owner_id, self.c)
        self.assertFalse(ScoreEvent.objects.exists())
        self.assertFalse(round_.placements.exists())

    def test_error_while_applying_rolls_back_everything(self):
        round_ = self.battle()
        self.choose(round_, self.a, correct=True)
        self.clock.advance(seconds=10)

        with mock.patch("games.services.scoring.award_capture", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                services.close_question(round_.pk)

        round_ = self.refreshed(round_)
        self.assertEqual((round_.status, round_.winner_id), (Round.Status.ACTIVE, None))
        self.assertEqual(self.current(round_).sequence, 1)
        self.assertEqual((self.territory("zhitno-pole").owner_id, self.score(self.a)), (self.b, 0))
        self.assertFalse(ScoreEvent.objects.exists())


class BattleDataTests(BattleTestCase):
    def test_sequence_of_choice_then_numeric_is_restored(self):
        round_ = self.battle()
        self.choose(round_, self.a, correct=True)
        self.choose(round_, self.b, correct=True)
        self.guess(round_, self.a, offset=1)
        self.guess(round_, self.b, offset=9)

        state = services.get_round_state(round_.pk)
        choice, numeric = state["questions"]
        self.assertEqual((choice["kind"], numeric["kind"]), ("choice", "numeric"))
        self.assertEqual(len(choice["options"]), 4)
        self.assertEqual({answer["value"] for answer in choice["answers"]}, {choice["correct_answer"]})
        self.assertEqual(sorted(answer["value"] - numeric["correct_answer"] for answer in numeric["answers"]), [1, 9])
        self.assertEqual(state["winner_id"], self.a)

    def test_equal_ids_in_both_bank_models_stay_distinct(self):
        ChoiceQuestion.objects.all().delete()
        NumericQuestion.objects.all().delete()
        choice = create_choice_questions(1, first_pk=500)[0]
        numeric = NumericQuestion.objects.create(pk=500, category=choice.category, text="Числов 500?", correct_answer=77)

        round_ = self.battle()
        self.choose(round_, self.a, correct=True)
        self.choose(round_, self.b, correct=True)

        asked = list(round_.questions.values_list("kind", "choice_question_id", "numeric_question_id"))
        self.assertEqual(asked, [("choice", 500, None), ("numeric", None, 500)])
        self.assertEqual(self.current(round_).text, numeric.text)
        self.assertEqual((choice.pk, numeric.pk), (500, 500))

    def test_editing_the_bank_does_not_change_asked_options(self):
        round_ = self.battle()
        asked = self.current(round_)
        AnswerOption.objects.filter(question=asked.choice_question).update(is_correct=False, text="X")

        self.choose(round_, self.a, correct=True)
        self.choose(round_, self.b, correct=False)

        self.assertEqual(self.refreshed(round_).winner_id, self.a)
        self.assertEqual(list(asked.options.values_list("text", flat=True)), ["A", "B", "C", "D"])


class BattleAfterConquestTests(TestCase):
    def test_battles_need_the_map_to_be_full(self):
        game, players = create_active_game()
        create_choice_questions(1)
        attacker_capital = Capital.objects.get(player=players[0]).territory
        neighbor = attacker_capital.neighbors.first()
        Territory.objects.filter(pk=neighbor.pk).update(owner=players[1])

        with self.assertRaises(InvalidStateError) as context:
            services.create_battle(game.pk, players[0].pk, neighbor.pk)

        self.assertEqual(context.exception.code, "map_not_full")
        self.assertFalse(RoundQuestion.objects.exists())
