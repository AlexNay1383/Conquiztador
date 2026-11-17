from django import forms
from django.contrib import admin
from django.db.models import Exists, OuterRef
from django.forms.models import BaseInlineFormSet

from .models import (
    REQUIRED_OPTION_COUNT,
    AnswerOption,
    Category,
    ChoiceQuestion,
    NumericQuestion,
    validate_answer_options,
)


class AnswerOptionFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        kept = [
            form
            for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE", False)
        ]
        validate_answer_options([form.cleaned_data.get("is_correct", False) for form in kept])


class ChoiceQuestionAdminForm(forms.ModelForm):
    def _post_clean(self):
        # The inline formset validates the submitted options; the saved ones may be outdated.
        self.instance.skip_option_validation = True
        try:
            super()._post_clean()
        finally:
            self.instance.skip_option_validation = False


class AnswerOptionInline(admin.TabularInline):
    model = AnswerOption
    formset = AnswerOptionFormSet
    extra = 0
    min_num = REQUIRED_OPTION_COUNT
    max_num = REQUIRED_OPTION_COUNT
    validate_min = True
    validate_max = True


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]


@admin.register(ChoiceQuestion)
class ChoiceQuestionAdmin(admin.ModelAdmin):
    form = ChoiceQuestionAdminForm
    list_display = ["text", "category", "is_playable"]
    list_filter = ["category"]
    search_fields = ["text"]
    list_select_related = ["category"]
    inlines = [AnswerOptionInline]

    def get_queryset(self, request):
        playable = ChoiceQuestion.objects.playable().filter(pk=OuterRef("pk"))
        return super().get_queryset(request).annotate(playable=Exists(playable))

    @admin.display(description="валиден", boolean=True, ordering="playable")
    def is_playable(self, question):
        return question.playable


@admin.register(NumericQuestion)
class NumericQuestionAdmin(admin.ModelAdmin):
    list_display = ["text", "category", "correct_answer"]
    list_filter = ["category"]
    search_fields = ["text"]
    list_select_related = ["category"]
