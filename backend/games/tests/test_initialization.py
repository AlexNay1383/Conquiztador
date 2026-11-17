import itertools
import random
from io import StringIO
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import TestCase

from games import services
from games.exceptions import InvalidStateError, NotFoundError
from games.map_definition import PROJECT_MAP, MapDefinition
from games.maps import check_game_map, definition_adjacency, edge_key, find_capital_triples
from games.models import Capital, Game, Player, Round, Territory

from .factories import build_map, create_game_with_players, create_user


def game_state(game):
    """A comparable snapshot of everything initialization may touch."""
    return {
        "status": Game.objects.get(pk=game.pk).status,
        "players": sorted(Player.objects.filter(game=game).values_list("pk", "user_id", "color", "score")),
        "territories": sorted(Territory.objects.filter(game=game).values_list("pk", "slug", "owner_id", "score")),
        "capitals": sorted(Capital.objects.filter(player__game=game).values_list("pk", "territory_id", "player_id")),
        "rounds": sorted(Round.objects.filter(game=game).values_list("pk", "number", "status")),
    }


class SuccessfulInitializationTests(TestCase):
    def setUp(self):
        self.game = create_game_with_players(3)
        self.players_before = sorted(self.game.players.values_list("pk", "user_id", "color", "score"))

        services.initialize_game(self.game.pk)

    def test_game_becomes_active(self):
        self.game.refresh_from_db()
        self.assertEqual(self.game.status, Game.Status.ACTIVE)

    def test_territories_match_the_definition(self):
        territories = Territory.objects.filter(game=self.game)

        self.assertEqual(territories.count(), 15)
        self.assertEqual(
            set(territories.values_list("slug", "name")),
            {(item.slug, item.name) for item in PROJECT_MAP.territories},
        )
        self.assertEqual(set(territories.values_list("score", flat=True)), {0})

    def test_edges_match_the_definition(self):
        links = Territory.neighbors.through.objects.filter(from_territory__game=self.game).values_list(
            "from_territory__slug", "to_territory__slug"
        )

        self.assertEqual(len(links), 2 * len(PROJECT_MAP.edges))
        self.assertEqual({edge_key(*link) for link in links}, {edge_key(*edge) for edge in PROJECT_MAP.edges})

    def test_three_non_adjacent_capitals_one_per_player(self):
        capitals = list(Capital.objects.filter(player__game=self.game).select_related("territory"))
        adjacency = definition_adjacency(PROJECT_MAP)

        self.assertEqual(len(capitals), 3)
        self.assertEqual({capital.player_id for capital in capitals}, set(self.game.players.values_list("pk", flat=True)))
        for capital in capitals:
            self.assertEqual(capital.territory.owner_id, capital.player_id)
            self.assertEqual(capital.health, 3)
        for first, second in itertools.combinations(capitals, 2):
            self.assertNotIn(second.territory.slug, adjacency[first.territory.slug])

    def test_other_territories_are_free(self):
        self.assertEqual(Territory.objects.filter(game=self.game, owner__isnull=True).count(), 12)

    def test_players_are_unchanged(self):
        self.assertEqual(sorted(self.game.players.values_list("pk", "user_id", "color", "score")), self.players_before)

    def test_result_passes_full_map_validation(self):
        self.assertEqual(check_game_map(self.game), [])

    def test_repeated_initialization_is_refused_without_changes(self):
        before = game_state(self.game)

        with self.assertRaises(InvalidStateError) as context:
            services.initialize_game(self.game.pk)

        self.assertEqual(context.exception.code, "game_not_waiting")
        self.assertEqual(game_state(self.game), before)


class InitializationIsolationTests(TestCase):
    def test_existing_rounds_and_other_games_are_untouched(self):
        other = create_game_with_players(3, prefix="other")
        services.initialize_game(other.pk)
        other_before = game_state(other)
        game = create_game_with_players(3)
        Round.objects.create(game=game, number=1, type=Round.Type.BONUS)
        rounds_before = game_state(game)["rounds"]

        services.initialize_game(game.pk)

        self.assertEqual(game_state(other), other_before)
        self.assertEqual(game_state(game)["rounds"], rounds_before)

    def test_creating_a_game_or_adding_players_does_not_initialize(self):
        game = services.create_game()
        for index in range(3):
            services.add_player(game.pk, create_user(f"auto{index}").pk)

        game.refresh_from_db()
        self.assertEqual(game.status, Game.Status.WAITING)
        self.assertFalse(Territory.objects.filter(game=game).exists())


