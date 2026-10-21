import random

from django.db import transaction

from .models import (
    Game,
    GamePlayer,
    WaitingRoomEntry,
    WAITING,
    IN_PROGRESS,
    COLOR_RED,
    COLOR_GREEN,
    COLOR_BLUE,
)


class AlreadyWaitingError(Exception):
    pass


class NotEligibleError(Exception):
    pass


def is_user_eligible(user):
    return not GamePlayer.objects.filter(
        user=user,
        game__status__in=[WAITING, IN_PROGRESS],
    ).exists()


def join_waiting_room(user):
    if WaitingRoomEntry.objects.filter(user=user).exists():
        raise AlreadyWaitingError("User already has a waiting room entry.")

    if not is_user_eligible(user):
        raise NotEligibleError(
            "User is a participant in a waiting or active game."
        )

    entry = WaitingRoomEntry.objects.create(user=user)

    try_form_game()

    return entry


def leave_waiting_room(user):
    deleted_count, _ = WaitingRoomEntry.objects.filter(user=user).delete()
    return deleted_count > 0


def _get_eligible_waiting_user_ids():
    ineligible_user_ids = GamePlayer.objects.filter(
        game__status__in=[WAITING, IN_PROGRESS],
    ).values_list('user_id', flat=True)

    eligible_entries = WaitingRoomEntry.objects.exclude(
        user_id__in=ineligible_user_ids,
    )

    return list(eligible_entries.values_list('id', 'user_id'))


def try_form_game():
    with transaction.atomic():
        eligible = _get_eligible_waiting_user_ids()

        if len(eligible) < 3:
            return None

        chosen = random.sample(eligible, 3)
        chosen_entry_ids = [entry_id for entry_id, _ in chosen]
        chosen_user_ids = [user_id for _, user_id in chosen]

        colors = [COLOR_RED, COLOR_GREEN, COLOR_BLUE]
        random.shuffle(colors)

        game = Game.objects.create(
            created_by_id=chosen_user_ids[0],
            status=WAITING,
        )

        for i, user_id in enumerate(chosen_user_ids):
            GamePlayer.objects.create(
                game=game,
                user_id=user_id,
                color=colors[i],
                player_order=i + 1,
                score=0,
            )

        WaitingRoomEntry.objects.filter(id__in=chosen_entry_ids).delete()

        return game
