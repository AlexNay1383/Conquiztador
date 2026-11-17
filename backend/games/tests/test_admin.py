from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from games.models import Game, Player

from .factories import create_game_with_players, create_user


class GamesAdminTests(TestCase):
    def setUp(self):
        admin_user = get_user_model().objects.create_superuser("admin", "admin@example.com", "admin-pass-2024")
        self.client.force_login(admin_user)

    def add_player(self, game, user, color):
        return self.client.post(
            reverse("admin:games_player_add"),
            {"game": game.pk, "user": user.pk, "color": color, "score": 0},
        )

    def test_changelists_and_filters_load(self):
        game = create_game_with_players(3)
        pages = [
            (reverse("admin:games_game_changelist"), {"status__exact": "waiting"}),
            (reverse("admin:games_player_changelist"), {"q": "player", "game__id__exact": game.pk, "color__exact": "red"}),
            (reverse("admin:games_round_changelist"), {"type__exact": "battle", "status__exact": "pending"}),
        ]
        for url, params in pages:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url, params).status_code, 200)

    def test_player_can_be_added_to_a_waiting_game(self):
        game = create_game_with_players(2)

        response = self.add_player(game, create_user("newcomer"), Player.Color.BLUE)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(game.players.count(), 3)

    def test_full_or_started_games_reject_new_players(self):
        full = create_game_with_players(3, prefix="full")
        active = create_game_with_players(2, prefix="active", status=Game.Status.ACTIVE)
        for game, color in ((full, Player.Color.RED), (active, Player.Color.BLUE)):
            with self.subTest(status=game.status):
                response = self.add_player(game, create_user(f"late{game.pk}"), color)

                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["adminform"].form.non_field_errors())
        self.assertEqual((full.players.count(), active.players.count()), (3, 2))

    def test_players_of_started_games_cannot_be_deleted(self):
        game = create_game_with_players(3, status=Game.Status.ACTIVE)
        player = game.players.first()

        response = self.client.post(reverse("admin:games_player_delete", args=[player.pk]), {"post": "yes"})

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Player.objects.filter(pk=player.pk).exists())

    def test_game_status_is_read_only(self):
        game = create_game_with_players(3)

        response = self.client.get(reverse("admin:games_game_change", args=[game.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="status"')
