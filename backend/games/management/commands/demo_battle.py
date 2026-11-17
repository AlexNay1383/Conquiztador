import random

from django.core.management.base import BaseCommand, CommandError

from games import services
from games.demo import DemoPlayer, create_demo_game
from games.models import Capital, ScoreEvent, Territory


class Command(BaseCommand):
    help = (
        "Conquer the map with three demo players, then play one battle in which both players answer the "
        "choice question correctly, so a numeric question decides the winner."
    )

    def add_arguments(self, parser):
        parser.add_argument("--seed", type=int, default=None, help="Seed for the simulated conquest phase.")

    def handle(self, *args, seed, **options):
        rng = random.Random(seed)
        game = create_demo_game()
        demo = DemoPlayer(game, rng, write=lambda line: None)
        if not demo.play_conquest():
            raise CommandError("The conquest phase could not finish; load more numeric questions.")
        demo.write = self.stdout.write
        names = demo.names
        self.stdout.write(f"Game #{game.pk}: the map is fully owned.")

        attacker, target = self.choose_battle(game)
        round_ = services.create_battle(game.pk, attacker.pk, target.pk, rng=rng)
        self.stdout.write(
            f"Round {round_.number} ({round_.type}): {names[attacker.pk]} attacks {target.slug} "
            f"(value {target.score}) owned by {names[round_.defender_id]}"
        )
        services.start_round(round_.pk)

        choice = round_.get_current_question()
        correct_option = choice.options.get(is_correct=True)
        self.stdout.write(f"  Q1 choice: {choice.text} -> correct: {correct_option.text}")
        for player_id in (round_.defender_id, attacker.pk):
            services.submit_answer(round_.pk, player_id, correct_option.source_option_id)
            self.stdout.write(f"    {names[player_id]} chose {correct_option.text}")

        numeric = round_.get_current_question()
        self.stdout.write(f"  Q2 {numeric.kind}: {numeric.text} -> correct: {numeric.correct_answer}")
        for player_id, offset in ((attacker.pk, 2), (round_.defender_id, -7)):
            services.submit_answer(round_.pk, player_id, numeric.correct_answer + offset)
            self.stdout.write(f"    {names[player_id]} answered {numeric.correct_answer + offset}")

        round_.refresh_from_db()
        target.refresh_from_db()
        self.stdout.write(
            f"  winner: {names[round_.winner_id]}; {target.slug} now belongs to "
            f"{names[target.owner_id]}, value {target.score}"
        )
        for event in ScoreEvent.objects.filter(round=round_):
            demo.describe_event(event)
        self.stdout.write("  stored history:")
        for item in services.get_round_state(round_.pk)["questions"]:
            self.stdout.write(f"    #{item['sequence']} {item['kind']}: answers {[a['value'] for a in item['answers']]}")

    def choose_battle(self, game):
        capitals = set(Capital.objects.filter(territory__game=game).values_list("territory_id", flat=True))
        for target in Territory.objects.filter(game=game).exclude(pk__in=capitals).order_by("slug"):
            attacker_territory = target.neighbors.exclude(owner=target.owner_id).select_related("owner").first()
            if attacker_territory is not None:
                return attacker_territory.owner, target
        raise CommandError("No ordinary territory borders another player.")
