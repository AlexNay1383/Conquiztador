from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, RegexValidator
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"
NAME_PATTERN = r"^\S+( \S+)*$"
CAPITAL_MAX_HEALTH = 3


def normalize_territory_name(value):
    """Trim and collapse whitespace runs to single spaces; names are compared case-insensitively."""
    return " ".join(str(value).split())


def normalize_territory_slug(value):
    return str(value).strip().lower()


def territory_name_key(value):
    return normalize_territory_name(value).casefold()


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


class UnresolvedReason(models.TextChoices):
    NONE = "", "—"
    QUESTION_LIMIT = "question_limit", "Достигнат лимит от въпроси"
    QUESTION_BANK_EXHAUSTED = "question_bank_exhausted", "Няма подходящ неизползван въпрос"
    NOT_ENOUGH_ANSWERS = "not_enough_answers", "Недостатъчно приети отговори"


class Round(models.Model):
    Type = RoundType
    Status = RoundStatus
    UnresolvedReason = UnresolvedReason

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="rounds", verbose_name="игра")
    number = models.PositiveIntegerField("номер")
    type = models.CharField("тип", max_length=16, choices=RoundType.choices)
    status = models.CharField("статус", max_length=16, choices=RoundStatus.choices, default=RoundStatus.PENDING)
    participants = models.ManyToManyField(Player, related_name="rounds", verbose_name="участници")
    places_needed = models.PositiveSmallIntegerField("необходими места", default=1)
    free_territories_at_creation = models.PositiveSmallIntegerField(
        "свободни територии при създаване", null=True, blank=True
    )
    winner = models.ForeignKey(
        Player,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="won_rounds",
        verbose_name="победител",
    )
    unresolved_reason = models.CharField(
        "причина за непълно класиране",
        max_length=32,
        choices=UnresolvedReason.choices,
        default=UnresolvedReason.NONE,
        blank=True,
    )
    created_at = models.DateTimeField("създаден", auto_now_add=True)
    started_at = models.DateTimeField("започнат", null=True, blank=True)
    completed_at = models.DateTimeField("завършен", null=True, blank=True)

    class Meta:
        ordering = ["game", "number"]
        verbose_name = "рунд"
        verbose_name_plural = "рундове"
        constraints = [
            models.UniqueConstraint(fields=["game", "number"], name="unique_round_number_per_game"),
            models.UniqueConstraint(
                fields=["game"],
                condition=Q(status__in=["pending", "active"]),
                name="one_unfinished_round_per_game",
            ),
            models.CheckConstraint(condition=Q(number__gte=1), name="round_number_gte_1"),
            models.CheckConstraint(condition=Q(places_needed__gte=1), name="round_places_needed_gte_1"),
            models.CheckConstraint(condition=Q(type__in=RoundType.values), name="round_type_valid"),
            models.CheckConstraint(condition=Q(status__in=RoundStatus.values), name="round_status_valid"),
            models.CheckConstraint(
                condition=Q(unresolved_reason__in=UnresolvedReason.values), name="round_unresolved_reason_valid"
            ),
            models.CheckConstraint(
                condition=Q(status="completed", completed_at__isnull=False)
                | (~Q(status="completed") & Q(completed_at__isnull=True, winner__isnull=True)),
                name="round_completion_fields_match_status",
            ),
            models.CheckConstraint(
                condition=Q(status="pending", started_at__isnull=True)
                | (~Q(status="pending") & Q(started_at__isnull=False)),
                name="round_started_at_matches_status",
            ),
            models.CheckConstraint(
                condition=(Q(status="completed") & (Q(winner__isnull=False) | ~Q(unresolved_reason="")))
                | (~Q(status="completed") & Q(unresolved_reason="")),
                name="round_without_winner_has_reason",
            ),
        ]

    def __str__(self):
        return f"Рунд {self.number} ({self.get_type_display()}), игра #{self.game_id}"

    def clean(self):
        super().clean()
        if self.winner_id is not None and self.game_id is not None and self.winner.game_id != self.game_id:
            raise ValidationError({"winner": "Победителят трябва да е играч от същата игра."})

    def get_current_question(self):
        return self.questions.exclude(status=QuestionStatus.COMPLETED).order_by("sequence").first()

    def get_ranking(self):
        """Decided places as {place: player}; missing places are not decided."""
        return {placement.place: placement.player for placement in self.placements.select_related("player")}


