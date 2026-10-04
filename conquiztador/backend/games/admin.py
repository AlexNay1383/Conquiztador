from django.contrib import admin
from .models import Game, GamePlayer, Round, RoundAnswer

class GamePlayerInline(admin.TabularInline):
    model = GamePlayer
    extra = 0

class RoundInline(admin.TabularInline):
    model = Round
    extra = 0

@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ('id', 'status', 'created_by', 'created_at')
    list_filter = ('status',)
    inlines = [GamePlayerInline, RoundInline]

@admin.register(GamePlayer)
class GamePlayerAdmin(admin.ModelAdmin):
    list_display = ('user', 'game', 'player_order', 'score')
    list_filter = ('game',)

@admin.register(Round)
class RoundAdmin(admin.ModelAdmin):
    list_display = ('number', 'game', 'status', 'question_type')
    list_filter = ('game', 'status', 'question_type')

@admin.register(RoundAnswer)
class RoundAnswerAdmin(admin.ModelAdmin):
    list_display = ('player', 'round', 'is_correct', 'points_awarded')
    list_filter = ('round__game',)
