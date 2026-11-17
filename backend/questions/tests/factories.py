from questions.models import AnswerOption, Category, ChoiceQuestion, NumericQuestion


def create_category(name="География"):
    return Category.objects.get_or_create(name=name)[0]


def create_choice_question(text="Коя е столицата на България?", category=None, options=None):
    """`options` is a list of (text, is_correct); by default four options with the first one correct."""
    question = ChoiceQuestion.objects.create(category=category or create_category(), text=text)
    if options is None:
        options = [("София", True), ("Пловдив", False), ("Варна", False), ("Бургас", False)]
    for option_text, is_correct in options:
        AnswerOption.objects.create(question=question, text=option_text, is_correct=is_correct)
    return question


def create_numeric_question(text="Колко области има България?", correct_answer=28, category=None):
    return NumericQuestion.objects.create(
        category=category or create_category(), text=text, correct_answer=correct_answer
    )
