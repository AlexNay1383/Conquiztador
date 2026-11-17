from django.test import SimpleTestCase

from games.map_definition import PROJECT_MAP, MapDefinition, TerritoryDefinition
from games.maps import (
    MapValidationError,
    check_definition,
    definition_adjacency,
    find_capital_triples,
    validate_definition,
)
from games.models import normalize_territory_name, normalize_territory_slug, territory_name_key


def ring(count, extra_edges=()):
    """A cycle of `count` territories t0..t{count-1}: connected, every node with two neighbours."""
    territories = tuple(TerritoryDefinition(f"t{index}", f"Територия {index}") for index in range(count))
    edges = tuple((f"t{index}", f"t{(index + 1) % count}") for index in range(count))
    return MapDefinition(territories, edges + tuple(extra_edges))


class ProjectMapTests(SimpleTestCase):
    def test_project_map_is_valid(self):
        self.assertEqual(check_definition(PROJECT_MAP), [])
        validate_definition(PROJECT_MAP)

    def test_project_map_shape(self):
        adjacency = definition_adjacency(PROJECT_MAP)

        self.assertEqual(len(adjacency), 15)
        self.assertEqual(len(PROJECT_MAP.edges), 25)
        self.assertTrue(all(len(neighbors) >= 2 for neighbors in adjacency.values()))

    def test_documented_capital_triple_is_valid(self):
        triples = find_capital_triples(definition_adjacency(PROJECT_MAP))

        self.assertIn(("kaliakra", "rozova-dolina", "skali"), triples)


class DefinitionRuleTests(SimpleTestCase):
    def assert_problem(self, definition, fragment):
        problems = check_definition(definition)
        self.assertTrue(any(fragment in problem for problem in problems), problems)
        with self.assertRaises(MapValidationError):
            validate_definition(definition)

    def test_small_ring_is_valid(self):
        self.assertEqual(check_definition(ring(9)), [])

    def test_territory_count(self):
        for count in (6, 8, 10, 24):
            with self.subTest(count=count):
                self.assert_problem(ring(count), "territories; expected")

    def test_names_and_slugs(self):
        base = ring(9)
        cases = {
            "Duplicate slug": (TerritoryDefinition("t0", "Друга"),),
            "Duplicate name": (TerritoryDefinition("x", "ТЕРИТОРИЯ 0"),),
            "Invalid slug": (TerritoryDefinition("Bad Slug", "Нова"),),
            "Invalid name": (TerritoryDefinition("x", "  Нова   земя "),),
        }
        for fragment, replacement in cases.items():
            with self.subTest(fragment):
                definition = MapDefinition(base.territories[:-1] + replacement, base.edges)
                self.assert_problem(definition, fragment)

    def test_edges(self):
        cases = {
            "unknown territory": ring(9, extra_edges=[("t0", "missing")]),
            "its own neighbour": ring(9, extra_edges=[("t0", "t0")]),
            "more than once": ring(9, extra_edges=[("t1", "t0")]),
        }
        for fragment, definition in cases.items():
            with self.subTest(fragment):
                self.assert_problem(definition, fragment)

    def test_every_territory_needs_two_neighbours(self):
        path = MapDefinition(ring(9).territories, ring(9).edges[:-1])

        self.assert_problem(path, "fewer than two neighbours")

    def test_map_must_be_connected(self):
        triangle = [("t0", "t1"), ("t1", "t2"), ("t2", "t0")]
        hexagon = [(f"t{index}", f"t{index + 1}") for index in range(3, 8)] + [("t8", "t3")]
        definition = MapDefinition(ring(9).territories, tuple(triangle + hexagon))

        self.assert_problem(definition, "not connected")

    def test_capital_triple_must_exist(self):
        territories = ring(9).territories
        complete = tuple(
            (first.slug, second.slug)
            for index, first in enumerate(territories)
            for second in territories[index + 1 :]
        )

        self.assert_problem(MapDefinition(territories, complete), "mutually non-adjacent")


class NormalizationTests(SimpleTestCase):
    def test_names_are_trimmed_and_collapsed(self):
        self.assertEqual(normalize_territory_name("  Розова \t  долина "), "Розова долина")

    def test_names_compare_case_insensitively(self):
        self.assertEqual(territory_name_key("РОЗОВА Долина"), territory_name_key("розова долина"))

    def test_slugs_are_trimmed_and_lowercased(self):
        self.assertEqual(normalize_territory_slug("  Zlaten-Grozd "), "zlaten-grozd")
