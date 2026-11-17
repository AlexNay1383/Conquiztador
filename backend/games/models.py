from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class GameStatus(models.TextChoices):
    WAITING = "waiting", "Изчакване на играчи"
    ACTIVE = "active", "Активна"
    COMPLETED = "completed", "Завършена"


class PlayerColor(models.TextChoices):
    RED = "red", "Червен"
    GREEN = "green", "Зелен"
    BLUE = "blue", "Син"


class RoundType(models.TextChoices):
    CITY_CAPTURE = "city_capture", "Завземане на територия"
    BATTLE = "battle", "Битка"
    CAPITAL_ATTACK = "capital_attack", "Атака на столица"
    BONUS = "bonus", "Бонус"


class RoundStatus(models.TextChoices):
    PENDING = "pending", "Предстоящ"
    ACTIVE = "active", "Активен"
    COMPLETED = "completed", "Завършен"


class Game(models.Model):
    PLAYER_COUNT = 3
    Status = GameStatus

    created_at = models.DateTimeField("създадена", auto_now_add=True)
    status = models.CharField("статус", max_length=16, choices=GameStatus.choices, default=GameStatus.WAITING)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "игра"
        verbose_name_plural = "игри"
        constraints = [
            models.CheckConstraint(condition=Q(status__in=GameStatus.values), name="game_status_valid"),
        ]

    def __str__(self):
        return f"Игра #{self.pk}"

    def get_current_round(self):
        return self.rounds.order_by("-number").first()

    def is_active(self):
        return self.status == self.Status.ACTIVE

    def is_completed(self):
        return self.status == self.Status.COMPLETED


class Player(models.Model):
    Color = PlayerColor

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="players",
        verbose_name="потребител",
    )
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="players", verbose_name="игра")
    score = models.IntegerField("точки", default=0)
    color = models.CharField("цвят", max_length=8, choices=PlayerColor.choices)

    class Meta:
        ordering = ["game", "id"]
        verbose_name = "играч"
        verbose_name_plural = "играчи"
        constraints = [
            models.UniqueConstraint(fields=["user", "game"], name="unique_user_per_game"),
            models.UniqueConstraint(fields=["game", "color"], name="unique_color_per_game"),
            models.CheckConstraint(condition=Q(score__gte=0), name="player_score_gte_0"),
            models.CheckConstraint(condition=Q(color__in=PlayerColor.values), name="player_color_valid"),
        ]

    def __str__(self):
        return f"{self.user} ({self.get_color_display()}, игра #{self.game_id})"


class Round(models.Model):
    Type = RoundType
    Status = RoundStatus

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="rounds", verbose_name="игра")
    number = models.PositiveIntegerField("номер")
    type = models.CharField("тип", max_length=16, choices=RoundType.choices)
    status = models.CharField("статус", max_length=16, choices=RoundStatus.choices, default=RoundStatus.PENDING)
    winner = models.ForeignKey(
        Player,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="won_rounds",
        verbose_name="победител",
    )
    created_at = models.DateTimeField("създаден", auto_now_add=True)
    completed_at = models.DateTimeField("завършен", null=True, blank=True)

    class Meta:
        ordering = ["game", "number"]
        verbose_name = "рунд"
        verbose_name_plural = "рундове"
        constraints = [
            models.UniqueConstraint(fields=["game", "number"], name="unique_round_number_per_game"),
            models.UniqueConstraint(
                fields=["game"],
                condition=Q(status="active"),
                name="one_active_round_per_game",
            ),
            models.CheckConstraint(condition=Q(number__gte=1), name="round_number_gte_1"),
            models.CheckConstraint(condition=Q(type__in=RoundType.values), name="round_type_valid"),
            models.CheckConstraint(condition=Q(status__in=RoundStatus.values), name="round_status_valid"),
            models.CheckConstraint(
                condition=Q(status="completed", completed_at__isnull=False)
                | (~Q(status="completed") & Q(completed_at__isnull=True, winner__isnull=True)),
                name="round_completion_fields_match_status",
            ),
        ]

    def __str__(self):
        return f"Рунд {self.number} ({self.get_type_display()}), игра #{self.game_id}"

    def clean(self):
        super().clean()
        if self.winner_id is not None and self.game_id is not None and self.winner.game_id != self.game_id:
            raise ValidationError({"winner": "Победителят трябва да е играч от същата игра."})
