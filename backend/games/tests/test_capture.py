from unittest import mock

from django.db import IntegrityError, transaction
from django.test import TestCase

from games import services
from games.exceptions import InvalidInputError, InvalidStateError, NotFoundError
from games.models import Capital, CaptureRight, Round, ScoreEvent, Territory
from questions.models import NumericQuestion

from .factories import create_active_game, create_numeric_questions, use_capture_rights, use_fake_clock


class CaptureTestCase(TestCase):
    def setUp(self):
        self.game, self.players = create_active_game()
        self.a, self.b, self.c = (player.pk for player in self.players)
        self.clock = use_fake_clock(self)
        create_numeric_questions(100, 200, 300, 400, 500, 600, 700, 800)

    def play_round(self, *ranking):
        """Play a city-capture round where the given players answer in ranking order; others stay silent."""
        round_ = services.create_city_capture_round(self.game.pk)
        services.start_round(round_.pk)
        correct = round_.get_current_question().correct_answer
        for offset, player_id in enumerate(ranking):
            self.clock.advance(seconds=1)
            services.submit_answer(round_.pk, player_id, correct + offset)
        if round_.get_current_question() is not None:
            self.clock.advance(seconds=10)
            services.close_question(round_.pk)
        round_.refresh_from_db()
        return round_

    def territory(self, slug):
        return Territory.objects.get(game=self.game, slug=slug)

    def capital_of(self, player_id):
        return Capital.objects.get(player_id=player_id).territory

    def free_neighbors(self, territory):
        return territory.neighbors.filter(owner__isnull=True).order_by("slug")

    def score(self, player_id):
        return self.game.players.get(pk=player_id).score

    def capture(self, player_id, territory):
        return services.capture_territory(self.game.pk, player_id, territory.pk)

    def assert_refused(self, error_class, code, player_id, territory_id):
        with self.assertRaises(error_class) as context:
            services.capture_territory(self.game.pk, player_id, territory_id)
        self.assertEqual(context.exception.code, code)

    def leave_free(self, count, owner_id):
        """Give every free territory except `count` of them to `owner_id`, directly."""
        free = Territory.objects.filter(game=self.game, owner__isnull=True).order_by("slug")
        keep = list(free.values_list("pk", flat=True)[:count])
        free.exclude(pk__in=keep).update(owner_id=owner_id)
        return Territory.objects.filter(pk__in=keep)


class RightsTests(CaptureTestCase):
    def test_first_gets_two_picks_and_second_one(self):
        round_ = self.play_round(self.a, self.b, self.c)

        self.assertEqual((round_.free_territories_at_creation, round_.places_needed), (12, 2))
        rights = list(CaptureRight.objects.filter(round=round_).values_list("player_id", "order", "allowed", "used"))
        self.assertEqual(rights, [(self.a, 1, 2, 0), (self.b, 2, 1, 0)])

    def test_picks_follow_the_ranking_order(self):
        self.play_round(self.a, self.b, self.c)
        b_target = self.free_neighbors(self.capital_of(self.b)).first()

        self.assert_refused(InvalidStateError, "not_your_turn", self.b, b_target.pk)
        self.assert_refused(InvalidStateError, "no_capture_right", self.c, b_target.pk)
        for _ in range(2):
            self.capture(self.a, self.free_neighbors(self.capital_of(self.a)).first())
        self.assert_refused(InvalidStateError, "no_capture_right", self.a, b_target.pk)
        target = self.free_neighbors(self.capital_of(self.b)).first()
        self.capture(self.b, target)
        self.assert_refused(InvalidStateError, "no_capture_right", self.b, self.free_neighbors(target).first().pk)

        self.assertEqual(Territory.objects.filter(game=self.game, owner__isnull=False).count(), 6)
        self.assertEqual(CaptureRight.objects.filter(used=0).count(), 0)

    def test_invalid_targets_and_players(self):
        self.play_round(self.a, self.b)
        other_game, (stranger, *_) = create_active_game(prefix="other")
        foreign_territory = Territory.objects.filter(game=other_game, owner__isnull=True).first()
        target = self.free_neighbors(self.capital_of(self.a)).first()

        self.assert_refused(InvalidInputError, "player_not_in_game", stranger.pk, target.pk)
        self.assert_refused(InvalidInputError, "territory_not_in_game", self.a, foreign_territory.pk)
        self.assert_refused(InvalidStateError, "territory_not_free", self.a, self.capital_of(self.b).pk)
        self.assert_refused(NotFoundError, "territory_not_found", self.a, 999_999)
        self.assert_refused(NotFoundError, "player_not_found", 999_999, target.pk)
        self.assertEqual(CaptureRight.objects.get(player_id=self.a).used, 0)


