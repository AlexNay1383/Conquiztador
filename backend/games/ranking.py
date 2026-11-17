"""Pure ranking rules for one question; no database access."""

from dataclasses import dataclass
from datetime import datetime
from itertools import groupby


@dataclass(frozen=True)
class NumericAnswer:
    player_id: int
    value: int
    received_at: datetime


@dataclass(frozen=True)
class FollowUp:
    """A new question is needed for `player_ids` to decide `place_count` places starting at `first_place`."""

    player_ids: tuple[int, ...]
    first_place: int
    place_count: int


@dataclass(frozen=True)
class QuestionOutcome:
    placements: tuple[tuple[int, int], ...] = ()
    follow_up: FollowUp | None = None
    follow_up_kind: str = "numeric"
    unresolved: bool = False


def rank_numeric(answers, correct_answer, group, first_place, place_count):
    """Assign `place_count` places starting at `first_place` among the accepted `answers` of `group`.

    Closer answers win; equal closeness is decided by the earlier arrival. A full tie (same closeness
    and same arrival) for a needed place asks the tied players again. Without any answer the whole
    group is asked again. Players without an answer never receive a place.
    """
    last_place = first_place + place_count - 1
    if not answers:
        return QuestionOutcome(follow_up=FollowUp(tuple(sorted(group)), first_place, place_count))

    def sort_key(answer):
        return abs(answer.value - correct_answer), answer.received_at

    placements = []
    place = first_place
    for _, tied in groupby(sorted(answers, key=lambda answer: (*sort_key(answer), answer.player_id)), key=sort_key):
        if place > last_place:
            break
        tied = list(tied)
        if len(tied) == 1:
            placements.append((place, tied[0].player_id))
            place += 1
            continue
        count = min(len(tied), last_place - place + 1)
        follow_up = FollowUp(tuple(sorted(answer.player_id for answer in tied)), place, count)
        return QuestionOutcome(placements=tuple(placements), follow_up=follow_up)

    return QuestionOutcome(placements=tuple(placements), unresolved=place <= last_place)
