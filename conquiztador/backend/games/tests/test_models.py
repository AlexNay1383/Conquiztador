from django.test import TestCase
from django.contrib.auth import get_user_model
from games.models import Game, GamePlayer, Round, RoundAnswer
from questions.models import Category, NumericQuestion, ChoiceQuestion, AnswerOption

User = get_user_model()

class GameModelsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u1", email="u1@example.com", password="pwd")
        self.cat = Category.objects.create(name="Cat1")
        self.num_q = NumericQuestion.objects.create(category=self.cat, text="Num?", correct_answer=1)
        
    def test_game_creation(self):
        g = Game.objects.create(created_by=self.user)
        self.assertEqual(g.status, "waiting")

    def test_game_player(self):
        g = Game.objects.create(created_by=self.user)
        p = GamePlayer.objects.create(game=g, user=self.user, player_order=1)
        self.assertEqual(p.score, 0)

    def test_round_creation(self):
        g = Game.objects.create(created_by=self.user)
        r = Round.objects.create(game=g, number=1, question_type="numeric", numeric_question=self.num_q)
        self.assertEqual(r.status, "pending")

    def test_round_answer(self):
        g = Game.objects.create(created_by=self.user)
        p = GamePlayer.objects.create(game=g, user=self.user, player_order=1)
        r = Round.objects.create(game=g, number=1, question_type="numeric", numeric_question=self.num_q)
        ans = RoundAnswer.objects.create(round=r, player=p, numeric_value=1, is_correct=True, points_awarded=10)
        self.assertEqual(ans.points_awarded, 10)