class AdjacencyTests(CaptureTestCase):
    def setUp(self):
        super().setUp()
        self.play_round(self.a, self.b, self.c)
        self.capital = self.capital_of(self.a)

    def test_non_adjacent_free_territory_is_refused(self):
        far = Territory.objects.filter(game=self.game, owner__isnull=True).exclude(neighbors=self.capital).first()

        self.assert_refused(InvalidInputError, "territory_not_adjacent", self.a, far.pk)

        self.assertIsNone(Territory.objects.get(pk=far.pk).owner)
        self.assertEqual(CaptureRight.objects.get(player_id=self.a).used, 0)

    def test_second_pick_may_neighbor_the_first(self):
        for first in self.free_neighbors(self.capital):
            beyond = (
                self.free_neighbors(first)
                .exclude(neighbors=self.capital)
                .exclude(pk=self.capital.pk)
            )
            if beyond.exists():
                break
        target = beyond.first()
        self.assert_refused(InvalidInputError, "territory_not_adjacent", self.a, target.pk)

        self.capture(self.a, first)
        self.capture(self.a, target)

        self.assertEqual(Territory.objects.get(pk=target.pk).owner_id, self.a)

    def test_any_free_territory_when_no_free_neighbor_exists(self):
        self.capital.neighbors.filter(owner__isnull=True).update(owner_id=self.c)
        far = Territory.objects.filter(game=self.game, owner__isnull=True).first()

        self.assertIn(far, services.get_capture_options(self.game.pk, self.a))
        self.capture(self.a, far)

        self.assertEqual(Territory.objects.get(pk=far.pk).owner_id, self.a)

    def test_options_are_recomputed_after_each_capture(self):
        before = set(services.get_capture_options(self.game.pk, self.a))
        first = self.free_neighbors(self.capital).first()

        self.capture(self.a, first)

        after = set(services.get_capture_options(self.game.pk, self.a))
        self.assertNotIn(first, after)
        self.assertEqual(after, (before - {first}) | set(self.free_neighbors(first)))
        self.assertEqual(services.get_capture_options(self.game.pk, self.b), [])


class ScoringTests(CaptureTestCase):
    def test_round_win_and_captures_are_scored(self):
        round_ = self.play_round(self.a, self.b, self.c)
        self.assertEqual([self.score(pk) for pk in (self.a, self.b, self.c)], [100, 0, 0])

        target = self.free_neighbors(self.capital_of(self.a)).first()
        self.capture(self.a, target)

        target.refresh_from_db()
        self.assertEqual((target.owner_id, target.score), (self.a, 100))
        self.assertEqual(self.score(self.a), 200)
        event = ScoreEvent.objects.get(kind="capture", territory=target)
        self.assertEqual(
            (event.round, event.points, event.score_before, event.score_after, event.territory_score_before, event.territory_score_after),
            (round_, 100, 100, 200, 0, 100),
        )
        self.assertIn("0 + 100 = 100", event.formula)

    def test_second_place_also_earns_capture_points(self):
        self.play_round(self.a, self.b, self.c)
        use_capture_rights(self.game)

        self.assertEqual([self.score(pk) for pk in (self.a, self.b, self.c)], [300, 100, 0])
        self.assertEqual(ScoreEvent.objects.filter(player_id=self.b, kind="capture").count(), 1)

    def test_win_is_awarded_once(self):
        round_ = self.play_round(self.a, self.b, self.c)

        with self.assertRaises(InvalidStateError):
            services.close_question(round_.pk)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ScoreEvent.objects.create(
                game=self.game, player_id=self.a, round=round_, kind="round_win",
                points=100, score_before=100, score_after=200, formula="duplicate",
            )

        self.assertEqual(self.score(self.a), 100)
        self.assertEqual(ScoreEvent.objects.filter(round=round_, kind="round_win").count(), 1)