class Territory(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="territories", verbose_name="игра")
    name = models.CharField(
        "име",
        max_length=100,
        validators=[RegexValidator(NAME_PATTERN, "Името не може да е празно или да има излишни интервали.")],
    )
    slug = models.CharField(
        "идентификатор",
        max_length=50,
        validators=[RegexValidator(SLUG_PATTERN, "Само малки латински букви, цифри и единични тирета.")],
    )
    neighbors = models.ManyToManyField("self", symmetrical=True, blank=True, verbose_name="съседи")
    owner = models.ForeignKey(
        Player,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="territories",
        verbose_name="собственик",
    )
    score = models.PositiveIntegerField("точки", default=0)

    class Meta:
        ordering = ["game", "slug"]
        verbose_name = "територия"
        verbose_name_plural = "територии"
        constraints = [
            models.UniqueConstraint(fields=["game", "slug"], name="unique_territory_slug_per_game"),
            models.UniqueConstraint(
                Lower("name"),
                "game",
                name="unique_territory_name_per_game",
                violation_error_message="Територия с това име вече съществува в играта.",
            ),
            models.CheckConstraint(condition=Q(slug__regex=SLUG_PATTERN), name="territory_slug_format"),
            models.CheckConstraint(condition=Q(name__regex=NAME_PATTERN), name="territory_name_format"),
        ]

    def __str__(self):
        return f"{self.name} (игра #{self.game_id})"

    def clean_fields(self, exclude=None):
        self.name = normalize_territory_name(self.name)
        self.slug = normalize_territory_slug(self.slug)
        super().clean_fields(exclude=exclude)

    def clean(self):
        super().clean()

        errors = {}
        if self.pk is not None:
            stored = Territory.objects.filter(pk=self.pk).values("game_id", "owner_id").first()
            if stored and stored["game_id"] != self.game_id:
                errors["game"] = "Територията не може да се премести в друга игра."
            capital = Capital.objects.filter(territory_id=self.pk).values_list("player_id", flat=True).first()
            if capital is not None and capital != self.owner_id:
                errors["owner"] = "Собственикът на столица е нейният играч."
        if self.owner_id is not None and self.game_id is not None and self.owner.game_id != self.game_id:
            errors["owner"] = "Собственикът трябва да е играч от същата игра."
        if errors:
            raise ValidationError(errors)


class Capital(models.Model):
    territory = models.OneToOneField(
        Territory, on_delete=models.RESTRICT, related_name="capital", verbose_name="територия"
    )
    player = models.OneToOneField(Player, on_delete=models.CASCADE, related_name="capital", verbose_name="играч")
    health = models.PositiveSmallIntegerField(
        "здраве", default=CAPITAL_MAX_HEALTH, validators=[MaxValueValidator(CAPITAL_MAX_HEALTH)]
    )

    class Meta:
        ordering = ["territory__game", "player"]
        verbose_name = "столица"
        verbose_name_plural = "столици"
        constraints = [
            models.CheckConstraint(
                condition=Q(health__gte=0, health__lte=CAPITAL_MAX_HEALTH), name="capital_health_range"
            ),
        ]

    def __str__(self):
        return f"Столица {self.territory.name} ({self.player})"

    @property
    def game(self):
        return self.territory.game

    def clean(self):
        super().clean()
        if self.territory_id is None or self.player_id is None:
            return
        if self.territory.game_id != self.player.game_id:
            raise ValidationError("Столицата и играчът трябва да са от една игра.")
        if self.territory.owner_id != self.player_id:
            raise ValidationError({"territory": "Столицата трябва да е собственост на своя играч."})


class QuestionKind(models.TextChoices):
    NUMERIC = "numeric", "Числов"


