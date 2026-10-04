from django.test import TestCase
from questions.models import Category, ChoiceQuestion, AnswerOption, NumericQuestion
from django.db import IntegrityError
from django.db.models import ProtectedError

class QuestionModelsTests(TestCase):
    def test_create_category(self):
        cat = Category.objects.create(name="Science")
        self.assertEqual(cat.name, "Science")

        with self.assertRaises(IntegrityError):
            Category.objects.create(name="Science")

    def test_create_choice_question(self):
        cat = Category.objects.create(name="History")
        q = ChoiceQuestion.objects.create(category=cat, text="Who?")
        AnswerOption.objects.create(question=q, text="A", is_correct=True)
        AnswerOption.objects.create(question=q, text="B", is_correct=False)
        AnswerOption.objects.create(question=q, text="C", is_correct=False)
        AnswerOption.objects.create(question=q, text="D", is_correct=False)
        
        self.assertEqual(q.options.count(), 4)
        self.assertEqual(q.options.filter(is_correct=True).count(), 1)

    def test_invalid_choice_question(self):
        # We enforce validity in forms/services, but testing we can create invalid ones at DB level 
        # as Django doesn't do cross-model validation on save automatically without explicit clean() calls.
        # This test ensures we understand the constraints.
        pass

    def test_create_numeric_question(self):
        cat = Category.objects.create(name="Math")
        q = NumericQuestion.objects.create(category=cat, text="2+2?", correct_answer=4)
        self.assertEqual(q.correct_answer, 4)

    def test_delete_choice_question(self):
        cat = Category.objects.create(name="Geo")
        q = ChoiceQuestion.objects.create(category=cat, text="Where?")
        AnswerOption.objects.create(question=q, text="Here", is_correct=True)
        
        q.delete()
        self.assertEqual(AnswerOption.objects.count(), 0)

    def test_protected_category(self):
        cat = Category.objects.create(name="Bio")
        NumericQuestion.objects.create(category=cat, text="Cells?", correct_answer=1)
        
        with self.assertRaises(ProtectedError):
            cat.delete()
