from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from games.models import Capital, Game, Player, Territory

from games import services

from .factories import (
    assign_capitals,
    build_map,
    create_active_game,
    create_battle_game,
    create_choice_questions,
    create_game_with_players,
    create_numeric_questions,
    create_user,
)


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

    def test_territory_and_capital_pages_work_without_games(self):
        for model in ("territory", "capital"):
            with self.subTest(model=model):
                response = self.client.get(reverse(f"admin:games_{model}_changelist"))
                self.assertEqual(response.status_code, 200)

    def test_territory_and_capital_pages_search_and_filter(self):
        game = create_game_with_players(3, status=Game.Status.ACTIVE)
        territories = build_map(game)
        assign_capitals(game, territories, ["skali", "kaliakra", "rozova-dolina"])
        pages = [
            (reverse("admin:games_territory_changelist"), {"q": "skali", "game__id__exact": game.pk}),
            (reverse("admin:games_territory_changelist"), {"owner__id__exact": game.players.first().pk}),
            (reverse("admin:games_capital_changelist"), {"q": "Скали", "territory__game__id__exact": game.pk}),
        ]
        for url, params in pages:
            with self.subTest(url=url, params=params):
                response = self.client.get(url, params)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["cl"].result_count, 1)

    def test_map_structure_cannot_be_edited(self):
        game = create_game_with_players(3, status=Game.Status.ACTIVE)
        territories = build_map(game)
        assign_capitals(game, territories, ["skali", "kaliakra", "rozova-dolina"])
        territory = territories["dunavia"]
        capital = Capital.objects.first()

        responses = [
            self.client.get(reverse("admin:games_territory_add")),
            self.client.get(reverse("admin:games_capital_add")),
            self.client.post(reverse("admin:games_territory_change", args=[territory.pk]), {"name": "X"}),
            self.client.post(reverse("admin:games_territory_delete", args=[territory.pk]), {"post": "yes"}),
            self.client.post(reverse("admin:games_capital_delete", args=[capital.pk]), {"post": "yes"}),
        ]

        self.assertEqual({response.status_code for response in responses}, {403})
        territory.refresh_from_db()
        self.assertEqual(territory.name, "Дунавия")
        view = self.client.get(reverse("admin:games_territory_change", args=[territory.pk]))
        self.assertEqual(view.status_code, 200)
        self.assertContains(view, "Скали")

    def test_round_pages_show_questions_answers_and_placements(self):
        game, players = create_active_game(prefix="admin")
        create_numeric_questions(100)
        round_ = services.create_city_capture_round(game.pk)
        services.start_round(round_.pk)
        for offset, player in enumerate(players):
            services.submit_answer(round_.pk, player.pk, 100 + offset)
        question = round_.questions.get()

        round_page = self.client.get(reverse("admin:games_round_change", args=[round_.pk]))
        question_page = self.client.get(reverse("admin:games_roundquestion_change", args=[question.pk]))
        changelist = self.client.get(reverse("admin:games_roundquestion_changelist"), {"kind__exact": "numeric"})

        self.assertContains(round_page, question.text)
        self.assertContains(question_page, "101")
        self.assertEqual(changelist.status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:games_roundquestion_add")).status_code, 403)

    def test_battle_pages_show_options_and_choices(self):
        game, players = create_battle_game(prefix="battle")
        create_choice_questions(1)
        target = Territory.objects.get(game=game, slug="zhitno-pole")
        round_ = services.create_battle(game.pk, players[0].pk, target.pk)
        services.start_round(round_.pk)
        question = round_.questions.get()
        services.submit_answer(round_.pk, players[0].pk, question.options.get(is_correct=True).source_option_id)

        round_page = self.client.get(reverse("admin:games_round_change", args=[round_.pk]))
        question_page = self.client.get(reverse("admin:games_roundquestion_change", args=[question.pk]))
        changelist = self.client.get(reverse("admin:games_round_changelist"), {"type__exact": "battle"})

        self.assertContains(round_page, "Житно поле")
        self.assertContains(question_page, "Въпрос с избор 1?")
        self.assertEqual(question_page.context["inline_admin_formsets"][0].formset.total_form_count(), 4)
        self.assertEqual(changelist.context["cl"].result_count, 1)

    def test_game_status_is_read_only(self):
        game = create_game_with_players(3)

        response = self.client.get(reverse("admin:games_game_change", args=[game.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="status"')
