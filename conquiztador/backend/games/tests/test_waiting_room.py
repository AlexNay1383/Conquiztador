from django.test import TestCase
from django.contrib.auth import get_user_model

from games.models import Game, GamePlayer, WaitingRoomEntry, WAITING, COLOR_CHOICES
from games.services import try_form_game, join_waiting_room

User = get_user_model()


class FormGameWithFiveWaitersTest(TestCase):

    def setUp(self):
        self.users = []
        for i in range(5):
            user = User.objects.create_user(
                username=f"user{i}",
                email=f"user{i}@example.com",
                password="testpass123",
            )
            self.users.append(user)
            WaitingRoomEntry.objects.create(user=user)

    def test_form_game_with_five_waiters(self):
        self.assertEqual(WaitingRoomEntry.objects.count(), 5)
        self.assertEqual(Game.objects.count(), 0)

        game = try_form_game()

        self.assertIsNotNone(game)
        self.assertEqual(Game.objects.count(), 1)
        self.assertEqual(game.status, WAITING)

        players = GamePlayer.objects.filter(game=game)
        self.assertEqual(players.count(), 3)

        for player in players:
            self.assertEqual(player.score, 0)

        colors = set(players.values_list('color', flat=True))
        allowed_colors = {c[0] for c in COLOR_CHOICES}
        self.assertEqual(len(colors), 3)
        self.assertTrue(colors.issubset(allowed_colors))

        orders = set(players.values_list('player_order', flat=True))
        self.assertEqual(len(orders), 3)

        remaining_entries = WaitingRoomEntry.objects.all()
        self.assertEqual(remaining_entries.count(), 2)

        game_user_ids = set(players.values_list('user_id', flat=True))
        remaining_user_ids = set(remaining_entries.values_list('user_id', flat=True))
        self.assertEqual(len(game_user_ids & remaining_user_ids), 0)

        all_user_ids = {u.id for u in self.users}
        self.assertEqual(game_user_ids | remaining_user_ids, all_user_ids)


class FormGameWithTwoWaitersTest(TestCase):

    def setUp(self):
        self.users = []
        for i in range(2):
            user = User.objects.create_user(
                username=f"user{i}",
                email=f"user{i}@example.com",
                password="testpass123",
            )
            self.users.append(user)
            WaitingRoomEntry.objects.create(user=user)

    def test_no_game_with_two_waiters(self):
        self.assertEqual(WaitingRoomEntry.objects.count(), 2)
        self.assertEqual(Game.objects.count(), 0)

        game = try_form_game()

        self.assertIsNone(game)
        self.assertEqual(Game.objects.count(), 0)
        self.assertEqual(GamePlayer.objects.count(), 0)

        self.assertEqual(WaitingRoomEntry.objects.count(), 2)
        remaining_user_ids = set(
            WaitingRoomEntry.objects.values_list('user_id', flat=True)
        )
        expected_user_ids = {u.id for u in self.users}
        self.assertEqual(remaining_user_ids, expected_user_ids)
