import random

from django.core.management.base import BaseCommand

from games import services
from games.exceptions import GameError
from games.models import ScoreEvent, Territory
from games.services.capture import pending_capture_rights

from .demo_round import create_demo_game


class Command(BaseCommand):
    help = "Play city-capture rounds between three demo players until every territory is taken."

    def add_arguments(self, parser):
        parser.add_argument("--seed", type=int, default=None, help="Seed for the simulated answers and picks.")

    def handle(self, *args, seed, **options):
        rng = random.Random(seed)
        game = create_demo_game()
        players = list(game.players.select_related("user").order_by("pk"))
        self.names = {player.pk: player.user.username for player in players}
        self.stdout.write(f"Game #{game.pk}")
        for territory in Territory.objects.filter(game=game, capital__isnull=False).order_by("slug"):
            self.stdout.write(f"  capital {territory.slug}: {self.names[territory.owner_id]}")

        while Territory.objects.filter(game=game, owner__isnull=True).exists():
            try:
                round_ = services.create_city_capture_round(game.pk, rng=rng)
            except GameError as error:
                self.stdout.write(f"Stopped: [{error.code}] {error.message}")
                break
            self.play_round(round_, players, rng)
            self.use_rights(game, rng)

        self.stdout.write("Final scores:")
        for player in game.players.order_by("-score", "pk"):
            owned = Territory.objects.filter(owner=player).count()
            self.stdout.write(f"  {self.names[player.pk]}: {player.score} points, {owned} territories")

    def play_round(self, round_, players, rng):
        services.start_round(round_.pk)
        free = round_.free_territories_at_creation
        self.stdout.write(f"Round {round_.number} ({free} free, {round_.places_needed} place(s) needed)")
        while (question := round_.get_current_question()) is not None:
            group = list(question.participants.order_by("pk"))
            for player in rng.sample(group, len(group)):
                services.submit_answer(round_.pk, player.pk, question.correct_answer + rng.randint(-20, 20))
        round_.refresh_from_db()
        ranking = ", ".join(f"{place}. {self.names[player.pk]}" for place, player in sorted(round_.get_ranking().items()))
        reason = f" [{round_.unresolved_reason}]" if round_.unresolved_reason else ""
        self.stdout.write(f"  questions: {round_.questions.count()}, ranking: {ranking or '-'}{reason}")
        for event in ScoreEvent.objects.filter(round=round_, kind=ScoreEvent.Kind.ROUND_WIN):
            self.print_event(event)

    def use_rights(self, game, rng):
        while (right := pending_capture_rights(game).first()) is not None:
            target = rng.choice(services.get_capture_options(game.pk, right.player_id))
            services.capture_territory(game.pk, right.player_id, target.pk)
            self.print_event(ScoreEvent.objects.get(round=right.round, territory=target, kind=ScoreEvent.Kind.CAPTURE))

    def print_event(self, event):
        target = f" {event.territory.slug}" if event.territory else ""
        self.stdout.write(
            f"  {self.names[event.player_id]} {event.get_kind_display().lower()}{target}: "
            f"{event.score_before} -> {event.score_after} ({event.formula})"
        )
