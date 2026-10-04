from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from games.models import Game, GamePlayer, Round, RoundAnswer
from questions.models import Category, NumericQuestion

User = get_user_model()

class GameConstraintsTests(TestCase):
    def setUp(self):
        self.u1 = User.objects.create_user(username="u1", email="u1@example.com", password="pwd")
        self.u2 = User.objects.create_user(username="u2", email="u2@example.com", password="pwd")
        self.g = Game.objects.create(created_by=self.u1)
        self.cat = Category.objects.create(name="Cat")
        self.num = NumericQuestion.objects.create(category=self.cat, text="?", correct_answer=1)

    def test_unique_player_in_game(self):
        GamePlayer.objects.create(game=self.g, user=self.u1, player_order=1)
        with self.assertRaises(IntegrityError):
            GamePlayer.objects.create(game=self.g, user=self.u1, player_order=2)

    def test_unique_order_in_game(self):
        GamePlayer.objects.create(game=self.g, user=self.u1, player_order=1)
        with self.assertRaises(IntegrityError):
            GamePlayer.objects.create(game=self.g, user=self.u2, player_order=1)

    def test_unique_round_number_in_game(self):
        Round.objects.create(game=self.g, number=1, question_type="numeric", numeric_question=self.num)
        with self.assertRaises(IntegrityError):
            Round.objects.create(game=self.g, number=1, question_type="numeric", numeric_question=self.num)

    def test_unique_answer_in_round(self):
        p1 = GamePlayer.objects.create(game=self.g, user=self.u1, player_order=1)
        r = Round.objects.create(game=self.g, number=1, question_type="numeric", numeric_question=self.num)
        RoundAnswer.objects.create(round=r, player=p1, numeric_value=1)
        with self.assertRaises(IntegrityError):
            RoundAnswer.objects.create(round=r, player=p1, numeric_value=2)
