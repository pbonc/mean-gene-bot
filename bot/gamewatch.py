"""Pure GameWatch eligibility, formatting, and announcement policy."""

from datetime import datetime, timedelta, timezone


WATCH_WINDOW = timedelta(minutes=15)
NBA_POINT_GATE = 10
NBA_TIME_GATE_SECONDS = 180
NFL_BIG_PLAY_YARDS = 20


def is_watchable(game, now=None):
    now = now or datetime.now(timezone.utc)
    start = game["start_time"]
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return not game.get("completed") and (
        game.get("state") == "in" or now >= start - WATCH_WINDOW
    )


def score_leader(game):
    home = int(game.get("home_score", 0))
    away = int(game.get("away_score", 0))
    if home == away:
        return "tie"
    return "home" if home > away else "away"


def should_announce(previous, current, seconds_since_announcement):
    if previous is None:
        return True
    score_changed = (
        previous.get("home_score") != current.get("home_score")
        or previous.get("away_score") != current.get("away_score")
    )
    if current.get("completed") and not previous.get("completed"):
        return True
    if current.get("sport") == "MLB":
        return score_changed
    if current.get("period") != previous.get("period"):
        return True
    if current.get("sport") != "NBA":
        return score_changed
    if not score_changed:
        return False
    points = abs(
        (current.get("home_score", 0) + current.get("away_score", 0))
        - (previous.get("home_score", 0) + previous.get("away_score", 0))
    )
    return (
        points >= NBA_POINT_GATE
        or score_leader(previous) != score_leader(current)
        or seconds_since_announcement >= NBA_TIME_GATE_SECONDS
    )


def mlb_updates(previous, current):
    """Return meaningful MLB messages; pitch-by-pitch and inning noise is excluded."""
    if previous is None:
        return []
    updates = []
    score_changed = (
        previous.get("home_score") != current.get("home_score")
        or previous.get("away_score") != current.get("away_score")
    )
    if score_changed:
        summary = _mlb_scoring_summary(previous, current)
        updates.append(format_update(current, summary=summary))

    previous_pitchers = previous.get("current_pitchers") or {}
    for team_id, pitcher in (current.get("current_pitchers") or {}).items():
        old = previous_pitchers.get(team_id)
        if old and old.get("id") != pitcher.get("id"):
            updates.append(
                f"GameWatch MLB pitching change: {pitcher['name']} replaces "
                f"{old['name']} for the {pitcher['team']}."
            )

    previous_milestones = {
        item.get("key") for item in (previous.get("milestones") or [])
    }
    for milestone in current.get("milestones") or []:
        if milestone.get("key") not in previous_milestones:
            updates.append(
                f"GameWatch MLB {milestone['kind']} watch: {milestone['pitcher']} "
                f"of the {milestone['team']} remains in after "
                f"{milestone['innings']:g} hitless innings."
            )

    if current.get("completed") and not previous.get("completed") and not score_changed:
        updates.append(format_update(current))
    return updates


def football_updates(previous, current):
    """Return score, game-boundary, turnover, and big-play NFL updates."""
    if previous is None:
        return []

    updates = []
    score_changed = (
        previous.get("home_score") != current.get("home_score")
        or previous.get("away_score") != current.get("away_score")
    )
    period_changed = current.get("period") != previous.get("period")
    play_changed = (
        current.get("last_play_id")
        and current.get("last_play_id") != previous.get("last_play_id")
    )
    play_text = str(current.get("last_play_text") or "").strip().rstrip(".")

    if score_changed:
        updates.append(format_update(current, summary=play_text or "Score change recorded"))

    if current.get("completed") and not previous.get("completed"):
        if not score_changed:
            updates.append(format_update(current))
        return updates

    if period_changed:
        old_period = int(previous.get("period") or 0)
        if old_period == 2:
            boundary = "Halftime"
        elif old_period > 0:
            boundary = f"End of the {_ordinal(old_period)} quarter"
        else:
            boundary = "Period change"
        updates.append(format_update(current, summary=boundary))

    if play_changed and not score_changed:
        if current.get("last_play_turnover"):
            updates.append(format_update(current, summary=f"Turnover: {play_text}"))
        elif int(current.get("last_play_yards") or 0) >= NFL_BIG_PLAY_YARDS:
            updates.append(format_update(current, summary=f"Big play: {play_text}"))
    return updates


def _ordinal(number):
    if 10 <= number % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def _mlb_scoring_summary(previous, current):
    """Correlate an ESPN scoring play to the team and scoreboard change."""
    home_delta = int(current.get("home_score", 0)) - int(previous.get("home_score", 0))
    away_delta = int(current.get("away_score", 0)) - int(previous.get("away_score", 0))
    changed_team_id = None
    changed_team_name = None
    changed_runs = 0
    if home_delta > 0 and away_delta <= 0:
        changed_team_id = str(current.get("home_team_id") or "")
        changed_team_name = current.get("home") or "Home team"
        changed_runs = home_delta
    elif away_delta > 0 and home_delta <= 0:
        changed_team_id = str(current.get("away_team_id") or "")
        changed_team_name = current.get("away") or "Away team"
        changed_runs = away_delta

    plays = current.get("scoring_plays") or []
    exact_score = [
        play for play in plays
        if int(play.get("home_score", -1)) == int(current.get("home_score", 0))
        and int(play.get("away_score", -1)) == int(current.get("away_score", 0))
        and (not changed_team_id or str(play.get("team_id") or "") == changed_team_id)
    ]
    if exact_score:
        return exact_score[-1].get("text") or "Scoring play recorded"
    team_and_runs = [
        play for play in plays
        if changed_team_id
        and str(play.get("team_id") or "") == changed_team_id
        and int(play.get("runs") or 0) == changed_runs
    ]
    if team_and_runs:
        return team_and_runs[-1].get("text") or "Scoring play recorded"
    if changed_team_name and changed_runs:
        return f"{changed_team_name} scored {changed_runs} run{'s' if changed_runs != 1 else ''}"
    return "Score change recorded"


def format_listing(game, number, now=None):
    now = now or datetime.now(timezone.utc)
    if game.get("state") == "in":
        timing = game.get("detail") or "Live"
    else:
        timing = game["start_time"].astimezone().strftime("%I:%M %p").lstrip("0")
    return f"{number}) {game['sport']} {game['away']} at {game['home']} ({timing})"


def format_update(game, summary=None):
    summary = str(summary).strip().rstrip(".") if summary else None
    if game.get("completed"):
        final = f"{summary} Final" if summary else "Final"
    else:
        final = summary or game.get("detail") or "Live"
    return (
        f"GameWatch {game['sport']}: {game['away']} {game['away_score']}, "
        f"{game['home']} {game['home_score']}. {final}."
    )
