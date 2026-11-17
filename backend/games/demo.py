"""Scripted play used by the demo management commands; it only calls the public services."""

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import transaction

from accounts.models import Profile
from games import services
from games.exceptions import GameError
from games.models import ScoreEvent, Territory
from games.services.capture import pending_capture_rights
from questions.models import NumericQuestion

DEMO_USERS = ["demo_red", "demo_green", "demo_blue"]
DEMO_PASSWORD = "demo-pass-2024"


def ensure_demo_users():
    users = []
    for username in DEMO_USERS:
        user, created = get_user_model().objects.get_or_create(
            username=username, defaults={"email": f"{username}@example.com"}
        )
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save()
            Profile.objects.create(user=user, nickname=username)
        users.append(user)
    return users


def create_demo_game():
    if not NumericQuestion.objects.exists():
        call_command("loaddata", "questions/question_bank.json", verbosity=0)
    with transaction.atomic():
        game = services.create_game()
        for user in ensure_demo_users():
            services.add_player(game.pk, user.pk)
    services.initialize_game(game.pk)
    return game


class DemoPlayer:
    def __init__(self, game, rng, write):
        self.game = game
        self.rng = rng
        self.write = write
        self.names = {player.pk: player.user.username for player in game.players.select_related("user")}

    def describe_event(self, event):
        target = f" {event.territory.slug}" if event.territory else ""
        self.write(
            f"  {self.names[event.player_id]} {event.get_kind_display().lower()}{target}: "
            f"{event.score_before} -> {event.score_after} ({event.formula})"
        )

    def play_conquest(self):
        while Territory.objects.filter(game=self.game, owner__isnull=True).exists():
            try:
                round_ = services.create_city_capture_round(self.game.pk, rng=self.rng)
            except GameError as error:
                self.write(f"Stopped: [{error.code}] {error.message}")
                return False
            self.play_city_capture(round_)
            self.use_rights()
        return True

    def play_city_capture(self, round_):
        services.start_round(round_.pk)
        self.write(
            f"Round {round_.number} ({round_.free_territories_at_creation} free, "
            f"{round_.places_needed} place(s) needed)"
        )
        while (question := round_.get_current_question()) is not None:
            group = list(question.participants.order_by("pk"))
            for player in self.rng.sample(group, len(group)):
                services.submit_answer(round_.pk, player.pk, question.correct_answer + self.rng.randint(-20, 20))
        round_.refresh_from_db()
        ranking = ", ".join(f"{place}. {self.names[player.pk]}" for place, player in sorted(round_.get_ranking().items()))
        reason = f" [{round_.unresolved_reason}]" if round_.unresolved_reason else ""
        self.write(f"  questions: {round_.questions.count()}, ranking: {ranking or '-'}{reason}")
        for event in ScoreEvent.objects.filter(round=round_, kind=ScoreEvent.Kind.ROUND_WIN):
            self.describe_event(event)

    def use_rights(self):
        while (right := pending_capture_rights(self.game).first()) is not None:
            target = self.rng.choice(services.get_capture_options(self.game.pk, right.player_id))
            services.capture_territory(self.game.pk, right.player_id, target.pk)
            self.describe_event(
                ScoreEvent.objects.get(round=right.round, territory=target, kind=ScoreEvent.Kind.CAPTURE)
            )

    def print_scores(self):
        self.write("Scores:")
        for player in self.game.players.order_by("-score", "pk"):
            owned = Territory.objects.filter(owner=player).count()
            self.write(f"  {self.names[player.pk]}: {player.score} points, {owned} territories")
