from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from games.maps import MapValidationError, check_game_map, validate_game_map
from games.models import Game, Territory

from .factories import assign_capitals, build_map, create_game_with_players

VALID_CAPITALS = ["skali", "kaliakra", "rozova-dolina"]


class GameMapValidationTests(TestCase):
    def setUp(self):
        self.game = create_game_with_players(3)
        self.territories = build_map(self.game)

    def assert_problem(self, fragment, game=None):
        problems = check_game_map(game or self.game)
        self.assertTrue(any(fragment in problem for problem in problems), problems)

    def test_complete_map_is_valid(self):
        self.assertEqual(check_game_map(self.game), [])

    def test_empty_map_is_not_complete(self):
        empty = create_game_with_players(3, prefix="empty")

        with self.assertRaises(MapValidationError) as context:
            validate_game_map(empty)

        self.assertEqual(context.exception.problems, ["The game has no territories."])

    def test_missing_or_renamed_territory(self):
        Territory.neighbors.through.objects.filter(from_territory=self.territories["tsarevo"]).delete()
        Territory.neighbors.through.objects.filter(to_territory=self.territories["tsarevo"]).delete()
        self.territories["tsarevo"].delete()
        Territory.objects.filter(pk=self.territories["skali"].pk).update(name="Високи скали")

        self.assert_problem("'tsarevo' is missing")
        self.assert_problem("'skali' is named")

    def test_missing_and_extra_edges(self):
        self.territories["skali"].neighbors.remove(self.territories["dunavia"])
        self.territories["skali"].neighbors.add(self.territories["tsarevo"])

        self.assert_problem("Edge dunavia-skali is missing")
        self.assert_problem("Edge skali-tsarevo is not part of the map")

    def test_link_to_another_game(self):
        other_territories = build_map(create_game_with_players(3, prefix="other"))
        Territory.neighbors.through.objects.create(
            from_territory=self.territories["skali"], to_territory=other_territories["tsarevo"]
        )

        self.assert_problem("another game")

    def test_asymmetric_link(self):
        Territory.neighbors.through.objects.filter(
            from_territory=self.territories["skali"], to_territory=self.territories["dunavia"]
        ).delete()

        self.assert_problem("not symmetric")

    def test_owner_from_another_game(self):
        stranger = create_game_with_players(3, prefix="other").players.first()
        Territory.objects.filter(pk=self.territories["skali"].pk).update(owner=stranger)

        self.assert_problem("owned by a player of another game")

    def test_validation_does_not_write(self):
        with CaptureQueriesContext(connection) as queries:
            check_game_map(self.game)

        statements = [query["sql"].split()[0].upper() for query in queries]
        self.assertTrue(statements)
        self.assertEqual(set(statements), {"SELECT"})


class ActiveGameCapitalValidationTests(TestCase):
    def setUp(self):
        self.game = create_game_with_players(3, status=Game.Status.ACTIVE)
        self.territories = build_map(self.game)

    def test_active_game_needs_a_capital_per_player(self):
        self.assertIn("Every player must have exactly one capital.", check_game_map(self.game))

    def test_non_adjacent_capitals_are_valid(self):
        assign_capitals(self.game, self.territories, VALID_CAPITALS)

        self.assertEqual(check_game_map(self.game), [])

    def test_adjacent_capitals_are_reported(self):
        assign_capitals(self.game, self.territories, ["skali", "dunavia", "tsarevo"])

        self.assertTrue(any("are adjacent" in problem for problem in check_game_map(self.game)))

    def test_capital_owned_by_someone_else_is_reported(self):
        assign_capitals(self.game, self.territories, VALID_CAPITALS)
        other_player = self.game.players.order_by("pk")[1]
        Territory.objects.filter(pk=self.territories["skali"].pk).update(owner=other_player)

        self.assertTrue(any("not owned by its player" in problem for problem in check_game_map(self.game)))
