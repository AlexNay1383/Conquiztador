"""Point awards. Every change of `Player.score` goes through `award_points` and leaves a `ScoreEvent`."""

from games.models import CaptureRight, Player, Round, ScoreEvent, Territory

ROUND_WIN_POINTS = 100
TERRITORY_SCORE_INCREMENT = 100
FIRST_PLACE_PICKS = 2
SECOND_PLACE_PICKS = 1


def award_points(*, player_id, round_, kind, points, formula, territory=None, territory_score_before=None):
    player = Player.objects.select_for_update().get(pk=player_id)
    score_before = player.score
    player.score = score_before + points
    player.save(update_fields=["score"])
    return ScoreEvent.objects.create(
        game_id=player.game_id,
        player=player,
        round=round_,
        territory=territory,
        kind=kind,
        points=points,
        score_before=score_before,
        score_after=player.score,
        territory_score_before=territory_score_before,
        territory_score_after=territory.score if territory is not None else None,
        formula=formula,
    )


def raise_territory_score(territory):
    """Increase the territory's value and return the value it had before."""
    before = territory.score
    territory.score = before + TERRITORY_SCORE_INCREMENT
    return before


def award_round_win(round_, player_id):
    return award_points(
        player_id=player_id,
        round_=round_,
        kind=ScoreEvent.Kind.ROUND_WIN,
        points=ROUND_WIN_POINTS,
        formula=f"победа = {ROUND_WIN_POINTS}",
    )


def award_capture(round_, player_id, territory, territory_score_before):
    return award_points(
        player_id=player_id,
        round_=round_,
        kind=ScoreEvent.Kind.CAPTURE,
        points=territory.score,
        formula=(
            f"завземане = стойност на територията след увеличението = "
            f"{territory_score_before} + {TERRITORY_SCORE_INCREMENT} = {territory.score}"
        ),
        territory=territory,
        territory_score_before=territory_score_before,
    )


def capture_picks(free_territories, place):
    """How many picks a place earns when `free_territories` were free at round creation."""
    if place == 1:
        return min(FIRST_PLACE_PICKS, free_territories)
    if place == 2 and free_territories >= FIRST_PLACE_PICKS + SECOND_PLACE_PICKS:
        return SECOND_PLACE_PICKS
    return 0


def apply_city_capture_result(round_):
    """Win award and capture rights for a just-completed city-capture round; runs once, inside its transaction."""
    ranking = dict(round_.placements.values_list("place", "player_id"))
    if 1 not in ranking:
        return
    award_round_win(round_, ranking[1])
    for place in (1, 2):
        picks = capture_picks(round_.free_territories_at_creation, place)
        if place in ranking and picks:
            CaptureRight.objects.create(round=round_, player_id=ranking[place], order=place, allowed=picks)


def apply_round_result(round_):
    if round_.type == Round.Type.CITY_CAPTURE:
        apply_city_capture_result(round_)


def free_territories(game):
    return Territory.objects.filter(game=game, owner__isnull=True)
