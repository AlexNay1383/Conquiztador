from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count

from .models import Game, Player, Round


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


@admin.register(Round)
class RoundAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ["game", "number", "type", "status", "winner", "created_at", "completed_at"]
    list_filter = ["game", "type", "status"]
    list_select_related = ["game", "winner__user"]
