from django.test import TestCase
from django.core.management import call_command
from questions.models import Category, ChoiceQuestion, NumericQuestion

class FixtureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('loaddata', 'questions/question_bank.json')

    def test_fixture_counts(self):
        self.assertEqual(Category.objects.count(), 6)
        self.assertEqual(ChoiceQuestion.objects.count(), 12)
        self.assertEqual(NumericQuestion.objects.count(), 12)

    def test_choice_questions_validity(self):
        for q in ChoiceQuestion.objects.all():
            self.assertEqual(q.options.count(), 4)
            self.assertEqual(q.options.filter(is_correct=True).count(), 1)
