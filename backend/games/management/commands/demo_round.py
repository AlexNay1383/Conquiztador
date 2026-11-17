from django.core.management.base import BaseCommand
from django.utils import timezone

from games import services
from games.demo import create_demo_game


class Command(BaseCommand):
    help = "Play one city-capture round between three demo players and print the stored result."

    def add_arguments(self, parser):
        parser.add_argument(
            "--offsets",
            type=int,
            nargs=3,
            default=[3, -3, 40],
            metavar=("RED", "GREEN", "BLUE"),
            help="How far each player's answer is from the correct one (answers are sent in this order).",
        )

    def handle(self, *args, offsets, **options):
        game = create_demo_game()
        players = list(game.players.select_related("user").order_by("pk"))
        names = {player.pk: player.user.username for player in players}

        round_ = services.create_city_capture_round(game.pk)
        services.start_round(round_.pk)
        question = round_.get_current_question()
        self.stdout.write(f"Game #{game.pk}, round {round_.number}: {question.text}")
        self.stdout.write(f"  correct answer: {question.correct_answer}")

        for player, offset in zip(players, offsets):
            answer = services.submit_answer(round_.pk, player.pk, question.correct_answer + offset)
            received = timezone.localtime(answer.received_at)
            self.stdout.write(f"  {names[player.pk]} answered {answer.numeric_value} at {received:%H:%M:%S.%f}")

        state = services.get_round_state(round_.pk)
        self.stdout.write(f"Round status: {state['status']}, questions asked: {len(state['questions'])}")
        if state["current_question"]:
            current = state["current_question"]
            self.stdout.write(
                f"  follow-up question for {[names[pk] for pk in current['participant_ids']]}, "
                f"deadline {timezone.localtime(current['deadline']):%H:%M:%S}"
            )
        for place, player_id in sorted(state["ranking"].items()):
            self.stdout.write(f"  place {place}: {names[player_id]}")
        if state["unresolved_reason"]:
            self.stdout.write(f"  incomplete ranking: {state['unresolved_reason']}")
