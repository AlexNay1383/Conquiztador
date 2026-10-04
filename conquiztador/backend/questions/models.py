from django.db import models
from django.core.exceptions import ValidationError

class Category(models.Model):
    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name

class BaseQuestion(models.Model):
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="%(class)ss",
    )
    text = models.TextField()

    class Meta:
        abstract = True

    def __str__(self):
        return self.text

class ChoiceQuestion(BaseQuestion):
    def clean(self):
        super().clean()
        # We can't easily validate related objects in model clean before they are saved,
        # but the milestone says:
        # - Точно четири свързани AnswerOption обекта
        # - Точно един AnswerOption с is_correct=True
        # We will handle this in form/admin or in a separate validator method if needed.
        pass

class NumericQuestion(BaseQuestion):
    correct_answer = models.IntegerField()

class AnswerOption(models.Model):
    question = models.ForeignKey(ChoiceQuestion, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return self.text