class RefusedInitializationTests(TestCase):
    def assert_refused(self, game_id, code, **kwargs):
        with self.assertRaises(InvalidStateError) as context:
            services.initialize_game(game_id, **kwargs)
        self.assertEqual(context.exception.code, code)

    def test_missing_game(self):
        with self.assertRaises(NotFoundError) as context:
            services.initialize_game(999_999)

        self.assertEqual(context.exception.code, "game_not_found")

    def test_game_must_be_waiting(self):
        for status in (Game.Status.ACTIVE, Game.Status.COMPLETED):
            with self.subTest(status=status):
                game = create_game_with_players(3, prefix=status, status=status)
                self.assert_refused(game.pk, "game_not_waiting")

    def test_exactly_three_players(self):
        game = create_game_with_players(2)

        self.assert_refused(game.pk, "wrong_player_count")

    def test_partial_map_is_refused_and_kept(self):
        game = create_game_with_players(3)
        Territory.objects.create(game=game, slug="skali", name="Скали")
        before = game_state(game)

        self.assert_refused(game.pk, "map_already_exists")

        self.assertEqual(game_state(game), before)

    def test_invalid_definition_is_refused(self):
        game = create_game_with_players(3)
        broken = MapDefinition(PROJECT_MAP.territories, PROJECT_MAP.edges[:-5])
        before = game_state(game)

        self.assert_refused(game.pk, "invalid_map_definition", definition=broken)

        self.assertEqual(game_state(game), before)

    def test_definition_without_capital_triple_is_refused(self):
        territories = PROJECT_MAP.territories[:9]
        complete = tuple(itertools.combinations([item.slug for item in territories], 2))
        game = create_game_with_players(3)

        self.assert_refused(game.pk, "invalid_map_definition", definition=MapDefinition(territories, complete))


class AtomicityTests(TestCase):
    def test_failure_midway_rolls_everything_back_and_allows_a_retry(self):
        game = create_game_with_players(3)
        before = game_state(game)

        with mock.patch("games.services.initialization.Capital.objects.bulk_create", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                services.initialize_game(game.pk)

        self.assertEqual(game_state(game), before)
        self.assertFalse(Territory.neighbors.through.objects.exists())

        services.initialize_game(game.pk)
        game.refresh_from_db()
        self.assertEqual(game.status, Game.Status.ACTIVE)


class CapitalRandomnessTests(TestCase):
    def test_choice_is_made_among_all_valid_triples_and_players_are_shuffled(self):
        game = create_game_with_players(3)
        rng = mock.Mock(wraps=random.Random(7))

        services.initialize_game(game.pk, rng=rng)

        offered_triples = rng.choice.call_args.args[0]
        self.assertEqual(offered_triples, find_capital_triples(definition_adjacency(PROJECT_MAP)))
        shuffled_players, count = rng.sample.call_args.args
        self.assertEqual(sorted(player.pk for player in shuffled_players), sorted(game.players.values_list("pk", flat=True)))
        self.assertEqual(count, 3)

    def test_input_order_does_not_fix_the_assignment(self):
        assignments = set()
        for seed in range(6):
            game = create_game_with_players(3, prefix=f"seed{seed}")
            services.initialize_game(game.pk, rng=random.Random(seed))
            first_player = game.players.order_by("pk").first()
            assignments.add(first_player.capital.territory.slug)

        self.assertGreater(len(assignments), 1)

    def test_an_unlucky_pick_cannot_fail(self):
        game = create_game_with_players(3)
        rng = mock.Mock()
        rng.choice.side_effect = lambda items: items[0]
        rng.sample.side_effect = lambda items, count: list(items)[:count]

        services.initialize_game(game.pk, rng=rng)

        self.assertEqual(check_game_map(game), [])


class AfterActivationTests(TestCase):
    def test_composition_is_frozen(self):
        game = create_game_with_players(3)
        services.initialize_game(game.pk)

        with self.assertRaises(InvalidStateError):
            services.add_player(game.pk, create_user("late").pk)
        with self.assertRaises(InvalidStateError):
            services.remove_player(game.players.first().pk)
        self.assertEqual(game.players.count(), 3)


class StartGameCommandTests(TestCase):
    def test_command_initializes_the_game(self):
        game = create_game_with_players(3)
        out = StringIO()

        call_command("start_game", game.pk, stdout=out)

        self.assertIn(f"Game #{game.pk} is active.", out.getvalue())
        self.assertEqual(out.getvalue().count("capital "), 3)

    def test_command_reports_the_refusal_code(self):
        game = create_game_with_players(2)

        with self.assertRaisesMessage(CommandError, "[wrong_player_count]"):
            call_command("start_game", game.pk, stdout=StringIO())


class ExistingMapHelperTests(TestCase):
    def test_build_map_helper_matches_initialization(self):
        built = create_game_with_players(3, prefix="built")
        build_map(built)
        initialized = create_game_with_players(3, prefix="init")
        services.initialize_game(initialized.pk)

        def links(game):
            return {
                edge_key(*pair)
                for pair in Territory.neighbors.through.objects.filter(from_territory__game=game).values_list(
                    "from_territory__slug", "to_territory__slug"
                )
            }

        self.assertEqual(links(built), links(initialized))
