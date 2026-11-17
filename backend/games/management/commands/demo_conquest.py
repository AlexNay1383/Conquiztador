import random

from django.core.management.base import BaseCommand

from games.demo import DemoPlayer, create_demo_game
from games.models import Territory


class Command(BaseCommand):
    help = "Play city-capture rounds between three demo players until every territory is taken."

    def add_arguments(self, parser):
        parser.add_argument("--seed", type=int, default=None, help="Seed for the simulated answers and picks.")

    def handle(self, *args, seed, **options):
        game = create_demo_game()
        demo = DemoPlayer(game, random.Random(seed), self.stdout.write)
        self.stdout.write(f"Game #{game.pk}")
        for territory in Territory.objects.filter(game=game, capital__isnull=False).order_by("slug"):
            self.stdout.write(f"  capital {territory.slug}: {demo.names[territory.owner_id]}")
        demo.play_conquest()
        demo.print_scores()