class QuestionStatus(models.TextChoices):
    PENDING = "pending", "Предстоящ"
    ACTIVE = "active", "Активен"
    COMPLETED = "completed", "Завършен"


class RoundQuestion(models.Model):
    """One question asked within a round, with a snapshot of its content at the time it was asked."""

    Kind = QuestionKind
    Status = QuestionStatus

    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="questions", verbose_name="рунд")
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="asked_questions", verbose_name="игра")
    sequence = models.PositiveSmallIntegerField("пореден номер")
    kind = models.CharField("вид", max_length=16, choices=QuestionKind.choices)
    numeric_question = models.ForeignKey(
        "questions.NumericQuestion",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="asked_in",
        verbose_name="числов въпрос",
    )
    text = models.TextField("текст")
    correct_answer = models.BigIntegerField("верен отговор", null=True, blank=True)
    participants = models.ManyToManyField(Player, related_name="asked_questions", verbose_name="участници")
    first_place = models.PositiveSmallIntegerField("първо определяно място")
    place_count = models.PositiveSmallIntegerField("брой определяни места")
    status = models.CharField("статус", max_length=16, choices=QuestionStatus.choices, default=QuestionStatus.PENDING)
    started_at = models.DateTimeField("начало", null=True, blank=True)
    deadline = models.DateTimeField("краен срок", null=True, blank=True)
    completed_at = models.DateTimeField("завършен", null=True, blank=True)

    class Meta:
        ordering = ["round", "sequence"]
        verbose_name = "зададен въпрос"
        verbose_name_plural = "зададени въпроси"
        constraints = [
            models.UniqueConstraint(fields=["round", "sequence"], name="unique_question_sequence_per_round"),
            models.UniqueConstraint(
                fields=["round"],
                condition=Q(status__in=["pending", "active"]),
                name="one_open_question_per_round",
            ),
            models.UniqueConstraint(
                fields=["game", "numeric_question"],
                condition=Q(numeric_question__isnull=False),
                name="numeric_question_once_per_game",
            ),
            models.CheckConstraint(condition=Q(sequence__gte=1), name="question_sequence_gte_1"),
            models.CheckConstraint(
                condition=Q(first_place__gte=1, place_count__gte=1), name="question_places_positive"
            ),
            models.CheckConstraint(
                condition=Q(kind="numeric", numeric_question__isnull=False, correct_answer__isnull=False),
                name="question_kind_matches_source",
            ),
            models.CheckConstraint(
                condition=Q(status="pending", started_at__isnull=True, deadline__isnull=True)
                | (~Q(status="pending") & Q(started_at__isnull=False, deadline__gt=models.F("started_at"))),
                name="question_timing_matches_status",
            ),
            models.CheckConstraint(
                condition=Q(status="completed", completed_at__isnull=False)
                | (~Q(status="completed") & Q(completed_at__isnull=True)),
                name="question_completion_matches_status",
            ),
        ]

    def __str__(self):
        return f"Въпрос {self.sequence} от {self.round}"

    @property
    def last_place(self):
        return self.first_place + self.place_count - 1


class RoundAnswer(models.Model):
    question = models.ForeignKey(
        RoundQuestion, on_delete=models.CASCADE, related_name="answers", verbose_name="въпрос"
    )
    player = models.ForeignKey(Player, on_delete=models.RESTRICT, related_name="answers", verbose_name="играч")
    numeric_value = models.BigIntegerField("числов отговор", null=True, blank=True)
    received_at = models.DateTimeField("получен")

    class Meta:
        ordering = ["question", "received_at"]
        verbose_name = "отговор"
        verbose_name_plural = "отговори"
        constraints = [
            models.UniqueConstraint(fields=["question", "player"], name="one_answer_per_player_per_question"),
        ]

    def __str__(self):
        return f"{self.player}: {self.numeric_value}"


