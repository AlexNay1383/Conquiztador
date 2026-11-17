from django.db import IntegrityError, transaction
from django.test import TestCase

from games import services
from games.exceptions import InvalidInputError, InvalidStateError
from games.models import Game, Player

from .factories import create_game_with_players, create_user


class AddPlayerTests(TestCase):
    def setUp(self):
        self.game = services.create_game()
        self.users = [create_user(f"user{index}") for index in range(4)]

    def test_three_users_with_three_colors(self):
        for user, color in zip(self.users, Player.Color.values):
            services.add_player(self.game.pk, user.pk, color)

        players = self.game.players.all()
        self.assertEqual(players.count(), 3)
        self.assertEqual({player.color for player in players}, {"red", "green", "blue"})
        self.assertEqual({player.score for player in players}, {0})

    def test_free_color_is_assigned_when_none_is_given(self):
        services.add_player(self.game.pk, self.users[0].pk, Player.Color.RED)

        player = services.add_player(self.game.pk, self.users[1].pk)

        self.assertEqual(player.color, Player.Color.GREEN)

    def test_fourth_player_is_refused(self):
        for user in self.users[:3]:
            services.add_player(self.game.pk, user.pk)

        with self.assertRaises(InvalidStateError) as context:
            services.add_player(self.game.pk, self.users[3].pk)

        self.assertEqual(context.exception.code, "game_full")

    def test_invalid_players_are_refused(self):
        services.add_player(self.game.pk, self.users[0].pk, Player.Color.RED)
        cases = {
            "user_already_joined": (self.users[0].pk, Player.Color.BLUE),
            "color_taken": (self.users[1].pk, Player.Color.RED),
            "invalid_color": (self.users[1].pk, "purple"),
        }
        for code, (user_id, color) in cases.items():
            with self.subTest(code=code):
                with self.assertRaises(InvalidInputError) as context:
                    services.add_player(self.game.pk, user_id, color)

                self.assertEqual(context.exception.code, code)
                self.assertEqual(self.game.players.count(), 1)

    def test_players_cannot_join_an_active_game(self):
        game = create_game_with_players(2, status=Game.Status.ACTIVE)

        with self.assertRaises(InvalidStateError) as context:
            services.add_player(game.pk, self.users[0].pk)

        self.assertEqual(context.exception.code, "game_not_waiting")


class RemovePlayerTests(TestCase):
    def test_player_can_leave_a_waiting_game(self):
        game = create_game_with_players(2)

        services.remove_player(game.players.first().pk)

        self.assertEqual(game.players.count(), 1)

    def test_player_cannot_leave_an_active_game(self):
        game = create_game_with_players(3, status=Game.Status.ACTIVE)

        with self.assertRaises(InvalidStateError):
            services.remove_player(game.players.first().pk)

        self.assertEqual(game.players.count(), 3)


class PlayerConstraintTests(TestCase):
    def setUp(self):
        self.game = create_game_with_players(1)
        self.existing = self.game.players.get()

    def test_database_rejects_invalid_players(self):
        other_user = create_user("other")
        cases = {
            "repeated user": dict(user=self.existing.user, color=Player.Color.GREEN),
            "repeated color": dict(user=other_user, color=self.existing.color),
            "negative score": dict(user=other_user, color=Player.Color.GREEN, score=-1),
            "unknown color": dict(user=other_user, color="purple"),
        }
        for name, fields in cases.items():
            with self.subTest(name):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Player.objects.create(game=self.game, **fields)

    def test_same_user_and_color_are_allowed_in_another_game(self):
        other_game = services.create_game()

        Player.objects.create(game=other_game, user=self.existing.user, color=self.existing.color)

        self.assertEqual(Player.objects.filter(user=self.existing.user).count(), 2)
