from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import RestrictedError
from django.test import TestCase

from games.maps import get_game_territories, get_player_capital, get_player_territories
from games.models import Capital, Game, Player, Round, Territory

from .factories import assign_capitals, build_map, create_game_with_players


class TerritoryConstraintTests(TestCase):
    def setUp(self):
        self.game = create_game_with_players(3)
        Territory.objects.create(game=self.game, slug="skali", name="Скали")

    def assert_rejected(self, **fields):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Territory.objects.create(game=self.game, **fields)

    def test_name_and_slug_are_unique_per_game(self):
        self.assert_rejected(slug="skali", name="Други скали")
        self.assert_rejected(slug="skali-2", name="СКАЛИ")

    def test_same_name_and_slug_in_another_game_are_separate_records(self):
        other = create_game_with_players(3, prefix="other")

        Territory.objects.create(game=other, slug="skali", name="Скали")

        self.assertEqual(Territory.objects.filter(slug="skali").count(), 2)

    def test_database_rejects_non_normalized_values(self):
        cases = [
            dict(slug="Skali-2", name="Нови скали"),
            dict(slug="skali--2", name="Нови скали"),
            dict(slug="", name="Нови скали"),
            dict(slug="skali-2", name=" Нови скали"),
            dict(slug="skali-2", name="Нови  скали"),
            dict(slug="skali-2", name=""),
        ]
        for fields in cases:
            with self.subTest(**fields):
                self.assert_rejected(**fields)

    def test_score_cannot_be_negative(self):
        self.assert_rejected(slug="dunavia", name="Дунавия", score=-1)

    def test_full_clean_normalizes_name_and_slug(self):
        territory = Territory(game=self.game, slug="  Dunavia ", name="  Дунавия   ")

        territory.full_clean()

        self.assertEqual((territory.slug, territory.name), ("dunavia", "Дунавия"))

    def test_full_clean_reports_case_insensitive_duplicate(self):
        with self.assertRaises(ValidationError):
            Territory(game=self.game, slug="skali-2", name="скали").full_clean()


class NeighborTests(TestCase):
    def setUp(self):
        self.game = create_game_with_players(3)
        self.first = Territory.objects.create(game=self.game, slug="skali", name="Скали")
        self.second = Territory.objects.create(game=self.game, slug="dunavia", name="Дунавия")

    def test_neighbors_are_symmetric(self):
        self.first.neighbors.add(self.second)

        self.assertIn(self.second, self.first.neighbors.all())
        self.assertIn(self.first, self.second.neighbors.all())

    def test_territory_cannot_neighbor_itself(self):
        with self.assertRaises(ValidationError), transaction.atomic():
            self.first.neighbors.add(self.first)

    def test_neighbor_must_be_from_the_same_game(self):
        other_game = create_game_with_players(3, prefix="other")
        foreign = Territory.objects.create(game=other_game, slug="madara", name="Мадара")

        with self.assertRaises(ValidationError), transaction.atomic():
            self.first.neighbors.add(foreign)

        self.assertFalse(self.first.neighbors.exists())


class OwnershipTests(TestCase):
    def setUp(self):
        self.game = create_game_with_players(3, status=Game.Status.ACTIVE)
        self.territories = build_map(self.game)
        assign_capitals(self.game, self.territories, ["skali", "kaliakra", "rozova-dolina"])
        self.player = self.game.players.order_by("pk").first()

    def test_owner_must_be_from_the_same_game(self):
        stranger = create_game_with_players(3, prefix="other").players.first()
        territory = self.territories["dunavia"]
        territory.owner = stranger

        with self.assertRaises(ValidationError) as context:
            territory.full_clean()

        self.assertIn("owner", context.exception.message_dict)

    def test_capital_owner_cannot_change(self):
        capital_territory = self.territories["skali"]
        capital_territory.owner = self.game.players.order_by("pk")[1]

        with self.assertRaises(ValidationError) as context:
            capital_territory.full_clean()

        self.assertIn("owner", context.exception.message_dict)

    def test_territory_cannot_move_to_another_game(self):
        territory = self.territories["dunavia"]
        territory.game = create_game_with_players(3, prefix="other")

        with self.assertRaises(ValidationError) as context:
            territory.full_clean()

        self.assertIn("game", context.exception.message_dict)

    def test_player_territories_and_capital(self):
        self.territories["dunavia"].owner = self.player
        self.territories["dunavia"].save()

        self.assertEqual(
            set(get_player_territories(self.player).values_list("slug", flat=True)), {"skali", "dunavia"}
        )
        self.assertEqual(get_player_capital(self.player).territory.slug, "skali")
        self.assertEqual(get_game_territories(self.game).count(), 15)


