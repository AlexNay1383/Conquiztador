from django.contrib.auth import get_user_model
from django.forms import inlineformset_factory
from django.test import TestCase
from django.urls import reverse

from questions.admin import AnswerOptionFormSet
from questions.models import AnswerOption, ChoiceQuestion

from .factories import create_category


def formset_data(options):
    data = {
        "options-TOTAL_FORMS": str(len(options)),
        "options-INITIAL_FORMS": "0",
        "options-MIN_NUM_FORMS": "4",
        "options-MAX_NUM_FORMS": "4",
    }
    for index, (text, is_correct) in enumerate(options):
        data[f"options-{index}-text"] = text
        if is_correct:
            data[f"options-{index}-is_correct"] = "on"
    return data


class AnswerOptionFormSetTests(TestCase):
    def setUp(self):
        self.question = ChoiceQuestion(category=create_category(), text="?")
        self.formset_class = inlineformset_factory(
            ChoiceQuestion,
            AnswerOption,
            formset=AnswerOptionFormSet,
            fields=["text", "is_correct"],
            extra=0,
            min_num=4,
            max_num=4,
            validate_min=True,
            validate_max=True,
        )

    def test_four_options_with_one_correct_are_accepted(self):
        formset = self.formset_class(
            formset_data([("A", True), ("B", False), ("C", False), ("D", False)]), instance=self.question
        )

        self.assertTrue(formset.is_valid(), formset.non_form_errors())

    def test_wrong_number_of_correct_options_is_rejected(self):
        for flags in ([False] * 4, [True, True, False, False]):
            with self.subTest(flags=flags):
                options = list(zip("ABCD", flags))
                formset = self.formset_class(formset_data(options), instance=self.question)

                self.assertFalse(formset.is_valid())
                self.assertTrue(formset.non_form_errors())


class QuestionAdminPagesTests(TestCase):
    fixtures = ["questions/question_bank.json"]

    def setUp(self):
        admin_user = get_user_model().objects.create_superuser("admin", "admin@example.com", "admin-pass-2024")
        self.client.force_login(admin_user)

    def test_changelists_support_search_and_category_filter(self):
        for model in ("category", "choicequestion", "numericquestion"):
            with self.subTest(model=model):
                url = reverse(f"admin:questions_{model}_changelist")
                self.assertEqual(self.client.get(url).status_code, 200)
                self.assertEqual(self.client.get(url, {"q": "столица"}).status_code, 200)
        response = self.client.get(reverse("admin:questions_choicequestion_changelist"), {"category__id__exact": 1})
        self.assertEqual(response.status_code, 200)

    def test_add_page_shows_four_answer_options(self):
        response = self.client.get(reverse("admin:questions_choicequestion_add"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["inline_admin_formsets"][0].formset.total_form_count(), 4)
