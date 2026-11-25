import time

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from django.utils import timezone

from games import clock, services
from games.exceptions import GameError


class Command(BaseCommand):
    help = "Close every active question whose deadline has passed, once or repeatedly with --loop."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Keep checking until stopped with Ctrl+C.")
        parser.add_argument("--interval", type=float, default=5.0, help="Seconds between checks with --loop.")

    def handle(self, *args, loop, interval, **options):
        if interval <= 0:
            raise CommandError("--interval must be positive.")
        if not loop:
            self.check_once()
            return
        self.stdout.write(f"Checking every {interval:g} s, press Ctrl+C to stop.")
        try:
            while True:
                self.check_once()
                time.sleep(interval)
                # A long-running process must not keep a connection the database has already dropped.
                close_old_connections()
        except KeyboardInterrupt:
            self.stdout.write("Stopped.")

    def check_once(self):
        now = clock.now()
        question_ids = list(services.expired_questions(now).values_list("pk", flat=True))
        processed = skipped = 0
        for question_id in question_ids:
            try:
                closed = services.close_expired_question(question_id)
            except GameError as error:
                skipped += 1
                self.stderr.write(f"  question #{question_id} refused: {error.code}")
                continue
            except Exception as error:  # noqa: BLE001 - one broken question must not stop the others
                skipped += 1
                self.stderr.write(f"  question #{question_id} failed: {error!r}")
                continue
            if closed:
                processed += 1
            else:
                skipped += 1
        self.stdout.write(f"[{timezone.localtime(now):%H:%M:%S}] processed: {processed}, skipped: {skipped}")