class CapitalTests(TestCase):
    def setUp(self):
        self.game = create_game_with_players(3, status=Game.Status.ACTIVE)
        self.territories = build_map(self.game)
        self.players = list(self.game.players.order_by("pk"))

    def make_owned(self, slug, player):
        territory = self.territories[slug]
        territory.owner = player
        territory.save()
        return territory

    def test_capital_starts_with_full_health(self):
        capital = Capital.objects.create(territory=self.make_owned("skali", self.players[0]), player=self.players[0])

        self.assertEqual(capital.health, 3)
        self.assertEqual(capital.game, self.game)

    def test_health_range(self):
        territory = self.make_owned("skali", self.players[0])
        for health in (-1, 4):
            with self.subTest(health=health):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Capital.objects.create(territory=territory, player=self.players[0], health=health)

    def test_destroyed_capital_keeps_its_record_and_owner(self):
        capital = Capital.objects.create(territory=self.make_owned("skali", self.players[0]), player=self.players[0])

        Capital.objects.filter(pk=capital.pk).update(health=0)

        capital.refresh_from_db()
        self.assertEqual((capital.health, capital.territory.owner, capital.player), (0, self.players[0], self.players[0]))

    def test_one_capital_per_player_and_per_territory(self):
        first = self.make_owned("skali", self.players[0])
        second = self.make_owned("kaliakra", self.players[0])
        Capital.objects.create(territory=first, player=self.players[0])

        with self.assertRaises(IntegrityError), transaction.atomic():
            Capital.objects.create(territory=second, player=self.players[0])
        with self.assertRaises(IntegrityError), transaction.atomic():
            Capital.objects.create(territory=first, player=self.players[1])

    def test_capital_must_be_owned_by_its_player_in_the_same_game(self):
        unowned = Capital(territory=self.territories["skali"], player=self.players[0])
        stranger = create_game_with_players(3, prefix="other").players.first()
        foreign = Capital(territory=self.make_owned("kaliakra", self.players[1]), player=stranger)

        for capital in (unowned, foreign):
            with self.subTest(player=capital.player_id):
                with self.assertRaises(ValidationError):
                    capital.full_clean()

    def test_missing_capital_is_reported_as_none_without_creating_one(self):
        self.assertIsNone(get_player_capital(self.players[0]))
        self.assertFalse(Capital.objects.exists())


class DeletionTests(TestCase):
    def setUp(self):
        self.game = create_game_with_players(3, status=Game.Status.ACTIVE)
        self.territories = build_map(self.game)
        assign_capitals(self.game, self.territories, ["skali", "kaliakra", "rozova-dolina"])
        Round.objects.create(game=self.game, number=1, type=Round.Type.CITY_CAPTURE)

    def test_deleting_the_game_removes_its_whole_state(self):
        self.game.delete()

        self.assertFalse(Territory.objects.exists())
        self.assertFalse(Capital.objects.exists())
        self.assertFalse(Player.objects.exists())
        self.assertFalse(Territory.neighbors.through.objects.exists())

    def test_owning_player_cannot_be_deleted(self):
        player = self.game.players.first()

        with self.assertRaises(RestrictedError):
            player.delete()
        with self.assertRaises(RestrictedError):
            player.user.delete()

        self.assertEqual(Capital.objects.count(), 3)

    def test_capital_territory_cannot_be_deleted(self):
        with self.assertRaises(RestrictedError):
            self.territories["skali"].delete()

        self.assertTrue(Capital.objects.filter(territory__slug="skali").exists())
