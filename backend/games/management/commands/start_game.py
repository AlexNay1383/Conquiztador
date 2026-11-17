from django.core.management.base import BaseCommand, CommandError

from games.exceptions import GameError
from games.maps import get_game_territories
from games.services import initialize_game


class Command(BaseCommand):
    help = "Initialize a waiting game: create its map, place the capitals and activate it."

    def add_arguments(self, parser):
        parser.add_argument("game_id", type=int)

    def handle(self, *args, game_id, **options):
        try:
            game = initialize_game(game_id)
        except GameError as error:
            raise CommandError(f"[{error.code}] {error.message}") from error

        self.stdout.write(self.style.SUCCESS(f"Game #{game.pk} is active."))
        for territory in get_game_territories(game).filter(capital__isnull=False).select_related("owner__user"):
            self.stdout.write(f"  capital {territory.slug}: {territory.owner.user.username} ({territory.owner.color})")
