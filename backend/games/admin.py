from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count

from .models import (
    Capital,
    CaptureRight,
    Game,
    Player,
    Round,
    RoundAnswer,
    RoundPlacement,
    RoundQuestion,
    RoundQuestionOption,
    ScoreEvent,
    Territory,
)


class ReadOnlyAdminMixin:
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class PlayerInline(admin.TabularInline):
    model = Player
    fields = ["user", "color", "score"]
    readonly_fields = fields
    extra = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ["id", "created_at", "status", "player_count"]
    list_filter = ["status"]
    readonly_fields = ["status", "created_at"]
    inlines = [PlayerInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(player_count=Count("players"))

    @admin.display(description="играчи", ordering="player_count")
    def player_count(self, game):
        return game.player_count


class PlayerAdminForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ["user", "game", "color", "score"]

    def clean(self):
        cleaned_data = super().clean()
        game = cleaned_data.get("game") if self.instance.pk is None else self.instance.game
        if game is None:
            return cleaned_data

        # The admin change view runs inside a transaction, so this lock is held until the save.
        game = Game.objects.select_for_update().get(pk=game.pk)
        if game.status != Game.Status.WAITING:
            raise ValidationError("Играчите могат да се променят само преди началото на играта.")
        if self.instance.pk is None and game.players.count() >= Game.PLAYER_COUNT:
            raise ValidationError("Играта вече има трима играчи.")
        return cleaned_data


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    form = PlayerAdminForm
    list_display = ["user", "game", "color", "score"]
    list_filter = ["game", "color"]
    search_fields = ["user__username"]
    list_select_related = ["user", "game"]
    autocomplete_fields = ["user"]
    actions = None

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return []
        if obj.game.status != Game.Status.WAITING:
            return ["user", "game", "color", "score"]
        return ["game"]

    def has_delete_permission(self, request, obj=None):
        return obj is None or obj.game.status == Game.Status.WAITING

    def delete_model(self, request, obj):
        game = Game.objects.select_for_update().get(pk=obj.game_id)
        if game.status != Game.Status.WAITING:
            raise PermissionDenied("Играчите могат да се премахват само преди началото на играта.")
        super().delete_model(request, obj)


class ReadOnlyInline(admin.TabularInline):
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class RoundQuestionInline(ReadOnlyInline):
    model = RoundQuestion
    fields = ["sequence", "kind", "text", "first_place", "place_count", "status", "started_at", "deadline"]
    show_change_link = True


class RoundPlacementInline(ReadOnlyInline):
    model = RoundPlacement
    fields = ["place", "player", "decided_by"]


class CaptureRightInline(ReadOnlyInline):
    model = CaptureRight
    fields = ["order", "player", "allowed", "used"]


class RoundAnswerInline(ReadOnlyInline):
    model = RoundAnswer
    fields = ["player", "numeric_value", "option", "received_at"]


class RoundQuestionOptionInline(ReadOnlyInline):
    model = RoundQuestionOption
    fields = ["position", "text", "is_correct", "source_option"]


@admin.register(Round)
class RoundAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = [
        "game",
        "number",
        "type",
        "status",
        "attacker",
        "target",
        "winner",
        "unresolved_reason",
        "created_at",
        "completed_at",
    ]
    list_filter = ["game", "type", "status"]
    list_select_related = ["game", "winner__user", "attacker__user", "target"]
    inlines = [RoundQuestionInline, RoundPlacementInline, CaptureRightInline]


@admin.register(RoundQuestion)
class RoundQuestionAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ["round", "sequence", "kind", "text", "status", "deadline"]
    list_filter = ["game", "kind", "status"]
    search_fields = ["text"]
    list_select_related = ["round"]
    inlines = [RoundQuestionOptionInline, RoundAnswerInline]


@admin.register(Territory)
class TerritoryAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ["name", "slug", "game", "owner", "score", "neighbor_names"]
    list_filter = ["game", "owner"]
    search_fields = ["name", "slug"]
    list_select_related = ["game", "owner__user"]
    fields = ["game", "name", "slug", "owner", "score", "neighbor_names"]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("neighbors")

    @admin.display(description="съседи")
    def neighbor_names(self, territory):
        return ", ".join(sorted(neighbor.name for neighbor in territory.neighbors.all()))


@admin.register(Capital)
class CapitalAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ["territory", "player", "health"]
    list_filter = ["territory__game"]
    search_fields = ["player__user__username", "player__user__profile__nickname", "territory__name", "territory__slug"]
    list_select_related = ["territory", "player__user"]


@admin.register(ScoreEvent)
class ScoreEventAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ["created_at", "player", "kind", "points", "score_before", "score_after", "territory", "formula"]
    list_filter = ["game", "kind"]
    search_fields = ["player__user__username", "territory__name"]
    list_select_related = ["player__user", "territory"]
