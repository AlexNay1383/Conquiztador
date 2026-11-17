from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Count, Q

REQUIRED_OPTION_COUNT = 4


def validate_answer_options(correct_flags):
    """Validate a choice question's options, given as one `is_correct` flag per option."""
    errors = []
    if len(correct_flags) != REQUIRED_OPTION_COUNT:
        errors.append(
            ValidationError(
                "Въпросът трябва да има точно %(required)d отговора, а има %(count)d.",
                code="option_count",
                params={"required": REQUIRED_OPTION_COUNT, "count": len(correct_flags)},
            )
        )
    if sum(1 for flag in correct_flags if flag) != 1:
        errors.append(ValidationError("Въпросът трябва да има точно един верен отговор.", code="correct_count"))
    if errors:
        raise ValidationError(errors)


class Category(models.Model):
    name = models.CharField("име", max_length=100, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "категория"
        verbose_name_plural = "категории"

    def __str__(self):
        return self.name


class BaseQuestion(models.Model):
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="%(class)ss",
        verbose_name="категория",
    )
    text = models.TextField("текст")

    class Meta:
        abstract = True

    def __str__(self):
        return self.text if len(self.text) <= 80 else f"{self.text[:77]}..."


class ChoiceQuestionQuerySet(models.QuerySet):
    def playable(self):
        """Questions that currently have exactly four options and exactly one correct option."""
        return self.annotate(
            option_count=Count("options"),
            correct_option_count=Count("options", filter=Q(options__is_correct=True)),
        ).filter(option_count=REQUIRED_OPTION_COUNT, correct_option_count=1)


class ChoiceQuestion(BaseQuestion):
    objects = ChoiceQuestionQuerySet.as_manager()
    skip_option_validation = False

    class Meta:
        ordering = ["id"]
        verbose_name = "въпрос с избор"
        verbose_name_plural = "въпроси с избор"

    def clean(self):
        super().clean()
        if self.pk is not None and not self.skip_option_validation:
            validate_answer_options([option.is_correct for option in self.options.all()])


class NumericQuestion(BaseQuestion):
    correct_answer = models.IntegerField("верен отговор")

    class Meta:
        ordering = ["id"]
        verbose_name = "числов въпрос"
        verbose_name_plural = "числови въпроси"


class AnswerOption(models.Model):
    question = models.ForeignKey(
        ChoiceQuestion,
        on_delete=models.CASCADE,
        related_name="options",
        verbose_name="въпрос",
    )
    text = models.CharField("текст", max_length=255)
    is_correct = models.BooleanField("верен", default=False)

    class Meta:
        ordering = ["id"]
        verbose_name = "отговор"
        verbose_name_plural = "отговори"

    def __str__(self):
        return self.text