class RoundPlacement(models.Model):
    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="placements", verbose_name="рунд")
    place = models.PositiveSmallIntegerField("място")
    player = models.ForeignKey(Player, on_delete=models.RESTRICT, related_name="placements", verbose_name="играч")
    decided_by = models.ForeignKey(
        RoundQuestion, on_delete=models.CASCADE, related_name="placements", verbose_name="определено от"
    )

    class Meta:
        ordering = ["round", "place"]
        verbose_name = "класиране"
        verbose_name_plural = "класирания"
        constraints = [
            models.UniqueConstraint(fields=["round", "place"], name="unique_place_per_round"),
            models.UniqueConstraint(fields=["round", "player"], name="one_place_per_player_per_round"),
            models.CheckConstraint(condition=Q(place__gte=1), name="placement_place_gte_1"),
        ]

    def __str__(self):
        return f"{self.place}. {self.player}"


class CaptureRight(models.Model):
    """How many free territories a ranked player of a city-capture round may still pick, and in which order."""

    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="capture_rights", verbose_name="рунд")
    player = models.ForeignKey(
        Player, on_delete=models.RESTRICT, related_name="capture_rights", verbose_name="играч"
    )
    order = models.PositiveSmallIntegerField("ред")
    allowed = models.PositiveSmallIntegerField("разрешени избори")
    used = models.PositiveSmallIntegerField("използвани избори", default=0)

    class Meta:
        ordering = ["round", "order"]
        verbose_name = "право за избор"
        verbose_name_plural = "права за избор"
        constraints = [
            models.UniqueConstraint(fields=["round", "order"], name="unique_capture_order_per_round"),
            models.UniqueConstraint(fields=["round", "player"], name="one_capture_right_per_player_per_round"),
            models.CheckConstraint(condition=Q(allowed__gte=1), name="capture_right_allowed_gte_1"),
            models.CheckConstraint(condition=Q(used__lte=models.F("allowed")), name="capture_right_used_lte_allowed"),
        ]

    def __str__(self):
        return f"{self.player}: {self.used}/{self.allowed}"

    @property
    def remaining(self):
        return self.allowed - self.used


class ScoreKind(models.TextChoices):
    ROUND_WIN = "round_win", "Победа в рунд"
    CAPTURE = "capture", "Завземане на територия"


class ScoreEvent(models.Model):
    """One change of a player's score, with the values before and after and the formula that produced it."""

    Kind = ScoreKind

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="score_events", verbose_name="игра")
    player = models.ForeignKey(Player, on_delete=models.RESTRICT, related_name="score_events", verbose_name="играч")
    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="score_events", verbose_name="рунд")
    territory = models.ForeignKey(
        Territory,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="score_events",
        verbose_name="територия",
    )
    kind = models.CharField("вид", max_length=16, choices=ScoreKind.choices)
    points = models.PositiveIntegerField("точки")
    score_before = models.PositiveIntegerField("точки преди")
    score_after = models.PositiveIntegerField("точки след")
    territory_score_before = models.PositiveIntegerField("точки на територията преди", null=True, blank=True)
    territory_score_after = models.PositiveIntegerField("точки на територията след", null=True, blank=True)
    formula = models.CharField("изчисление", max_length=200)
    created_at = models.DateTimeField("създадено", auto_now_add=True)

    class Meta:
        ordering = ["game", "created_at", "id"]
        verbose_name = "точкуване"
        verbose_name_plural = "точкувания"
        constraints = [
            models.CheckConstraint(condition=Q(points__gt=0), name="score_event_points_positive"),
            models.CheckConstraint(
                condition=Q(score_after=models.F("score_before") + models.F("points")),
                name="score_event_after_is_before_plus_points",
            ),
            models.CheckConstraint(
                condition=Q(kind__in=ScoreKind.values), name="score_event_kind_valid"
            ),
            models.UniqueConstraint(
                fields=["round"], condition=Q(kind="round_win"), name="one_win_award_per_round"
            ),
            models.UniqueConstraint(
                fields=["round", "territory"], condition=Q(kind="capture"), name="one_capture_award_per_territory_per_round"
            ),
        ]

    def __str__(self):
        return f"{self.player}: +{self.points} ({self.get_kind_display()})"
