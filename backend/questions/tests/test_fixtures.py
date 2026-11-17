from django.test import TestCase

from questions.models import AnswerOption, Category, ChoiceQuestion, NumericQuestion


class QuestionBankFixtureTests(TestCase):
    fixtures = ["questions/question_bank.json"]

    def test_fixture_counts(self):
        self.assertEqual(Category.objects.count(), 6)
        self.assertEqual(ChoiceQuestion.objects.count(), 12)
        self.assertEqual(AnswerOption.objects.count(), 48)
        self.assertEqual(NumericQuestion.objects.count(), 12)

    def test_every_choice_question_is_valid(self):
        for question in ChoiceQuestion.objects.all():
            with self.subTest(question=question.pk):
                question.full_clean()

        self.assertEqual(ChoiceQuestion.objects.playable().count(), ChoiceQuestion.objects.count())

    def test_every_numeric_question_has_an_integer_answer(self):
        for question in NumericQuestion.objects.all():
            with self.subTest(question=question.pk):
                question.full_clean()
                self.assertIsInstance(question.correct_answer, int)
