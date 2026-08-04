"""Pure GameWatch eligibility, formatting, and announcement policy."""

from datetime import datetime, timedelta, timezone


WATCH_WINDOW = timedelta(minutes=15)
NBA_POINT_GATE = 10
NBA_TIME_GATE_SECONDS = 180


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
        summary = current.get("scoring_play") or "Scoring play recorded."
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
