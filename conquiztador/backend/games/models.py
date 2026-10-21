from django.db import models
from django.conf import settings
from questions.models import ChoiceQuestion, NumericQuestion, AnswerOption

WAITING = "waiting"
IN_PROGRESS = "in_progress"
FINISHED = "finished"
CANCELLED = "cancelled"

STATUS_CHOICES = [
    (WAITING, "Waiting"),
    (IN_PROGRESS, "In Progress"),
    (FINISHED, "Finished"),
    (CANCELLED, "Cancelled"),
]

PENDING = "pending"
OPEN = "open"
CLOSED = "closed"
EVALUATED = "evaluated"

ROUND_STATUS_CHOICES = [
    (PENDING, "Pending"),
    (OPEN, "Open"),
    (CLOSED, "Closed"),
    (EVALUATED, "Evaluated"),
]

CHOICE = "choice"
NUMERIC = "numeric"

QUESTION_TYPE_CHOICES = [
    (CHOICE, "Choice"),
    (NUMERIC, "Numeric"),
]


COLOR_RED = "red"
COLOR_GREEN = "green"
COLOR_BLUE = "blue"

COLOR_CHOICES = [
    (COLOR_RED, "Red"),
    (COLOR_GREEN, "Green"),
    (COLOR_BLUE, "Blue"),
]


class Game(models.Model):
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=WAITING)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Game #{self.id} ({self.get_status_display()})"

class GamePlayer(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='players')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    color = models.CharField(max_length=10, choices=COLOR_CHOICES)
    player_order = models.PositiveSmallIntegerField()
    score = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['game', 'user'], ['game', 'player_order'], ['game', 'color']]

    def __str__(self):
        return f"{self.user.username} in Game #{self.game_id}"

class Round(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='rounds')
    number = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=ROUND_STATUS_CHOICES, default=PENDING)
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPE_CHOICES)
    choice_question = models.ForeignKey(ChoiceQuestion, null=True, blank=True, on_delete=models.PROTECT)
    numeric_question = models.ForeignKey(NumericQuestion, null=True, blank=True, on_delete=models.PROTECT)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [['game', 'number']]

    def __str__(self):
        return f"Round {self.number} (Game #{self.game_id})"

class RoundAnswer(models.Model):
    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name='answers')
    player = models.ForeignKey(GamePlayer, on_delete=models.CASCADE, related_name='answers')
    selected_option = models.ForeignKey(AnswerOption, null=True, blank=True, on_delete=models.PROTECT)
    numeric_value = models.IntegerField(null=True, blank=True)
    is_correct = models.BooleanField(null=True, blank=True)
    points_awarded = models.IntegerField(default=0)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [['round', 'player']]

    def __str__(self):
        return f"Answer by {self.player.user.username} in Round {self.round.number}"


class WaitingRoomEntry(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='waiting_room_entry',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Waiting room entries"

    def __str__(self):
        return f"{self.user.username} waiting since {self.created_at}"
