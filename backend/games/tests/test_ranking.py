import itertools
from datetime import UTC, datetime, timedelta

from django.test import SimpleTestCase

from games.ranking import FollowUp, NumericAnswer, rank_numeric

START = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
A, B, C = 1, 2, 3


def answer(player_id, value, seconds):
    return NumericAnswer(player_id, value, START + timedelta(seconds=seconds))


def rank(answers, correct=100, group=(A, B, C), first_place=1, place_count=2):
    return rank_numeric(answers, correct, list(group), first_place, place_count)


class NumericRankingTests(SimpleTestCase):
    def test_closeness_beats_speed(self):
        outcome = rank([answer(A, 90, 1), answer(B, 99, 5), answer(C, 150, 0.5)])

        self.assertEqual(outcome.placements, ((1, B), (2, A)))
        self.assertIsNone(outcome.follow_up)
        self.assertFalse(outcome.unresolved)

    def test_equal_closeness_is_decided_by_speed_on_both_sides(self):
        outcome = rank([answer(A, 110, 3), answer(B, 90, 2), answer(C, 200, 1)])

        self.assertEqual(outcome.placements, ((1, B), (2, A)))

    def test_sub_second_differences_count(self):
        outcome = rank([answer(A, 95, 2.000002), answer(B, 105, 2.000001)], place_count=1)

        self.assertEqual(outcome.placements, ((1, B),))

    def test_single_answer_takes_only_first_place(self):
        outcome = rank([answer(C, 7, 9)])

        self.assertEqual(outcome.placements, ((1, C),))
        self.assertIsNone(outcome.follow_up)
        self.assertTrue(outcome.unresolved)

    def test_no_answers_asks_the_same_group_again(self):
        outcome = rank([], group=(B, C), first_place=2, place_count=1)

        self.assertEqual(outcome.placements, ())
        self.assertEqual(outcome.follow_up, FollowUp((B, C), 2, 1))

    def test_full_tie_for_first_asks_only_the_tied_players(self):
        outcome = rank([answer(A, 95, 4), answer(B, 105, 4), answer(C, 100, 6)], place_count=1)

        self.assertEqual(outcome.placements, ((1, C),))
        self.assertIsNone(outcome.follow_up)

        outcome = rank([answer(A, 95, 4), answer(B, 105, 4), answer(C, 300, 1)])

        self.assertEqual(outcome.placements, ())
        self.assertEqual(outcome.follow_up, FollowUp((A, B), 1, 2))

    def test_full_tie_for_second_keeps_the_first_place(self):
        outcome = rank([answer(A, 100, 1), answer(B, 90, 3), answer(C, 110, 3)])

        self.assertEqual(outcome.placements, ((1, A),))
        self.assertEqual(outcome.follow_up, FollowUp((B, C), 2, 1))

    def test_tie_below_the_needed_places_is_ignored(self):
        outcome = rank([answer(A, 100, 1), answer(B, 90, 3), answer(C, 110, 3)], place_count=1)

        self.assertEqual(outcome.placements, ((1, A),))
        self.assertIsNone(outcome.follow_up)

    def test_three_way_tie_asks_everyone_for_both_places(self):
        outcome = rank([answer(A, 100, 2), answer(B, 100, 2), answer(C, 100, 2)])

        self.assertEqual(outcome.follow_up, FollowUp((A, B, C), 1, 2))

    def test_follow_up_assigns_only_its_own_places(self):
        outcome = rank([answer(B, 50, 1)], group=(B, C), first_place=2, place_count=1)

        self.assertEqual(outcome.placements, ((2, B),))
        self.assertFalse(outcome.unresolved)

    def test_result_does_not_depend_on_record_order(self):
        answers = [answer(A, 90, 1), answer(B, 110, 1), answer(C, 101, 7)]
        outcomes = {rank(list(order)) for order in itertools.permutations(answers)}

        self.assertEqual(len(outcomes), 1)