class PhaseTests(CaptureTestCase):
    def test_next_round_waits_for_all_picks(self):
        self.play_round(self.a, self.b, self.c)

        with self.assertRaises(InvalidStateError) as context:
            services.create_city_capture_round(self.game.pk)
        self.assertEqual(context.exception.code, "capture_rights_pending")

        use_capture_rights(self.game)
        round_ = services.create_city_capture_round(self.game.pk)
        self.assertEqual((round_.number, round_.free_territories_at_creation, round_.places_needed), (2, 9, 2))

    def test_last_two_territories_go_to_the_winner_and_end_the_phase(self):
        self.leave_free(2, owner_id=self.c)
        round_ = self.play_round(self.b, self.a, self.c)

        self.assertEqual((round_.places_needed, round_.winner_id), (1, self.b))
        self.assertEqual(list(CaptureRight.objects.filter(round=round_).values_list("player_id", "allowed")), [(self.b, 2)])
        use_capture_rights(self.game)

        self.assertFalse(Territory.objects.filter(game=self.game, owner__isnull=True).exists())
        with self.assertRaises(InvalidStateError) as context:
            services.create_city_capture_round(self.game.pk)
        self.assertEqual(context.exception.code, "no_free_territories")
        self.game.refresh_from_db()
        self.assertTrue(self.game.is_active())

    def test_last_single_territory(self):
        self.leave_free(1, owner_id=self.c)
        round_ = self.play_round(self.a, self.b)

        self.assertEqual(list(CaptureRight.objects.filter(round=round_).values_list("player_id", "allowed")), [(self.a, 1)])

    def test_unresolved_second_place_keeps_first_rights_and_leaves_territories(self):
        round_ = self.play_round(self.a)

        self.assertEqual(round_.unresolved_reason, Round.UnresolvedReason.NOT_ENOUGH_ANSWERS)
        self.assertEqual(list(CaptureRight.objects.filter(round=round_).values_list("player_id", "allowed")), [(self.a, 2)])
        use_capture_rights(self.game)
        next_round = services.create_city_capture_round(self.game.pk)
        self.assertEqual(next_round.free_territories_at_creation, 10)

    def test_round_without_winner_distributes_nothing(self):
        round_ = services.create_city_capture_round(self.game.pk)
        services.start_round(round_.pk)
        for _ in range(3):
            self.clock.advance(seconds=10)
            services.close_question(round_.pk)

        self.assertFalse(CaptureRight.objects.exists())
        self.assertFalse(ScoreEvent.objects.exists())
        self.assertEqual(services.create_city_capture_round(self.game.pk).free_territories_at_creation, 12)

    def test_missing_question_blocks_the_round_until_the_bank_grows(self):
        NumericQuestion.objects.all().delete()

        with self.assertRaises(InvalidStateError) as context:
            services.create_city_capture_round(self.game.pk)
        self.assertEqual(context.exception.code, "no_question_available")
        self.assertFalse(Round.objects.exists())

        create_numeric_questions(42)
        self.assertEqual(services.create_city_capture_round(self.game.pk).number, 1)


class AtomicityTests(CaptureTestCase):
    def test_failure_midway_keeps_territory_free_and_right_unused(self):
        self.play_round(self.a, self.b, self.c)
        target = self.free_neighbors(self.capital_of(self.a)).first()

        with mock.patch("games.services.capture.award_capture", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.capture(self.a, target)

        target.refresh_from_db()
        self.assertEqual((target.owner_id, target.score), (None, 0))
        self.assertEqual(CaptureRight.objects.get(player_id=self.a).used, 0)
        self.assertEqual(self.score(self.a), 100)
