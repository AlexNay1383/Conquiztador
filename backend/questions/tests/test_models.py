from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError
from django.test import TestCase

from questions.models import AnswerOption, Category, ChoiceQuestion, NumericQuestion

from .factories import create_category, create_choice_question, create_numeric_question


class CategoryTests(TestCase):
    def test_create_category(self):
        category = Category(name="История")

        category.full_clean()
        category.save()

        self.assertEqual(str(category), "История")

    def test_name_is_unique(self):
        Category.objects.create(name="История")

        with self.assertRaises(ValidationError):
            Category(name="История").full_clean()
        with self.assertRaises(IntegrityError):
            Category.objects.create(name="История")

    def test_category_with_questions_cannot_be_deleted(self):
        category = create_category()
        create_numeric_question(category=category)

        with self.assertRaises(ProtectedError):
            category.delete()

        self.assertTrue(Category.objects.filter(pk=category.pk).exists())


class ChoiceQuestionTests(TestCase):
    def test_valid_choice_question(self):
        question = create_choice_question()

        question.full_clean()

        self.assertEqual(question.options.count(), 4)
        self.assertEqual(question.options.get(is_correct=True).text, "София")
        self.assertIn(question, ChoiceQuestion.objects.playable())

    def test_invalid_choice_questions(self):
        cases = {
            "three options": [("A", True), ("B", False), ("C", False)],
            "five options": [("A", True), ("B", False), ("C", False), ("D", False), ("E", False)],
            "no correct option": [("A", False), ("B", False), ("C", False), ("D", False)],
            "two correct options": [("A", True), ("B", True), ("C", False), ("D", False)],
        }
        for name, options in cases.items():
            with self.subTest(name):
                question = create_choice_question(text=name, options=options)

                with self.assertRaises(ValidationError):
                    question.full_clean()
                self.assertNotIn(question, ChoiceQuestion.objects.playable())

    def test_deleting_question_deletes_its_options(self):
        question = create_choice_question()

        question.delete()

        self.assertFalse(AnswerOption.objects.exists())


class NumericQuestionTests(TestCase):
    def test_create_numeric_question(self):
        question = create_numeric_question(correct_answer=28)

        question.full_clean()

        self.assertEqual(NumericQuestion.objects.get(pk=question.pk).correct_answer, 28)

    def test_correct_answer_is_required_integer(self):
        category = create_category()
        for value in (None, "many"):
            with self.subTest(value=value):
                question = NumericQuestion(category=category, text="?", correct_answer=value)

                with self.assertRaises(ValidationError) as context:
                    question.full_clean()
                self.assertIn("correct_answer", context.exception.message_dict)

    def test_same_category_holds_both_question_types(self):
        category = create_category()
        create_choice_question(category=category)
        create_numeric_question(category=category)

        self.assertEqual(category.choicequestions.count(), 1)
        self.assertEqual(category.numericquestions.count(), 1)
