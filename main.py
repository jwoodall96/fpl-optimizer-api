from fastapi import FastAPI, HTTPException
import requests
import math

app = FastAPI(
    title="FPL Optimizer API",
    description="Lightweight API providing live FPL data to a custom GPT.",
    version="1.0.0",
)

FPL_BASE = "https://fantasy.premierleague.com/api"


def get_bootstrap():
    response = requests.get(f"{FPL_BASE}/bootstrap-static/", timeout=20)
    response.raise_for_status()
    return response.json()


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "FPL Optimizer API is running"
    }


@app.get("/gameweek")
def gameweek():
    data = get_bootstrap()

    events = data["events"]

    current = next(
        (gw for gw in events if gw.get("is_current")),
        None
    )

    next_gw = next(
        (gw for gw in events if gw.get("is_next")),
        None
    )

    return {
        "current": current,
        "next": next_gw
    }


@app.get("/teams")
def teams():
    data = get_bootstrap()

    return [
        {
            "id": team["id"],
            "name": team["name"],
            "short_name": team["short_name"],
            "strength": team.get("strength"),
            "strength_attack_home": team.get("strength_attack_home"),
            "strength_attack_away": team.get("strength_attack_away"),
            "strength_defence_home": team.get("strength_defence_home"),
            "strength_defence_away": team.get("strength_defence_away"),
        }
        for team in data["teams"]
    ]


@app.get("/players")
def players(
    team: int | None = None,
    position: int | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    available_only: bool = True,
    sort_by: str = "total_points",
    order: str = "desc",
    limit: int = 50,
):
    data = get_bootstrap()

    # Prevent oversized responses
    limit = max(1, min(limit, 100))

    team_lookup = {
        t["id"]: t["name"]
        for t in data["teams"]
    }

    position_lookup = {
        p["id"]: p["singular_name_short"]
        for p in data["element_types"]
    }

    result = []

    for p in data["elements"]:
        price = p["now_cost"] / 10

        if team is not None and p["team"] != team:
            continue

        if position is not None and p["element_type"] != position:
            continue

        if min_price is not None and price < min_price:
            continue

        if max_price is not None and price > max_price:
            continue

        if available_only and p.get("status") not in ("a", None):
            continue

        result.append({
            "id": p["id"],
            "name": p["web_name"],
            "team_id": p["team"],
            "team": team_lookup.get(p["team"]),
            "position_id": p["element_type"],
            "position": position_lookup.get(p["element_type"]),
            "price": price,
            "total_points": p.get("total_points", 0),
            "form": p.get("form", "0"),
            "points_per_game": p.get("points_per_game", "0"),
            "selected_by_percent": p.get("selected_by_percent", "0"),
            "minutes": p.get("minutes", 0),
            "goals": p.get("goals_scored", 0),
            "assists": p.get("assists", 0),
            "expected_goals": p.get("expected_goals", "0"),
            "expected_assists": p.get("expected_assists", "0"),
            "expected_goal_involvements": p.get("expected_goal_involvements", "0"),
            "expected_goals_conceded": p.get("expected_goals_conceded", "0"),
            "clean_sheets": p.get("clean_sheets", 0),
            "saves": p.get("saves", 0),
            "bonus": p.get("bonus", 0),
            "bps": p.get("bps", 0),
            "influence": p.get("influence", "0"),
            "creativity": p.get("creativity", "0"),
            "threat": p.get("threat", "0"),
            "ict_index": p.get("ict_index", "0"),
            "status": p.get("status"),
            "chance_next":
                p.get("chance_of_playing_next_round"),
            "news": p.get("news", ""),
        })

    allowed_sort_fields = {
        "price",
        "total_points",
        "minutes",
        "goals",
        "assists",
        "clean_sheets",
        "saves",
        "bonus",
        "bps",
        "form",
        "points_per_game",
        "selected_by_percent",
        "influence",
        "creativity",
        "threat",
        "ict_index",
    }

    if sort_by not in allowed_sort_fields:
        sort_by = "total_points"

    def sort_value(player):
        value = player.get(sort_by, 0)

        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0

    reverse = order.lower() != "asc"

    result.sort(key=sort_value, reverse=reverse)

    result = result[:limit]

    return {
        "count": len(result),
        "filters": {
            "team": team,
            "position": position,
            "min_price": min_price,
            "max_price": max_price,
            "available_only": available_only,
            "sort_by": sort_by,
            "order": order,
            "limit": limit,
        },
        "players": result,
    }

@app.get("/players/{player_id}")
def player(player_id: int):
    data = get_bootstrap()

    p = next(
        (x for x in data["elements"] if x["id"] == player_id),
        None
    )

    if p is None:
        raise HTTPException(status_code=404, detail="Player not found")

    summary_response = requests.get(
        f"{FPL_BASE}/element-summary/{player_id}/",
        timeout=20
    )
    summary_response.raise_for_status()

    return {
        "player": p,
        "summary": summary_response.json()
    }


@app.get("/fixtures")
def fixtures(gameweek: int | None = None):
    url = f"{FPL_BASE}/fixtures/"

    if gameweek is not None:
        url += f"?event={gameweek}"

    response = requests.get(url, timeout=20)
    response.raise_for_status()

    fixtures_data = response.json()

    return {
        "count": len(fixtures_data),
        "fixtures": fixtures_data
    }

HISTORICAL_BASE = (
    "https://raw.githubusercontent.com/"
    "vaastav/Fantasy-Premier-League/master/data"
)


@app.get("/history/{season}")
def historical_players(
    season: str,
    player: str | None = None,
    position: int | None = None,
    min_minutes: int = 0,
    sort_by: str = "total_points",
    order: str = "desc",
    limit: int = 50,
):
    """
    Search archived FPL player data for a previous season.
    Example season: 2025-26
    """
    limit = max(1, min(limit, 100))

    url = f"{HISTORICAL_BASE}/{season}/players_raw.csv"

    response = requests.get(url, timeout=30)

    if response.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail=f"Historical data not found for season {season}",
        )

    response.raise_for_status()

    import csv
    import io

    rows = list(
        csv.DictReader(
            io.StringIO(
                response.content.decode("utf-8")
            )
        )
    )

    result = []

    for p in rows:

        # Optional player-name search
        if player:
            search_name = player.lower()

            full_name = (
                f"{p.get('first_name', '')} "
                f"{p.get('second_name', '')}"
            ).lower()

            web_name = p.get("web_name", "").lower()

            if (
                search_name not in full_name
                and search_name not in web_name
            ):
                continue

        # Optional position filter
        if position is not None:
            try:
                player_position = int(
                    p.get("element_type", 0) or 0
                )
            except (TypeError, ValueError):
                player_position = 0

            if player_position != position:
                continue

        # Optional minimum-minutes filter
        try:
            minutes = int(
                float(p.get("minutes", 0) or 0)
            )
        except (TypeError, ValueError):
            minutes = 0

        if minutes < min_minutes:
            continue

        result.append({
            "id": p.get("id"),
            "first_name": p.get("first_name"),
            "second_name": p.get("second_name"),
            "web_name": p.get("web_name"),
            "team": p.get("team"),
            "element_type": p.get("element_type"),
            "minutes": p.get("minutes"),
            "total_points": p.get("total_points"),
            "goals_scored": p.get("goals_scored"),
            "assists": p.get("assists"),
            "expected_goals": p.get("expected_goals"),
            "expected_assists": p.get("expected_assists"),
            "expected_goal_involvements":
                p.get("expected_goal_involvements"),
            "expected_goals_conceded":
                p.get("expected_goals_conceded"),
            "clean_sheets": p.get("clean_sheets"),
            "saves": p.get("saves"),
            "bonus": p.get("bonus"),
            "bps": p.get("bps"),
        })

    allowed_sort_fields = {
        "minutes",
        "total_points",
        "goals_scored",
        "assists",
        "expected_goals",
        "expected_assists",
        "expected_goal_involvements",
        "expected_goals_conceded",
        "clean_sheets",
        "saves",
        "bonus",
        "bps",
    }

    if sort_by not in allowed_sort_fields:
        sort_by = "total_points"

    def historical_sort_value(p):
        try:
            return float(p.get(sort_by, 0) or 0)
        except (TypeError, ValueError):
            return 0

    reverse = order.lower() != "asc"

    result.sort(
        key=historical_sort_value,
        reverse=reverse,
    )

    result = result[:limit]

    return {
        "season": season,
        "count": len(result),
        "filters": {
            "player": player,
            "position": position,
            "min_minutes": min_minutes,
            "sort_by": sort_by,
            "order": order,
            "limit": limit,
        },
        "players": result,
    }

@app.get("/player-pool")
def player_pool(
    position: int | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    min_history_minutes: int = 0,
    sort_by: str = "xgi_per90",
    order: str = "desc",
    limit: int = 50,
):
    """
    Join current FPL players to 2025-26 historical performance.
    """
    limit = max(1, min(limit, 100))

    # Current FPL data
    current = get_bootstrap()

    team_lookup = {
        t["id"]: t["name"]
        for t in current["teams"]
    }

    position_lookup = {
        p["id"]: p["singular_name_short"]
        for p in current["element_types"]
    }

    # Historical 2025-26 data
    history_url = (
        f"{HISTORICAL_BASE}/2025-26/players_raw.csv"
    )

    response = requests.get(history_url, timeout=30)
    response.raise_for_status()

    import csv
    import io

    historical_rows = list(
        csv.DictReader(
            io.StringIO(
                response.content.decode("utf-8")
            )
        )
    )

    # Match primarily using web_name
    history_lookup = {}

    for h in historical_rows:
        key = h.get("web_name", "").strip().lower()

        if key:
            history_lookup[key] = h

    result = []

    for p in current["elements"]:

        price = p["now_cost"] / 10

        if position is not None:
            if p["element_type"] != position:
                continue

        if min_price is not None and price < min_price:
            continue

        if max_price is not None and price > max_price:
            continue

        name = p["web_name"]
        historical = history_lookup.get(
            name.strip().lower()
        )

        history_minutes = 0
        history_xg = 0.0
        history_xa = 0.0
        history_xgi = 0.0
        history_points = 0

        if historical:
            try:
                history_minutes = int(
                    float(
                        historical.get("minutes", 0)
                        or 0
                    )
                )
            except (TypeError, ValueError):
                history_minutes = 0

            try:
                history_xg = float(
                    historical.get(
                        "expected_goals", 0
                    ) or 0
                )
            except (TypeError, ValueError):
                history_xg = 0.0

            try:
                history_xa = float(
                    historical.get(
                        "expected_assists", 0
                    ) or 0
                )
            except (TypeError, ValueError):
                history_xa = 0.0

            history_xgi = history_xg + history_xa

            try:
                history_points = int(
                    float(
                        historical.get(
                            "total_points", 0
                        ) or 0
                    )
                )
            except (TypeError, ValueError):
                history_points = 0

        if history_minutes < min_history_minutes:
            continue

        if history_minutes > 0:
            xg_per90 = (
                history_xg / history_minutes * 90
            )
            xa_per90 = (
                history_xa / history_minutes * 90
            )
            xgi_per90 = (
                history_xgi / history_minutes * 90
            )
            points_per90 = (
                history_points / history_minutes * 90
            )
        else:
            xg_per90 = 0.0
            xa_per90 = 0.0
            xgi_per90 = 0.0
            points_per90 = 0.0

        result.append({
            "id": p["id"],
            "name": name,
            "team": team_lookup.get(p["team"]),
            "team_id": p["team"],
            "position":
                position_lookup.get(
                    p["element_type"]
                ),
            "position_id": p["element_type"],
            "price": price,
            "status": p.get("status"),
            "history_found":
                historical is not None,
            "history_minutes": history_minutes,
            "history_points": history_points,
            "history_xg":
                round(history_xg, 2),
            "history_xa":
                round(history_xa, 2),
            "history_xgi":
                round(history_xgi, 2),
            "xg_per90":
                round(xg_per90, 3),
            "xa_per90":
                round(xa_per90, 3),
            "xgi_per90":
                round(xgi_per90, 3),
            "points_per90":
                round(points_per90, 3),
        })

    allowed_sort_fields = {
        "price",
        "history_minutes",
        "history_points",
        "history_xg",
        "history_xa",
        "history_xgi",
        "xg_per90",
        "xa_per90",
        "xgi_per90",
        "points_per90",
    }

    if sort_by not in allowed_sort_fields:
        sort_by = "xgi_per90"

    reverse = order.lower() != "asc"

    result.sort(
        key=lambda x: x.get(sort_by, 0),
        reverse=reverse,
    )

    result = result[:limit]

    return {
        "count": len(result),
        "filters": {
            "position": position,
            "min_price": min_price,
            "max_price": max_price,
            "min_history_minutes":
                min_history_minutes,
            "sort_by": sort_by,
            "order": order,
            "limit": limit,
        },
        "players": result,
    }
# ============================================================
# PROJECTION ENGINE V1
# ============================================================

MODEL_VERSION = "1.0-unadjusted"


def safe_float(value, default=0.0):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return default


def safe_int(value, default=0):
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return default


def get_historical_lookup(season="2025-26"):
    """
    Load archived FPL player data and index by web_name.
    """
    history_url = (
        f"{HISTORICAL_BASE}/{season}/players_raw.csv"
    )

    response = requests.get(history_url, timeout=30)
    response.raise_for_status()

    import csv
    import io

    rows = list(
        csv.DictReader(
            io.StringIO(
                response.content.decode("utf-8")
            )
        )
    )

    lookup = {}

    for row in rows:
        key = row.get("web_name", "").strip().lower()

        if key:
            lookup[key] = row

    return lookup


def get_player_fixtures(team_id, start_gw=1, horizon=6):
    """
    Return fixtures for one team over the requested GW horizon.
    """
    response = requests.get(
        f"{FPL_BASE}/fixtures/",
        timeout=20,
    )
    response.raise_for_status()

    all_fixtures = response.json()

    end_gw = start_gw + horizon - 1

    result = []

    for fixture in all_fixtures:
        event = fixture.get("event")

        if event is None:
            continue

        if event < start_gw or event > end_gw:
            continue

        is_home = fixture.get("team_h") == team_id
        is_away = fixture.get("team_a") == team_id

        if not is_home and not is_away:
            continue

        if is_home:
            opponent_id = fixture.get("team_a")
            difficulty = fixture.get(
                "team_h_difficulty"
            )
        else:
            opponent_id = fixture.get("team_h")
            difficulty = fixture.get(
                "team_a_difficulty"
            )

        result.append({
            "gameweek": event,
            "fixture_id": fixture.get("id"),
            "home": is_home,
            "opponent_id": opponent_id,
            "difficulty": difficulty,
        })

    result.sort(
        key=lambda x: (
            x["gameweek"],
            x["fixture_id"] or 0,
        )
    )

    return result


def appearance_expected_points(expected_minutes):
    """
    Simple V1 appearance model.

    This is intentionally transparent rather than pretending
    expected minutes alone gives us an exact appearance probability.

    >= 60 expected minutes -> 2 appearance points
    1-59 expected minutes -> scaled between 0 and 1 point
    0 expected minutes -> 0 points
    """
    if expected_minutes <= 0:
        return 0.0

    if expected_minutes >= 60:
        return 2.0

    return expected_minutes / 60


def goal_points_for_position(position_id):
    """
    FPL points awarded per goal by position.
    """
    scoring = {
        1: 6,  # GK
        2: 6,  # DEF
        3: 5,  # MID
        4: 4,  # FWD
    }

    return scoring.get(position_id, 0)


def calculate_unadjusted_projection(
    position_id,
    xg_per90,
    xa_per90,
    expected_minutes,
):
    """
    Projection Engine V1.

    Includes:
    - appearance points
    - expected goal points
    - expected assist points

    Does NOT yet include:
    - fixture adjustment
    - clean-sheet points
    - goalkeeper saves
    - defensive contributions
    - bonus
    - cards
    - own goals
    - penalty misses

    Those will be added in later model versions.
    """
    expected_minutes = max(
        0.0,
        min(float(expected_minutes), 90.0)
    )

    minutes_factor = expected_minutes / 90

    expected_goals = xg_per90 * minutes_factor
    expected_assists = xa_per90 * minutes_factor

    appearance_xpts = appearance_expected_points(
        expected_minutes
    )

    goal_xpts = (
        expected_goals
        * goal_points_for_position(position_id)
    )

    assist_xpts = expected_assists * 3

    attacking_xpts = goal_xpts + assist_xpts

    total_xpts = appearance_xpts + attacking_xpts

    return {
        "expected_minutes":
            round(expected_minutes, 1),
        "expected_goals":
            round(expected_goals, 3),
        "expected_assists":
            round(expected_assists, 3),
        "appearance_xpts":
            round(appearance_xpts, 3),
        "goal_xpts":
            round(goal_xpts, 3),
        "assist_xpts":
            round(assist_xpts, 3),
        "attacking_xpts":
            round(attacking_xpts, 3),
        "total_xpts":
            round(total_xpts, 3),
    }


@app.get("/projection/{player_id}")
def player_projection(
    player_id: int,
    expected_minutes: float = 75,
    start_gw: int = 1,
    horizon: int = 6,
):
    """
    Produce a transparent V1 GW projection for one player.

    expected_minutes is currently applied to every fixture in
    the horizon. The GPT can override it based on current
    expected-minutes research.
    """
    horizon = max(1, min(horizon, 10))

    current = get_bootstrap()

    player = next(
        (
            p for p in current["elements"]
            if p["id"] == player_id
        ),
        None,
    )

    if player is None:
        raise HTTPException(
            status_code=404,
            detail="Current FPL player not found",
        )

    team_lookup = {
        t["id"]: t["name"]
        for t in current["teams"]
    }

    history_lookup = get_historical_lookup_by_code()

    historical = history_lookup.get(
        safe_int(player.get("code"), -1)
    )

    if historical is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "No 2025-26 historical match found "
                "for this player"
            ),
        )

    history_minutes = safe_int(
        historical.get("minutes")
    )

    if history_minutes <= 0:
        raise HTTPException(
            status_code=400,
            detail=(
                "Historical player has no usable "
                "minutes for projection"
            ),
        )

    history_xg = safe_float(
        historical.get("expected_goals")
    )

    history_xa = safe_float(
        historical.get("expected_assists")
    )

    xg_per90 = (
        history_xg / history_minutes * 90
    )

    xa_per90 = (
        history_xa / history_minutes * 90
    )

    fixtures = get_player_fixtures(
        player["team"],
        start_gw=start_gw,
        horizon=horizon,
    )

    fixture_projections = []

    for fixture in fixtures:

        projection = calculate_unadjusted_projection(
            position_id=player["element_type"],
            xg_per90=xg_per90,
            xa_per90=xa_per90,
            expected_minutes=expected_minutes,
        )

        fixture_projections.append({
            **fixture,
            **projection,
        })

    total_xpts = sum(
        x["total_xpts"]
        for x in fixture_projections
    )

    total_expected_goals = sum(
        x["expected_goals"]
        for x in fixture_projections
    )

    total_expected_assists = sum(
        x["expected_assists"]
        for x in fixture_projections
    )

    return {
        "model_version": MODEL_VERSION,
        "model_type":
            "unadjusted attacking projection",
        "warning": (
            "V1 is not a complete FPL xPts model. "
            "It currently includes appearance, goals "
            "and assists only. Fixture strength, clean "
            "sheets, saves, defensive contributions "
            "and bonus are not yet included."
        ),
        "player": {
            "id": player["id"],
            "name": player["web_name"],
            "team": team_lookup.get(
                player["team"]
            ),
            "team_id": player["team"],
            "position_id":
                player["element_type"],
            "price":
                player["now_cost"] / 10,
            "status": player.get("status"),
        },
        "historical_basis": {
            "season": "2025-26",
            "minutes": history_minutes,
            "expected_goals":
                round(history_xg, 3),
            "expected_assists":
                round(history_xa, 3),
            "xg_per90":
                round(xg_per90, 3),
            "xa_per90":
                round(xa_per90, 3),
            "xgi_per90":
                round(
                    xg_per90 + xa_per90,
                    3,
                ),
        },
        "assumptions": {
            "expected_minutes_per_fixture":
                expected_minutes,
            "start_gw": start_gw,
            "horizon": horizon,
            "fixture_adjustment": False,
        },
        "fixtures": fixture_projections,
        "totals": {
            "fixtures":
                len(fixture_projections),
            "expected_goals":
                round(
                    total_expected_goals,
                    3,
                ),
            "expected_assists":
                round(
                    total_expected_assists,
                    3,
                ),
            "total_xpts":
                round(total_xpts, 3),
        },
    }
@app.get("/historical-team-strength")
def historical_team_strength(
    season: str = "2025-26",
):
    """
    Calculate historical team attacking and defensive strength
    from archived FPL fixture results.

    Strength of 1.0 = league average.
    >1 attacking strength = stronger attack.
    >1 defensive weakness = easier opponent to score against.
    """

    url = f"{HISTORICAL_BASE}/{season}/fixtures.csv"

    response = requests.get(url, timeout=30)

    if response.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail=f"Fixture history not found for {season}",
        )

    response.raise_for_status()

    import csv
    import io

    rows = list(
        csv.DictReader(
            io.StringIO(
                response.content.decode("utf-8")
            )
        )
    )

    teams = {}

    def ensure_team(team_id):
        if team_id not in teams:
            teams[team_id] = {
                "home_games": 0,
                "away_games": 0,
                "home_goals_for": 0,
                "home_goals_against": 0,
                "away_goals_for": 0,
                "away_goals_against": 0,
            }

    for row in rows:
        try:
            home = int(row["team_h"])
            away = int(row["team_a"])
            home_goals = int(row["team_h_score"])
            away_goals = int(row["team_a_score"])
        except (KeyError, TypeError, ValueError):
            continue

        ensure_team(home)
        ensure_team(away)

        teams[home]["home_games"] += 1
        teams[home]["home_goals_for"] += home_goals
        teams[home]["home_goals_against"] += away_goals

        teams[away]["away_games"] += 1
        teams[away]["away_goals_for"] += away_goals
        teams[away]["away_goals_against"] += home_goals

    total_home_goals = sum(
        t["home_goals_for"] for t in teams.values()
    )
    total_away_goals = sum(
        t["away_goals_for"] for t in teams.values()
    )

    total_home_games = sum(
        t["home_games"] for t in teams.values()
    )
    total_away_games = sum(
        t["away_games"] for t in teams.values()
    )

    league_home_goals_per_game = (
        total_home_goals / total_home_games
        if total_home_games else 0
    )

    league_away_goals_per_game = (
        total_away_goals / total_away_games
        if total_away_games else 0
    )

    result = []

    for team_id, t in teams.items():

        home_gf_pg = (
            t["home_goals_for"] / t["home_games"]
            if t["home_games"] else 0
        )

        home_ga_pg = (
            t["home_goals_against"] / t["home_games"]
            if t["home_games"] else 0
        )

        away_gf_pg = (
            t["away_goals_for"] / t["away_games"]
            if t["away_games"] else 0
        )

        away_ga_pg = (
            t["away_goals_against"] / t["away_games"]
            if t["away_games"] else 0
        )

        result.append({
            "historical_team_id": team_id,

            "home_games": t["home_games"],
            "away_games": t["away_games"],

            "home_goals_for_per_game":
                round(home_gf_pg, 3),

            "away_goals_for_per_game":
                round(away_gf_pg, 3),

            "home_goals_against_per_game":
                round(home_ga_pg, 3),

            "away_goals_against_per_game":
                round(away_ga_pg, 3),

            "home_attack_strength": round(
                home_gf_pg /
                league_home_goals_per_game,
                3,
            ) if league_home_goals_per_game else 0,

            "away_attack_strength": round(
                away_gf_pg /
                league_away_goals_per_game,
                3,
            ) if league_away_goals_per_game else 0,

            "home_defence_weakness": round(
                home_ga_pg /
                league_away_goals_per_game,
                3,
            ) if league_away_goals_per_game else 0,

            "away_defence_weakness": round(
                away_ga_pg /
                league_home_goals_per_game,
                3,
            ) if league_home_goals_per_game else 0,
        })

    return {
        "season": season,
        "league": {
            "home_goals_per_team_game":
                round(league_home_goals_per_game, 3),
            "away_goals_per_team_game":
                round(league_away_goals_per_game, 3),
        },
        "teams": result,
    }
def get_historical_team_mapping(season="2025-26"):
    """
    Map historical FPL team IDs to team names.
    """
    url = f"{HISTORICAL_BASE}/{season}/teams.csv"

    response = requests.get(url, timeout=30)

    if response.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail=f"Historical teams not found for {season}",
        )

    response.raise_for_status()

    import csv
    import io

    rows = list(
        csv.DictReader(
            io.StringIO(
                response.content.decode("utf-8")
            )
        )
    )

    mapping = {}

    for row in rows:
        try:
            team_id = int(row["id"])
        except (KeyError, TypeError, ValueError):
            continue

        name = (
            row.get("name")
            or row.get("team")
            or ""
        ).strip()

        if name:
            mapping[team_id] = name

    return mapping

@app.get("/team-mapping")
def team_mapping(season: str = "2025-26"):
    """
    Safely match historical Premier League teams to the
    current FPL season by team name rather than team ID.
    """
    historical = get_historical_team_mapping(season)

    current = get_bootstrap()

    current_by_name = {
        team["name"].strip().lower(): team
        for team in current["teams"]
    }

    matched = []
    historical_only = []

    for historical_id, historical_name in historical.items():

        current_team = current_by_name.get(
            historical_name.strip().lower()
        )

        if current_team:
            matched.append({
                "historical_team_id": historical_id,
                "historical_name": historical_name,
                "current_team_id": current_team["id"],
                "current_name": current_team["name"],
            })
        else:
            historical_only.append({
                "historical_team_id": historical_id,
                "historical_name": historical_name,
            })

    historical_names = {
        name.strip().lower()
        for name in historical.values()
    }

    current_only = []

    for team in current["teams"]:
        if team["name"].strip().lower() not in historical_names:
            current_only.append({
                "current_team_id": team["id"],
                "current_name": team["name"],
            })

    return {
        "historical_season": season,
        "matched_count": len(matched),
        "matched": matched,
        "historical_only": historical_only,
        "current_only": current_only,
    }

# ============================================================
# PROJECTION ENGINE V2 - FIXTURE ADJUSTMENT
# ============================================================

MODEL_VERSION_V2 = "2.0-fixture-adjusted"

PROMOTED_DEFENCE_WEAKNESS = 1.10


def get_historical_team_strength_lookup(
    season="2025-26",
):
    """
    Build historical defensive-strength data keyed by team name.
    """

    fixture_url = (
        f"{HISTORICAL_BASE}/{season}/fixtures.csv"
    )

    response = requests.get(
        fixture_url,
        timeout=30,
    )
    response.raise_for_status()

    import csv
    import io

    rows = list(
        csv.DictReader(
            io.StringIO(
                response.content.decode("utf-8")
            )
        )
    )

    team_names = get_historical_team_mapping(
        season
    )

    teams = {}

    def ensure_team(team_id):
        if team_id not in teams:
            teams[team_id] = {
                "home_games": 0,
                "away_games": 0,
                "home_ga": 0,
                "away_ga": 0,
            }

    total_home_goals = 0
    total_away_goals = 0
    matches = 0

    for row in rows:
        try:
            home = int(row["team_h"])
            away = int(row["team_a"])
            hg = int(row["team_h_score"])
            ag = int(row["team_a_score"])
        except (KeyError, TypeError, ValueError):
            continue

        ensure_team(home)
        ensure_team(away)

        teams[home]["home_games"] += 1
        teams[home]["home_ga"] += ag

        teams[away]["away_games"] += 1
        teams[away]["away_ga"] += hg

        total_home_goals += hg
        total_away_goals += ag
        matches += 1

    league_home_goals = (
        total_home_goals / matches
        if matches else 0
    )

    league_away_goals = (
        total_away_goals / matches
        if matches else 0
    )

    lookup = {}

    for team_id, values in teams.items():

        name = team_names.get(team_id)

        if not name:
            continue

        home_ga_pg = (
            values["home_ga"]
            / values["home_games"]
            if values["home_games"]
            else league_away_goals
        )

        away_ga_pg = (
            values["away_ga"]
            / values["away_games"]
            if values["away_games"]
            else league_home_goals
        )

        lookup[name.strip().lower()] = {
            "historical_team_id": team_id,
            "home_defence_weakness": (
                home_ga_pg / league_away_goals
                if league_away_goals else 1.0
            ),
            "away_defence_weakness": (
                away_ga_pg / league_home_goals
                if league_home_goals else 1.0
            ),
        }

    return lookup


@app.get("/projection-v2/{player_id}")
def player_projection_v2(
    player_id: int,
    expected_minutes: float = 75,
    start_gw: int = 1,
    horizon: int = 6,
):
    """
    Fixture-adjusted attacking projection.

    V2 adjusts historical player xG/xA rates using the
    opponent's historical home/away defensive weakness.
    """

    horizon = max(1, min(horizon, 10))

    current = get_bootstrap()

    player = next(
        (
            p for p in current["elements"]
            if p["id"] == player_id
        ),
        None,
    )

    if player is None:
        raise HTTPException(
            status_code=404,
            detail="Current FPL player not found",
        )

    current_teams = {
        t["id"]: t["name"]
        for t in current["teams"]
    }

    history_lookup = get_historical_lookup_by_code()

    historical = history_lookup.get(
        safe_int(player.get("code"), -1)
    )

    if historical is None:
        raise HTTPException(
            status_code=404,
            detail="No historical player match found",
        )

    history_minutes = safe_int(
        historical.get("minutes")
    )

    if history_minutes <= 0:
        raise HTTPException(
            status_code=400,
            detail="No usable historical minutes",
        )

    history_xg = safe_float(
        historical.get("expected_goals")
    )

    history_xa = safe_float(
        historical.get("expected_assists")
    )

    base_xg_per90 = (
        history_xg / history_minutes * 90
    )

    base_xa_per90 = (
        history_xa / history_minutes * 90
    )

    strength_lookup = (
        get_historical_team_strength_lookup()
    )

    fixtures = get_player_fixtures(
        player["team"],
        start_gw=start_gw,
        horizon=horizon,
    )

    projections = []

    for fixture in fixtures:

        opponent_name = current_teams.get(
            fixture["opponent_id"]
        )

        historical_strength = (
            strength_lookup.get(
                opponent_name.strip().lower()
            )
            if opponent_name
            else None
        )

        if historical_strength:

            # Player at home -> opponent is away.
            if fixture["home"]:
                multiplier = (
                    historical_strength[
                        "away_defence_weakness"
                    ]
                )
                basis = (
                    "opponent historical "
                    "away defence"
                )

            # Player away -> opponent is home.
            else:
                multiplier = (
                    historical_strength[
                        "home_defence_weakness"
                    ]
                )
                basis = (
                    "opponent historical "
                    "home defence"
                )

            promoted_assumption = False

        else:
            multiplier = (
                PROMOTED_DEFENCE_WEAKNESS
            )
            basis = (
                "promoted-team default assumption"
            )
            promoted_assumption = True

        adjusted_xg_per90 = (
            base_xg_per90 * multiplier
        )

        adjusted_xa_per90 = (
            base_xa_per90 * multiplier
        )

        projection = (
            calculate_unadjusted_projection(
                position_id=
                    player["element_type"],
                xg_per90=adjusted_xg_per90,
                xa_per90=adjusted_xa_per90,
                expected_minutes=
                    expected_minutes,
            )
        )

        projections.append({
            **fixture,
            "opponent": opponent_name,
            "fixture_multiplier":
                round(multiplier, 3),
            "multiplier_basis": basis,
            "promoted_assumption":
                promoted_assumption,
            "base_xg_per90":
                round(base_xg_per90, 3),
            "base_xa_per90":
                round(base_xa_per90, 3),
            "adjusted_xg_per90":
                round(adjusted_xg_per90, 3),
            "adjusted_xa_per90":
                round(adjusted_xa_per90, 3),
            **projection,
        })

    total_xpts = sum(
        p["total_xpts"]
        for p in projections
    )

    return {
        "model_version": MODEL_VERSION_V2,
        "model_type":
            "fixture-adjusted attacking projection",
        "player": {
            "id": player["id"],
            "name": player["web_name"],
            "team":
                current_teams.get(
                    player["team"]
                ),
            "position_id":
                player["element_type"],
            "price":
                player["now_cost"] / 10,
        },
        "historical_basis": {
            "season": "2025-26",
            "minutes": history_minutes,
            "xg_per90":
                round(base_xg_per90, 3),
            "xa_per90":
                round(base_xa_per90, 3),
        },
        "assumptions": {
            "expected_minutes":
                expected_minutes,
            "promoted_team_defence_weakness":
                PROMOTED_DEFENCE_WEAKNESS,
            "fixture_adjustment": True,
        },
        "fixtures": projections,
        "totals": {
            "fixtures": len(projections),
            "total_xpts":
                round(total_xpts, 3),
        },
        "still_missing": [
            "clean-sheet points",
            "goalkeeper saves",
            "defensive contributions",
            "bonus",
            "GW-specific expected minutes",
            "current-season team-strength adjustment",
        ],
    }

@app.get("/historical-fields")
def historical_fields(
    season: str = "2025-26",
):
    """
    Show available columns in archived players_raw.csv.
    """
    url = (
        f"{HISTORICAL_BASE}/"
        f"{season}/players_raw.csv"
    )

    response = requests.get(url, timeout=30)
    response.raise_for_status()

    import csv
    import io

    reader = csv.DictReader(
        io.StringIO(
            response.content.decode("utf-8")
        )
    )

    return {
        "season": season,
        "field_count": len(
            reader.fieldnames or []
        ),
        "fields": reader.fieldnames or [],
    }

# ============================================================
# PROJECTION ENGINE V3 - CORE FPL XPTS
# ============================================================

MODEL_VERSION_V3 = "3.7-core-fpl-empirical-defcon"



_DEFCON_GW_CACHE = None

def get_empirical_defcon_lookup(season="2025-26", prior_matches=8.0):
    """Build shrunk match-level DefCon threshold probabilities by historical FPL ID.

    Uses the archived merged gameweek file. Matches with zero minutes are ignored.
    The observed threshold-hit rate is shrunk toward a player-specific Poisson
    prior derived from his mean defensive-contribution count, preventing small
    samples from producing extreme 0%/100% estimates.
    """
    global _DEFCON_GW_CACHE
    if _DEFCON_GW_CACHE is not None:
        return _DEFCON_GW_CACHE

    import csv
    import io

    url = f"{HISTORICAL_BASE}/{season}/gws/merged_gw.csv"
    response = requests.get(url, timeout=45)
    response.raise_for_status()
    reader = csv.DictReader(io.StringIO(response.content.decode("utf-8")))

    grouped = {}
    for row in reader:
        player_id = safe_int(row.get("element"), -1)
        minutes = safe_int(row.get("minutes"), 0)
        if player_id < 0 or minutes <= 0:
            continue
        raw = row.get("defensive_contribution")
        if raw in (None, ""):
            continue
        actions = safe_float(raw)
        bucket = grouped.setdefault(player_id, {"actions": [], "minutes": []})
        bucket["actions"].append(actions)
        bucket["minutes"].append(minutes)

    lookup = {}
    for player_id, bucket in grouped.items():
        actions = bucket["actions"]
        n = len(actions)
        if n == 0:
            continue
        lookup[player_id] = {
            "matches": n,
            "mean_actions": sum(actions) / n,
            "actions": actions,
            "prior_matches": float(prior_matches),
        }

    _DEFCON_GW_CACHE = lookup
    return lookup


def empirical_defcon_probability(historical_player_id, position_id, expected_minutes, fallback_mean):
    """Return empirical/shrunk probability of crossing the FPL DefCon threshold."""
    if position_id == 2:
        threshold = 10
    elif position_id in (3, 4):
        threshold = 12
    else:
        return {"probability": 0.0, "source": "not eligible", "matches": 0, "hits": 0}

    # Player-specific Poisson prior, preserving V3.5 as the fallback/regulariser.
    lam = max(0.0, float(fallback_mean))
    if lam <= 0:
        poisson_probability = 0.0
    else:
        term = math.exp(-lam)
        cdf = term
        for k in range(1, threshold):
            term *= lam / k
            cdf += term
        poisson_probability = max(0.0, min(1.0, 1.0 - cdf))

    try:
        record = get_empirical_defcon_lookup().get(safe_int(historical_player_id, -1))
    except Exception:
        record = None

    if not record or record["matches"] < 5:
        return {
            "probability": poisson_probability,
            "source": "poisson fallback: insufficient match-level history",
            "matches": 0 if not record else record["matches"],
            "hits": 0 if not record else sum(1 for x in record["actions"] if x >= threshold),
        }

    hits = sum(1 for x in record["actions"] if x >= threshold)
    n = record["matches"]
    prior_n = record["prior_matches"]
    shrunk = (hits + prior_n * poisson_probability) / (n + prior_n)
    return {
        "probability": max(0.0, min(1.0, shrunk)),
        "source": "empirical 2025/26 match hit-rate shrunk to player Poisson prior",
        "matches": n,
        "hits": hits,
        "raw_probability": hits / n,
        "poisson_prior_probability": poisson_probability,
        "prior_matches": prior_n,
    }

def clean_sheet_points_for_position(position_id):
    scoring = {
        1: 4,  # GK
        2: 4,  # DEF
        3: 1,  # MID
        4: 0,  # FWD
    }
    return scoring.get(position_id, 0)


def get_positional_rate_baselines(history_lookup):
    """Weighted league baselines by FPL position for rate shrinkage."""
    fields = {
        "xg_per90": "expected_goals",
        "xa_per90": "expected_assists",
        "clean_sheets_per90": "clean_sheets",
        "saves_per90": "saves",
        "bonus_per90": "bonus",
        "defcon_points_per90": "defensive_contribution",
    }
    totals = {pos: {k: 0.0 for k in fields} for pos in (1, 2, 3, 4)}
    minutes = {pos: 0 for pos in (1, 2, 3, 4)}

    for row in history_lookup.values():
        pos = safe_int(row.get("element_type"))
        mins = safe_int(row.get("minutes"))
        if pos not in totals or mins <= 0:
            continue
        minutes[pos] += mins
        for rate_name, raw_field in fields.items():
            totals[pos][rate_name] += safe_float(row.get(raw_field))

    baselines = {}
    for pos in totals:
        mins = minutes[pos]
        factor = 90 / mins if mins > 0 else 0.0
        baselines[pos] = {
            rate_name: totals[pos][rate_name] * factor
            for rate_name in fields
        }
    return baselines


def get_historical_player_rates(
    historical,
    position_baseline=None,
    shrinkage_minutes=900,
):
    """Convert totals to per-90 rates and shrink small samples to position norms."""
    minutes = safe_int(historical.get("minutes"))
    if minutes <= 0:
        return None

    factor = 90 / minutes
    raw = {
        "xg_per90": safe_float(historical.get("expected_goals")) * factor,
        "xa_per90": safe_float(historical.get("expected_assists")) * factor,
        "clean_sheets_per90": safe_float(historical.get("clean_sheets")) * factor,
        "saves_per90": safe_float(historical.get("saves")) * factor,
        "bonus_per90": safe_float(historical.get("bonus")) * factor,
        "defcon_points_per90": safe_float(
            historical.get("defensive_contribution")
        ) * factor,
    }

    reliability = minutes / (minutes + max(1, shrinkage_minutes))
    baseline = position_baseline or {key: 0.0 for key in raw}
    adjusted = {
        key: reliability * value + (1 - reliability) * baseline.get(key, 0.0)
        for key, value in raw.items()
    }

    return {
        "minutes": minutes,
        "reliability_weight": reliability,
        **adjusted,
        "raw_xg_per90": raw["xg_per90"],
        "raw_xa_per90": raw["xa_per90"],
    }


def estimate_expected_minutes(historical, default_minutes=75.0):
    """API-only availability estimate from last-season minutes, capped at 90."""
    historical_minutes = safe_int(historical.get("minutes"))
    if historical_minutes <= 0:
        return 0.0

    season_share = min(1.0, historical_minutes / (38 * 90))
    # Square-root dampening avoids over-penalising players who missed part of a season,
    # while still preventing tiny samples from being treated as regular starters.
    estimate = 90.0 * (season_share ** 0.5)
    return round(max(0.0, min(90.0, estimate)), 1)



def adjust_minutes_for_current_availability(player, baseline_minutes):
    """
    V1.4: adjust baseline expected minutes using live FPL availability.

    Historical availability remains the baseline. Current injury,
    suspension and chance-of-playing information can reduce it.
    """
    status = player.get("status", "a")
    chance = player.get("chance_of_playing_next_round")
    news = player.get("news", "") or ""

    baseline_minutes = max(0.0, min(float(baseline_minutes), 90.0))
    adjusted_minutes = baseline_minutes
    adjustment_reason = "no current adjustment"

    # Clearly unavailable / not selectable statuses.
    if status in {"i", "s", "u", "n"}:
        adjusted_minutes = 0.0
        adjustment_reason = f"FPL status '{status}' - unavailable"

    # FPL may publish an explicit probability for a flagged player.
    elif chance is not None:
        try:
            probability = max(0.0, min(float(chance), 100.0)) / 100.0
            adjusted_minutes = baseline_minutes * probability
            adjustment_reason = f"FPL chance of playing: {chance}%"
        except (TypeError, ValueError):
            pass

    return {
        "baseline_minutes": round(baseline_minutes, 1),
        "expected_minutes": round(adjusted_minutes, 1),
        "status": status,
        "chance_of_playing_next_round": chance,
        "news": news,
        "adjustment_reason": adjustment_reason,
    }


def get_historical_team_full_strength_lookup(season="2025-26"):
    """
    V1.5: historical home/away attack and defence strengths keyed by team name.

    Strength 1.0 = league average.
    Defence weakness > 1.0 = concedes more than league average.
    """
    url = f"{HISTORICAL_BASE}/{season}/fixtures.csv"
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    import csv
    import io

    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8"))))
    team_names = get_historical_team_mapping(season)

    teams = {}

    def ensure_team(team_id):
        if team_id not in teams:
            teams[team_id] = {
                "home_games": 0,
                "away_games": 0,
                "home_gf": 0,
                "away_gf": 0,
                "home_ga": 0,
                "away_ga": 0,
            }

    total_home_goals = 0
    total_away_goals = 0
    matches = 0

    for row in rows:
        try:
            home = int(row["team_h"])
            away = int(row["team_a"])
            hg = int(row["team_h_score"])
            ag = int(row["team_a_score"])
        except (KeyError, TypeError, ValueError):
            continue

        ensure_team(home)
        ensure_team(away)

        teams[home]["home_games"] += 1
        teams[home]["home_gf"] += hg
        teams[home]["home_ga"] += ag

        teams[away]["away_games"] += 1
        teams[away]["away_gf"] += ag
        teams[away]["away_ga"] += hg

        total_home_goals += hg
        total_away_goals += ag
        matches += 1

    league_home_goals = total_home_goals / matches if matches else 1.0
    league_away_goals = total_away_goals / matches if matches else 1.0

    lookup = {}

    for team_id, values in teams.items():
        name = team_names.get(team_id)
        if not name:
            continue

        home_games = values["home_games"]
        away_games = values["away_games"]

        home_gf = values["home_gf"] / home_games if home_games else league_home_goals
        away_gf = values["away_gf"] / away_games if away_games else league_away_goals
        home_ga = values["home_ga"] / home_games if home_games else league_away_goals
        away_ga = values["away_ga"] / away_games if away_games else league_home_goals

        lookup[name.strip().lower()] = {
            "historical_team_id": team_id,
            "home_attack_strength": home_gf / league_home_goals if league_home_goals else 1.0,
            "away_attack_strength": away_gf / league_away_goals if league_away_goals else 1.0,
            "home_defence_weakness": home_ga / league_away_goals if league_away_goals else 1.0,
            "away_defence_weakness": away_ga / league_home_goals if league_home_goals else 1.0,
        }

    return {
        "league_home_goals": league_home_goals,
        "league_away_goals": league_away_goals,
        "teams": lookup,
    }


def fixture_clean_sheet_probability(
    player_team_name,
    opponent_name,
    player_is_home,
    full_strength_lookup,
):
    """
    V1.5 fixture-specific team clean-sheet probability.

    Expected opponent goals =
        venue league scoring rate
        * opponent attack strength
        * player's team defensive weakness

    P(clean sheet) = exp(-expected opponent goals).

    Current-only/promoted teams use neutral attack strength (1.0) and
    PROMOTED_DEFENCE_WEAKNESS for their own defence.
    """
    teams = full_strength_lookup["teams"]

    own = teams.get((player_team_name or "").strip().lower())
    opponent = teams.get((opponent_name or "").strip().lower())

    if player_is_home:
        league_rate = full_strength_lookup["league_away_goals"]
        opponent_attack = (
            opponent["away_attack_strength"] if opponent else 1.0
        )
        own_defence_weakness = (
            own["home_defence_weakness"]
            if own
            else PROMOTED_DEFENCE_WEAKNESS
        )
        basis = "opponent away attack x team home defence"
    else:
        league_rate = full_strength_lookup["league_home_goals"]
        opponent_attack = (
            opponent["home_attack_strength"] if opponent else 1.0
        )
        own_defence_weakness = (
            own["away_defence_weakness"]
            if own
            else PROMOTED_DEFENCE_WEAKNESS
        )
        basis = "opponent home attack x team away defence"

    expected_goals_conceded = max(
        0.0,
        league_rate * opponent_attack * own_defence_weakness,
    )
    probability = math.exp(-expected_goals_conceded)

    return {
        "clean_sheet_probability": max(0.0, min(probability, 1.0)),
        "expected_goals_conceded": expected_goals_conceded,
        "clean_sheet_basis": basis,
        "opponent_attack_strength": opponent_attack,
        "team_defence_weakness": own_defence_weakness,
        "opponent_promoted_assumption": opponent is None,
        "team_promoted_assumption": own is None,
    }


def probabilistic_appearance(expected_minutes):
    """
    V3.3: convert expected minutes into appearance probabilities.

    Expected minutes alone cannot identify the exact distribution of playing
    time, so this is deliberately a transparent heuristic:

    - P(appearance) rises linearly from 0 to 1 between 0 and 60 expected mins.
    - Conditional on appearing, P(60+ mins) follows a logistic curve centred
      on 60 expected mins with an 8-minute scale.
    - P(60+) is capped by P(appearance).

    Expected FPL appearance points = P(appearance) + P(60+).
    This removes the hard 60-minute cliff while preserving near-2 appearance
    points for highly nailed 85-90 minute players.
    """
    minutes = max(0.0, min(float(expected_minutes), 90.0))

    if minutes <= 0:
        return {
            "appearance_probability": 0.0,
            "sixty_plus_probability": 0.0,
            "appearance_xpts": 0.0,
        }

    appearance_probability = min(1.0, minutes / 60.0)

    conditional_sixty_plus = 1.0 / (
        1.0 + math.exp(-(minutes - 60.0) / 8.0)
    )

    sixty_plus_probability = min(
        appearance_probability,
        appearance_probability * conditional_sixty_plus,
    )

    appearance_xpts = appearance_probability + sixty_plus_probability

    return {
        "appearance_probability": appearance_probability,
        "sixty_plus_probability": sixty_plus_probability,
        "appearance_xpts": appearance_xpts,
    }


def calculate_core_projection(
    position_id,
    xg_per90,
    xa_per90,
    clean_sheets_per90,
    saves_per90,
    bonus_per90,
    defcon_points_per90,
    expected_minutes,
    attack_multiplier=1.0,
    clean_sheet_multiplier=1.0,
    fixture_clean_sheet_probability=None,
    save_multiplier=1.0,
    bonus_fixture_adjustment=True,
    historical_player_id=None,
):
    """
    V3.4 expected FPL points for one fixture.

    Attack is adjusted for opponent defensive weakness.

    Clean-sheet rate is adjusted for opponent attacking
    strength.

    Goalkeeper saves are fixture-adjusted using opponent
    venue-specific attacking strength. Defensive contributions
    while defensive contributions remain unadjusted. Bonus starts from the
    shrunk historical bonus/90 baseline and is adjusted by a bounded,
    position-aware fixture multiplier. Appearance and clean-sheet eligibility use a probabilistic
    60-minute model rather than a hard expected-minutes threshold.
    """

    expected_minutes = max(
        0.0,
        min(float(expected_minutes), 90.0)
    )

    minutes_factor = expected_minutes / 90

    adjusted_xg_per90 = (
        xg_per90 * attack_multiplier
    )

    adjusted_xa_per90 = (
        xa_per90 * attack_multiplier
    )

    expected_goals = (
        adjusted_xg_per90 * minutes_factor
    )

    expected_assists = (
        adjusted_xa_per90 * minutes_factor
    )

    appearance = probabilistic_appearance(expected_minutes)
    appearance_probability = appearance["appearance_probability"]
    sixty_plus_probability = appearance["sixty_plus_probability"]
    appearance_xpts = appearance["appearance_xpts"]

    goal_xpts = (
        expected_goals
        * goal_points_for_position(
            position_id
        )
    )

    assist_xpts = (
        expected_assists * 3
    )

    # V1.5: prefer a fixture-specific team clean-sheet probability.
    # Historical clean-sheet rate remains as a backwards-compatible fallback.
    if fixture_clean_sheet_probability is not None:
        cs_probability = float(fixture_clean_sheet_probability)
    else:
        cs_probability = clean_sheets_per90 * clean_sheet_multiplier

    cs_probability = max(0.0, min(cs_probability, 1.0))

    # V3.3: CS points require 60+ actual minutes, so weight the
    # fixture clean-sheet probability by P(60+) rather than using a hard
    # expected-minutes threshold.
    clean_sheet_xpts = (
        cs_probability
        * sixty_plus_probability
        * clean_sheet_points_for_position(position_id)
    )

    # V1.6: fixture-adjust goalkeeper save volume.
    # Historical saves/90 is the goalkeeper baseline. Opponent
    # venue-specific attack strength is a proxy for shot pressure.
    if position_id == 1:
        bounded_save_multiplier = max(
            0.65,
            min(float(save_multiplier), 1.50),
        )
        expected_saves = (
            saves_per90
            * minutes_factor
            * bounded_save_multiplier
        )
        # Expected-value approximation of 1 FPL point per 3 saves.
        save_xpts = expected_saves / 3
    else:
        expected_saves = 0.0
        save_xpts = 0.0

    # V3.5: convert expected defensive-contribution actions into xPts.
    # DEF earns 2 points at 10+ CBIT actions; MID/FWD earn 2 points
    # at 12+ CBIRT actions. Goalkeepers are not eligible.
    #
    # Historical data gives us an average action rate rather than a
    # match-level probability distribution, so model the action count
    # as Poisson with mean equal to the minutes-adjusted expected count.
    # This gives a smooth probability of crossing the threshold instead
    # of incorrectly awarding 0/2 points based only on the mean.
    expected_defcon = (
        defcon_points_per90
        * minutes_factor
    )

    if position_id == 2:
        defcon_threshold = 10
    elif position_id in (3, 4):
        defcon_threshold = 12
    else:
        defcon_threshold = None

    if defcon_threshold is None or expected_defcon <= 0:
        defcon_probability = 0.0
        defcon_xpts = 0.0
        defcon_probability_source = "not eligible or zero expected actions"
        defcon_history_matches = 0
        defcon_history_hits = 0
        defcon_raw_probability = None
        defcon_poisson_prior_probability = None
    else:
        empirical = empirical_defcon_probability(
            historical_player_id=historical_player_id,
            position_id=position_id,
            expected_minutes=expected_minutes,
            fallback_mean=expected_defcon,
        )
        defcon_probability = empirical["probability"]
        defcon_xpts = 2.0 * defcon_probability
        defcon_probability_source = empirical["source"]
        defcon_history_matches = empirical.get("matches", 0)
        defcon_history_hits = empirical.get("hits", 0)
        defcon_raw_probability = empirical.get("raw_probability")
        defcon_poisson_prior_probability = empirical.get("poisson_prior_probability")

    # V3.6: translate the 2025/26 historical bonus baseline into the
    # 2026/27 BPS environment before applying the existing fixture multiplier.
    # Official 2026/27 changes reduce CBI reward (1 BPS per 3 rather than 2),
    # remove the Being Tackled penalty, and improve goalkeeper save treatment.
    # We do not have the full event-level BPS ledger here, so use a deliberately
    # bounded, transparent season-transition adjustment rather than pretending
    # to reconstruct exact BPS. Defenders with higher projected DefCon pressure
    # receive the largest reduction because CBI is the explicit overlap FPL
    # changed; GKs and attacking positions receive small directional uplifts.
    historical_base_bonus_xpts = bonus_per90 * minutes_factor

    if position_id == 1:
        bps_2026_adjustment = 1.05
        bps_2026_basis = "2026/27 GK BPS uplift: revised saves + big-chance saves"
    elif position_id == 2:
        # Scale the centre-back/CBI penalty with the probability of reaching
        # the 10-action DefCon threshold. Maximum reduction is 15%.
        bps_2026_adjustment = 1.0 - (0.15 * defcon_probability)
        bps_2026_basis = "2026/27 defender BPS: reduced CBI reward, scaled by DefCon probability"
    elif position_id in (3, 4):
        bps_2026_adjustment = 1.03
        bps_2026_basis = "2026/27 attacking BPS uplift: Being Tackled penalty removed"
    else:
        bps_2026_adjustment = 1.0
        bps_2026_basis = "no 2026/27 BPS adjustment"

    base_bonus_xpts = historical_base_bonus_xpts * bps_2026_adjustment

    if bonus_fixture_adjustment:
        cs_baseline = max(0.05, min(float(clean_sheets_per90), 0.95))
        cs_bonus_multiplier = cs_probability / cs_baseline
        cs_bonus_multiplier = max(0.65, min(cs_bonus_multiplier, 1.35))
        attack_bonus_multiplier = max(0.65, min(float(attack_multiplier), 1.35))
        save_bonus_multiplier = max(0.65, min(float(save_multiplier), 1.35))

        if position_id == 1:
            raw_bonus_multiplier = (
                0.70 * cs_bonus_multiplier
                + 0.30 * save_bonus_multiplier
            )
            bonus_basis = "70% clean-sheet outlook + 30% save pressure"
        elif position_id == 2:
            raw_bonus_multiplier = (
                0.55 * attack_bonus_multiplier
                + 0.45 * cs_bonus_multiplier
            )
            bonus_basis = "55% attacking fixture + 45% clean-sheet outlook"
        elif position_id == 3:
            raw_bonus_multiplier = (
                0.85 * attack_bonus_multiplier
                + 0.15 * cs_bonus_multiplier
            )
            bonus_basis = "85% attacking fixture + 15% clean-sheet outlook"
        else:
            raw_bonus_multiplier = attack_bonus_multiplier
            bonus_basis = "attacking fixture strength"

        bonus_multiplier = max(0.65, min(raw_bonus_multiplier, 1.35))
    else:
        bonus_multiplier = 1.0
        bonus_basis = "historical bonus/90 only"

    bonus_xpts = base_bonus_xpts * bonus_multiplier

    total_xpts = (
        appearance_xpts
        + goal_xpts
        + assist_xpts
        + clean_sheet_xpts
        + save_xpts
        + defcon_xpts
        + bonus_xpts
    )

    return {
        "expected_minutes":
            round(expected_minutes, 1),

        "expected_goals":
            round(expected_goals, 3),

        "expected_assists":
            round(expected_assists, 3),

        "clean_sheet_probability":
            round(cs_probability, 3),

        "expected_saves":
            round(expected_saves, 3),

        "appearance_probability":
            round(appearance_probability, 3),

        "sixty_plus_probability":
            round(sixty_plus_probability, 3),

        "appearance_xpts":
            round(appearance_xpts, 3),

        "goal_xpts":
            round(goal_xpts, 3),

        "assist_xpts":
            round(assist_xpts, 3),

        "clean_sheet_xpts":
            round(clean_sheet_xpts, 3),

        "save_xpts":
            round(save_xpts, 3),
        "expected_defensive_contributions":
            round(expected_defcon, 3),

        "defcon_threshold":
            defcon_threshold,

        "defcon_probability":
            round(defcon_probability, 3),
        "defcon_probability_source":
            defcon_probability_source,
        "defcon_history_matches":
            defcon_history_matches,
        "defcon_history_hits":
            defcon_history_hits,
        "defcon_raw_probability":
            None if defcon_raw_probability is None else round(defcon_raw_probability, 3),
        "defcon_poisson_prior_probability":
            None if defcon_poisson_prior_probability is None else round(defcon_poisson_prior_probability, 3),

        "defcon_xpts":
            round(defcon_xpts, 3),

        "historical_base_bonus_xpts":
            round(historical_base_bonus_xpts, 3),

        "bps_2026_adjustment":
            round(bps_2026_adjustment, 3),

        "bps_2026_basis":
            bps_2026_basis,

        "base_bonus_xpts":
            round(base_bonus_xpts, 3),

        "bonus_multiplier":
            round(bonus_multiplier, 3),

        "bonus_basis":
            bonus_basis,

        "bonus_xpts":
            round(bonus_xpts, 3),

        "total_xpts":
            round(total_xpts, 3),
    }


@app.get("/projection-v3/{player_id}")
def player_projection_v3(
    player_id: int,
    expected_minutes: float = 0,
    start_gw: int = 1,
    horizon: int = 6,
):
    """
    Core FPL expected-points projection.

    Includes:
    appearance, goals, assists, clean sheets,
    goalkeeper saves, defensive contributions and bonus.
    """

    horizon = max(1, min(horizon, 10))

    current = get_bootstrap()

    player = next(
        (
            p for p in current["elements"]
            if p["id"] == player_id
        ),
        None,
    )

    if player is None:
        raise HTTPException(
            status_code=404,
            detail="Current FPL player not found",
        )

    current_teams = {
        t["id"]: t["name"]
        for t in current["teams"]
    }

    full_team_strength = get_historical_team_full_strength_lookup()

    history_lookup = get_historical_lookup_by_code()

    historical = history_lookup.get(
        safe_int(player.get("code"), -1)
    )

    if historical is None:
        raise HTTPException(
            status_code=404,
            detail="No historical player match found",
        )

    positional_baselines = get_positional_rate_baselines(history_lookup)
    position_baseline = positional_baselines.get(player["element_type"], {})
    rates = get_historical_player_rates(
        historical,
        position_baseline=position_baseline,
    )

    if rates is None:
        raise HTTPException(
            status_code=400,
            detail="No usable historical minutes",
        )

    baseline_expected_minutes = (
        estimate_expected_minutes(historical)
        if expected_minutes <= 0
        else expected_minutes
    )

    # V1.4.1: use the same live FPL availability adjustment as the
    # squad optimiser. This prevents injured/suspended/unavailable
    # players from retaining historical baseline minutes in the
    # standalone V3 projection.
    availability = adjust_minutes_for_current_availability(
        player=player,
        baseline_minutes=baseline_expected_minutes,
    )
    model_expected_minutes = availability["expected_minutes"]

    strength_lookup = (
        get_historical_team_strength_lookup()
    )

    fixtures = get_player_fixtures(
        player["team"],
        start_gw=start_gw,
        horizon=horizon,
    )

    projections = []

    for fixture in fixtures:

        opponent_name = current_teams.get(
            fixture["opponent_id"]
        )

        
        cs_info = fixture_clean_sheet_probability(
            player_team_name=current_teams.get(player["team"]),
            opponent_name=opponent_name,
            player_is_home=fixture["home"],
            full_strength_lookup=full_team_strength,
        )
        opponent_strength = (
            strength_lookup.get(
                opponent_name.strip().lower()
            )
            if opponent_name
            else None
        )

        if opponent_strength:

            if fixture["home"]:
                attack_multiplier = (
                    opponent_strength[
                        "away_defence_weakness"
                    ]
                )

                # Approximate opponent attack from inverse
                # of their away defensive field is NOT valid,
                # so use FDR-derived neutral adjustment for CS
                # until team attack lookup is added.
                cs_multiplier = 1.0

                basis = (
                    "historical opponent "
                    "away defence"
                )

            else:
                attack_multiplier = (
                    opponent_strength[
                        "home_defence_weakness"
                    ]
                )

                cs_multiplier = 1.0

                basis = (
                    "historical opponent "
                    "home defence"
                )

            promoted_assumption = False

        else:
            attack_multiplier = (
                PROMOTED_DEFENCE_WEAKNESS
            )

            cs_multiplier = 1.0

            basis = (
                "promoted-team default assumption"
            )

            promoted_assumption = True

        save_multiplier = cs_info["opponent_attack_strength"]

        projection = calculate_core_projection(
            position_id=
                player["element_type"],

            xg_per90=
                rates["xg_per90"],

            xa_per90=
                rates["xa_per90"],

            clean_sheets_per90=
                rates["clean_sheets_per90"],

            saves_per90=
                rates["saves_per90"],

            bonus_per90=
                rates["bonus_per90"],

            defcon_points_per90=
                rates["defcon_points_per90"],

            expected_minutes=
                model_expected_minutes,

            attack_multiplier=
                attack_multiplier,

            clean_sheet_multiplier=
                cs_multiplier,
            fixture_clean_sheet_probability=cs_info["clean_sheet_probability"],
            save_multiplier=save_multiplier,
            historical_player_id=safe_int(historical.get("id"), -1),
        )

        projections.append({
            **fixture,

            "opponent":
                opponent_name,

            "attack_multiplier":
                round(
                    attack_multiplier,
                    3
                ),

            "fixture_basis":
                basis,

            "promoted_assumption":
                promoted_assumption,

            "expected_goals_conceded":
                round(cs_info["expected_goals_conceded"], 3),
            "clean_sheet_basis":
                cs_info["clean_sheet_basis"],
            "opponent_attack_strength":
                round(cs_info["opponent_attack_strength"], 3),
            "team_defence_weakness":
                round(cs_info["team_defence_weakness"], 3),
            "clean_sheet_promoted_assumption":
                (
                    cs_info["opponent_promoted_assumption"]
                    or cs_info["team_promoted_assumption"]
                ),
            "save_multiplier":
                round(max(0.65, min(float(save_multiplier), 1.50)), 3),
            "save_basis":
                "opponent venue-specific attack strength",

            **projection,
        })

    total_xpts = sum(
        p["total_xpts"]
        for p in projections
    )

    component_totals = {
        "appearance_xpts": round(
            sum(
                p["appearance_xpts"]
                for p in projections
            ),
            3,
        ),
        "goal_xpts": round(
            sum(
                p["goal_xpts"]
                for p in projections
            ),
            3,
        ),
        "assist_xpts": round(
            sum(
                p["assist_xpts"]
                for p in projections
            ),
            3,
        ),
        "clean_sheet_xpts": round(
            sum(
                p["clean_sheet_xpts"]
                for p in projections
            ),
            3,
        ),
        "save_xpts": round(
            sum(
                p["save_xpts"]
                for p in projections
            ),
            3,
        ),
        "defcon_xpts": round(
            sum(
                p["defcon_xpts"]
                for p in projections
            ),
            3,
        ),
        "bonus_xpts": round(
            sum(
                p["bonus_xpts"]
                for p in projections
            ),
            3,
        ),
    }

    return {
        "model_version":
            MODEL_VERSION_V3,

        "model_type":
            "core FPL expected points",

        "player": {
            "id": player["id"],
            "name": player["web_name"],
            "team":
                current_teams.get(
                    player["team"]
                ),
            "position_id":
                player["element_type"],
            "price":
                player["now_cost"] / 10,
            "status":
                player.get("status"),
        },

        "historical_rates_per90": {
            key: round(value, 3)
            if isinstance(value, float)
            else value
            for key, value
            in rates.items()
        },

        "assumptions": {
            "expected_minutes":
                model_expected_minutes,
            "baseline_expected_minutes":
                baseline_expected_minutes,
            "expected_minutes_mode":
                "auto" if expected_minutes <= 0 else "manual",
            "current_availability_adjustment":
                True,
            "availability_source":
                "live FPL status/chance_of_playing_next_round/news",
            "availability":
                availability,
            "rate_shrinkage_minutes":
                900,
            "promoted_team_defence_weakness":
                PROMOTED_DEFENCE_WEAKNESS,
            "clean_sheet_fixture_adjustment":
                True,
            "save_fixture_adjustment":
                True,
            "bonus_fixture_adjustment":
                True,
            "defcon_fixture_adjustment":
                False,
        },

        "fixtures":
            projections,

        "component_totals":
            component_totals,

        "totals": {
            "fixtures":
                len(projections),
            "total_xpts":
                round(total_xpts, 3),
        },
    }

# ============================================================
# SQUAD OPTIMISER V1.6 - MULTI-WEEK CAPTAINCY
# ============================================================

from pulp import (
    LpProblem,
    LpMaximize,
    LpVariable,
    lpSum,
    LpBinary,
    PULP_CBC_CMD,
    LpStatus,
)


def get_historical_lookup_by_code(
    season="2025-26",
):
    """
    Historical player lookup using persistent FPL player code.
    """
    url = f"{HISTORICAL_BASE}/{season}/players_raw.csv"
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    import csv
    import io

    rows = list(
        csv.DictReader(
            io.StringIO(response.content.decode("utf-8"))
        )
    )

    lookup = {}
    for row in rows:
        try:
            code = int(row["code"])
        except (KeyError, TypeError, ValueError):
            continue
        lookup[code] = row

    return lookup


def project_player_for_optimizer(
    player,
    current,
    history_lookup,
    strength_lookup,
    positional_baselines,
    full_strength_lookup,
    expected_minutes=0,
    start_gw=1,
    horizon=6,
):
    """
    Produce V3-style total xPts for one player without
    making an internal HTTP call to our own API.
    """
    player_code = player.get("code")
    try:
        player_code = int(player_code)
    except (TypeError, ValueError):
        return None

    historical = history_lookup.get(player_code)
    if historical is None:
        return None

    position_baseline = positional_baselines.get(
        player["element_type"], {}
    )
    rates = get_historical_player_rates(
        historical,
        position_baseline=position_baseline,
    )
    if rates is None:
        return None

    baseline_expected_minutes = (
        estimate_expected_minutes(historical)
        if expected_minutes <= 0
        else expected_minutes
    )

    availability = adjust_minutes_for_current_availability(
        player=player,
        baseline_minutes=baseline_expected_minutes,
    )
    model_expected_minutes = availability["expected_minutes"]

    current_teams = {
        t["id"]: t["name"]
        for t in current["teams"]
    }

    fixtures = get_player_fixtures(
        player["team"],
        start_gw=start_gw,
        horizon=horizon,
    )
    if not fixtures:
        return None

    gw_projections = []

    for fixture in fixtures:
        opponent_name = current_teams.get(
            fixture["opponent_id"]
        )

        cs_info = fixture_clean_sheet_probability(
            player_team_name=current_teams.get(player["team"]),
            opponent_name=opponent_name,
            player_is_home=fixture["home"],
            full_strength_lookup=full_strength_lookup,
        )

        opponent_strength = (
            strength_lookup.get(opponent_name.strip().lower())
            if opponent_name
            else None
        )

        if opponent_strength:
            if fixture["home"]:
                attack_multiplier = opponent_strength[
                    "away_defence_weakness"
                ]
            else:
                attack_multiplier = opponent_strength[
                    "home_defence_weakness"
                ]
        else:
            attack_multiplier = PROMOTED_DEFENCE_WEAKNESS

        projection = calculate_core_projection(
            position_id=player["element_type"],
            xg_per90=rates["xg_per90"],
            xa_per90=rates["xa_per90"],
            clean_sheets_per90=rates["clean_sheets_per90"],
            saves_per90=rates["saves_per90"],
            bonus_per90=rates["bonus_per90"],
            defcon_points_per90=rates["defcon_points_per90"],
            expected_minutes=model_expected_minutes,
            attack_multiplier=attack_multiplier,
            clean_sheet_multiplier=1.0,
            fixture_clean_sheet_probability=
                cs_info["clean_sheet_probability"],
            save_multiplier=
                cs_info["opponent_attack_strength"],
        )

        gw_projections.append({
            "gameweek": fixture["gameweek"],
            "opponent": opponent_name,
            "expected_goals_conceded": round(
                cs_info["expected_goals_conceded"], 3
            ),
            "clean_sheet_basis": cs_info["clean_sheet_basis"],
            "opponent_attack_strength": round(
                cs_info["opponent_attack_strength"], 3
            ),
            "team_defence_weakness": round(
                cs_info["team_defence_weakness"], 3
            ),
            "clean_sheet_promoted_assumption": (
                cs_info["opponent_promoted_assumption"]
                or cs_info["team_promoted_assumption"]
            ),
            "save_multiplier": round(
                max(
                    0.65,
                    min(
                        float(cs_info["opponent_attack_strength"]),
                        1.50,
                    ),
                ),
                3,
            ),
            "save_basis":
                "opponent venue-specific attack strength",
            "expected_saves": projection["expected_saves"],
            "save_xpts": projection["save_xpts"],
            "home": fixture["home"],
            "xpts": projection["total_xpts"],
        })

    total_xpts = sum(
        gw["xpts"] for gw in gw_projections
    )

    return {
        "id": player["id"],
        "name": player["web_name"],
        "team_id": player["team"],
        "team": current_teams.get(player["team"]),
        "position_id": player["element_type"],
        "price": player["now_cost"] / 10,
        "expected_minutes": model_expected_minutes,
        "availability": availability,
        "historical_minutes": rates["minutes"],
        "rate_reliability": round(
            rates["reliability_weight"], 3
        ),
        "total_xpts": round(total_xpts, 3),
        "gw_projections": gw_projections,
    }


@app.get("/optimize-squad")
def optimize_squad(
    budget: float = 100.0,
    expected_minutes: float = 0,
    start_gw: int = 1,
    horizon: int = 6,
):
    """
    V1.6 bench-weighted squad optimiser with multi-week captaincy.

    Optimises:
    - legal 15-player FPL squad
    - legal starting XI independently in every GW
    - ordered outfield bench independently in every GW
    - reserve goalkeeper independently in every GW
    - captain independently in every GW

    Objective weights:
    XI = 1.00
    bench 1 = 0.30
    bench 2 = 0.10
    bench 3 = 0.03
    reserve GK = 0.03
    """

    horizon = max(1, min(horizon, 10))
    current = get_bootstrap()
    history_lookup = get_historical_lookup_by_code()
    strength_lookup = get_historical_team_strength_lookup()
    full_strength_lookup = (
        get_historical_team_full_strength_lookup()
    )
    positional_baselines = (
        get_positional_rate_baselines(history_lookup)
    )

    candidates = []

    for player in current["elements"]:
        # Doubtful/flagged players may remain in the pool because their
        # live chance-of-playing reduces expected minutes. Clearly
        # unavailable players remain excluded.
        if player.get("status") in {"i", "s", "u", "n"}:
            continue
        if player.get("can_select") is False:
            continue

        projection = project_player_for_optimizer(
            player=player,
            current=current,
            history_lookup=history_lookup,
            strength_lookup=strength_lookup,
            positional_baselines=positional_baselines,
            full_strength_lookup=full_strength_lookup,
            expected_minutes=expected_minutes,
            start_gw=start_gw,
            horizon=horizon,
        )

        if projection is not None:
            candidates.append(projection)

    if not candidates:
        raise HTTPException(
            status_code=500,
            detail="No projection candidates available",
        )

    gameweeks = sorted({
        gw["gameweek"]
        for p in candidates
        for gw in p["gw_projections"]
    })

    gw_xpts = {
        (p["id"], gw["gameweek"]): gw["xpts"]
        for p in candidates
        for gw in p["gw_projections"]
    }

    problem = LpProblem(
        "FPL_Bench_Weighted_Multiweek_Captaincy_Optimizer",
        LpMaximize,
    )

    selected = {
        p["id"]: LpVariable(
            f"squad_{p['id']}",
            cat=LpBinary,
        )
        for p in candidates
    }

    starting = {
        (p["id"], gw): LpVariable(
            f"start_{p['id']}_{gw}",
            cat=LpBinary,
        )
        for p in candidates
        for gw in gameweeks
    }

    bench1 = {
        (p["id"], gw): LpVariable(
            f"bench1_{p['id']}_{gw}",
            cat=LpBinary,
        )
        for p in candidates
        for gw in gameweeks
    }

    bench2 = {
        (p["id"], gw): LpVariable(
            f"bench2_{p['id']}_{gw}",
            cat=LpBinary,
        )
        for p in candidates
        for gw in gameweeks
    }

    bench3 = {
        (p["id"], gw): LpVariable(
            f"bench3_{p['id']}_{gw}",
            cat=LpBinary,
        )
        for p in candidates
        for gw in gameweeks
    }

    reserve_gk = {
        (p["id"], gw): LpVariable(
            f"reserve_gk_{p['id']}_{gw}",
            cat=LpBinary,
        )
        for p in candidates
        for gw in gameweeks
    }

    captain = {
        (p["id"], gw): LpVariable(
            f"captain_{p['id']}_{gw}",
            cat=LpBinary,
        )
        for p in candidates
        for gw in gameweeks
    }

    XI_WEIGHT = 1.00
    BENCH1_WEIGHT = 0.30
    BENCH2_WEIGHT = 0.10
    BENCH3_WEIGHT = 0.03
    RESERVE_GK_WEIGHT = 0.03

    # Weighted expected points from every weekly squad role,
    # plus one extra copy of each gameweek captain's points.
    problem += (
        lpSum(
            XI_WEIGHT
            * starting[(p["id"], gw)]
            * gw_xpts.get((p["id"], gw), 0.0)
            for p in candidates
            for gw in gameweeks
        )
        + lpSum(
            BENCH1_WEIGHT
            * bench1[(p["id"], gw)]
            * gw_xpts.get((p["id"], gw), 0.0)
            for p in candidates
            for gw in gameweeks
        )
        + lpSum(
            BENCH2_WEIGHT
            * bench2[(p["id"], gw)]
            * gw_xpts.get((p["id"], gw), 0.0)
            for p in candidates
            for gw in gameweeks
        )
        + lpSum(
            BENCH3_WEIGHT
            * bench3[(p["id"], gw)]
            * gw_xpts.get((p["id"], gw), 0.0)
            for p in candidates
            for gw in gameweeks
        )
        + lpSum(
            RESERVE_GK_WEIGHT
            * reserve_gk[(p["id"], gw)]
            * gw_xpts.get((p["id"], gw), 0.0)
            for p in candidates
            for gw in gameweeks
        )
        + lpSum(
            captain[(p["id"], gw)]
            * gw_xpts.get((p["id"], gw), 0.0)
            for p in candidates
            for gw in gameweeks
        )
    )

    # Legal 15-player squad.
    problem += (
        lpSum(
            selected[p["id"]]
            for p in candidates
        )
        == 15
    )

    problem += (
        lpSum(
            selected[p["id"]] * p["price"]
            for p in candidates
        )
        <= budget
    )

    position_requirements = {
        1: 2,
        2: 5,
        3: 5,
        4: 3,
    }

    for position_id, required in position_requirements.items():
        problem += (
            lpSum(
                selected[p["id"]]
                for p in candidates
                if p["position_id"] == position_id
            )
            == required
        )

    for team_id in {
        p["team_id"] for p in candidates
    }:
        problem += (
            lpSum(
                selected[p["id"]]
                for p in candidates
                if p["team_id"] == team_id
            )
            <= 3
        )

    # Every selected player has exactly one weekly role:
    # XI, bench 1, bench 2, bench 3, or reserve GK.
    for gw in gameweeks:

        problem += (
            lpSum(
                starting[(p["id"], gw)]
                for p in candidates
            )
            == 11
        )

        problem += (
            lpSum(
                bench1[(p["id"], gw)]
                for p in candidates
            )
            == 1
        )

        problem += (
            lpSum(
                bench2[(p["id"], gw)]
                for p in candidates
            )
            == 1
        )

        problem += (
            lpSum(
                bench3[(p["id"], gw)]
                for p in candidates
            )
            == 1
        )

        problem += (
            lpSum(
                reserve_gk[(p["id"], gw)]
                for p in candidates
            )
            == 1
        )

        for p in candidates:
            pid = p["id"]

            problem += (
                starting[(pid, gw)]
                + bench1[(pid, gw)]
                + bench2[(pid, gw)]
                + bench3[(pid, gw)]
                + reserve_gk[(pid, gw)]
                == selected[pid]
            )

            # Only outfield players can occupy the three ordered
            # outfield bench positions.
            if p["position_id"] == 1:
                problem += bench1[(pid, gw)] == 0
                problem += bench2[(pid, gw)] == 0
                problem += bench3[(pid, gw)] == 0

            # Only a goalkeeper can be the reserve GK.
            else:
                problem += reserve_gk[(pid, gw)] == 0

        # Legal starting XI:
        # exactly 1 GK, 3-5 DEF, 2-5 MID, 1-3 FWD.
        problem += (
            lpSum(
                starting[(p["id"], gw)]
                for p in candidates
                if p["position_id"] == 1
            )
            == 1
        )

        problem += (
            lpSum(
                starting[(p["id"], gw)]
                for p in candidates
                if p["position_id"] == 2
            )
            >= 3
        )
        problem += (
            lpSum(
                starting[(p["id"], gw)]
                for p in candidates
                if p["position_id"] == 2
            )
            <= 5
        )

        problem += (
            lpSum(
                starting[(p["id"], gw)]
                for p in candidates
                if p["position_id"] == 3
            )
            >= 2
        )
        problem += (
            lpSum(
                starting[(p["id"], gw)]
                for p in candidates
                if p["position_id"] == 3
            )
            <= 5
        )

        problem += (
            lpSum(
                starting[(p["id"], gw)]
                for p in candidates
                if p["position_id"] == 4
            )
            >= 1
        )
        problem += (
            lpSum(
                starting[(p["id"], gw)]
                for p in candidates
                if p["position_id"] == 4
            )
            <= 3
        )

        # Exactly one captain in every GW, and the captain must start.
        problem += (
            lpSum(
                captain[(p["id"], gw)]
                for p in candidates
            )
            == 1
        )

        for p in candidates:
            problem += (
                captain[(p["id"], gw)]
                <= starting[(p["id"], gw)]
            )

    problem.solve(PULP_CBC_CMD(msg=False))

    status = LpStatus[problem.status]
    if status != "Optimal":
        raise HTTPException(
            status_code=500,
            detail=(
                "Optimizer did not find an optimal squad: "
                f"{status}"
            ),
        )

    squad = [
        p for p in candidates
        if selected[p["id"]].value() == 1
    ]

    position_names = {
        1: "GK",
        2: "DEF",
        3: "MID",
        4: "FWD",
    }

    for p in squad:
        p["position"] = position_names.get(
            p["position_id"]
        )

    total_cost = sum(
        p["price"] for p in squad
    )

    weekly_lineups = []

    xi_total = 0.0
    weighted_bench_total = 0.0
    captain_bonus_total = 0.0

    for gw in gameweeks:

        xi = [
            p for p in squad
            if starting[(p["id"], gw)].value() == 1
        ]

        xi.sort(
            key=lambda p: (
                p["position_id"],
                -gw_xpts.get((p["id"], gw), 0.0),
            )
        )

        b1 = next(
            p for p in squad
            if bench1[(p["id"], gw)].value() == 1
        )
        b2 = next(
            p for p in squad
            if bench2[(p["id"], gw)].value() == 1
        )
        b3 = next(
            p for p in squad
            if bench3[(p["id"], gw)].value() == 1
        )
        rgk = next(
            p for p in squad
            if reserve_gk[(p["id"], gw)].value() == 1
        )

        captain_player = next(
            p for p in squad
            if captain[(p["id"], gw)].value() == 1
        )

        xi_xpts = sum(
            gw_xpts.get((p["id"], gw), 0.0)
            for p in xi
        )

        bench_weighted_xpts = (
            BENCH1_WEIGHT
            * gw_xpts.get((b1["id"], gw), 0.0)
            + BENCH2_WEIGHT
            * gw_xpts.get((b2["id"], gw), 0.0)
            + BENCH3_WEIGHT
            * gw_xpts.get((b3["id"], gw), 0.0)
            + RESERVE_GK_WEIGHT
            * gw_xpts.get((rgk["id"], gw), 0.0)
        )

        captain_bonus = gw_xpts.get(
            (captain_player["id"], gw),
            0.0,
        )

        xi_total += xi_xpts
        weighted_bench_total += bench_weighted_xpts
        captain_bonus_total += captain_bonus

        weekly_lineups.append({
            "gameweek": gw,
            "formation": "-".join(
                str(
                    sum(
                        1 for p in xi
                        if p["position_id"] == pos
                    )
                )
                for pos in (2, 3, 4)
            ),
            "xi_xpts": round(xi_xpts, 3),
            "weighted_bench_xpts": round(
                bench_weighted_xpts, 3
            ),
            "captain_bonus_xpts": round(captain_bonus, 3),
            "captain": {
                "id": captain_player["id"],
                "name": captain_player["name"],
                "xpts": gw_xpts.get((captain_player["id"], gw), 0.0),
            },
            "starting_xi": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "team": p["team"],
                    "position": p["position"],
                    "price": p["price"],
                    "xpts": gw_xpts.get(
                        (p["id"], gw), 0.0
                    ),
                }
                for p in xi
            ],
            "bench": [
                {
                    "order": 1,
                    "role": "bench_1",
                    "weight": BENCH1_WEIGHT,
                    "id": b1["id"],
                    "name": b1["name"],
                    "team": b1["team"],
                    "position": b1["position"],
                    "price": b1["price"],
                    "xpts": gw_xpts.get(
                        (b1["id"], gw), 0.0
                    ),
                },
                {
                    "order": 2,
                    "role": "bench_2",
                    "weight": BENCH2_WEIGHT,
                    "id": b2["id"],
                    "name": b2["name"],
                    "team": b2["team"],
                    "position": b2["position"],
                    "price": b2["price"],
                    "xpts": gw_xpts.get(
                        (b2["id"], gw), 0.0
                    ),
                },
                {
                    "order": 3,
                    "role": "bench_3",
                    "weight": BENCH3_WEIGHT,
                    "id": b3["id"],
                    "name": b3["name"],
                    "team": b3["team"],
                    "position": b3["position"],
                    "price": b3["price"],
                    "xpts": gw_xpts.get(
                        (b3["id"], gw), 0.0
                    ),
                },
                {
                    "order": 4,
                    "role": "reserve_gk",
                    "weight": RESERVE_GK_WEIGHT,
                    "id": rgk["id"],
                    "name": rgk["name"],
                    "team": rgk["team"],
                    "position": rgk["position"],
                    "price": rgk["price"],
                    "xpts": gw_xpts.get(
                        (rgk["id"], gw), 0.0
                    ),
                },
            ],
        })

    gw1_lineup = next(
        row for row in weekly_lineups
        if row["gameweek"] == start_gw
    )

    gw1_captain_player = next(
        p for p in squad
        if captain[(p["id"], start_gw)].value() == 1
    )

    gw1_xi_ids = {
        p["id"]
        for p in squad
        if starting[(p["id"], start_gw)].value() == 1
    }

    vice_candidates = sorted(
        [
            p for p in squad
            if (
                p["id"] in gw1_xi_ids
                and p["id"] != gw1_captain_player["id"]
            )
        ],
        key=lambda p: gw_xpts.get(
            (p["id"], start_gw), 0.0
        ),
        reverse=True,
    )

    vice_player = (
        vice_candidates[0]
        if vice_candidates
        else gw1_captain_player
    )

    gw1_captain_bonus = gw_xpts.get(
        (gw1_captain_player["id"], start_gw),
        0.0,
    )

    objective_xpts = (
        xi_total
        + weighted_bench_total
        + captain_bonus_total
    )

    squad.sort(
        key=lambda x: (
            x["position_id"],
            -x["total_xpts"],
        )
    )

    return {
        "optimizer_version": "1.6-multiweek-captaincy",
        "projection_model": MODEL_VERSION_V3,
        "objective": (
            "maximise weighted expected FPL points across the "
            "horizon: XI 1.00, bench1 0.30, bench2 0.10, "
            "bench3 0.03, reserve GK 0.03, plus captaincy in every gameweek"
        ),
        "constraints": {
            "budget": budget,
            "squad_size": 15,
            "goalkeepers": 2,
            "defenders": 5,
            "midfielders": 5,
            "forwards": 3,
            "max_per_club": 3,
            "legal_xi_each_gameweek": True,
            "ordered_outfield_bench_each_gameweek": True,
            "reserve_gk_each_gameweek": True,
        },
        "assumptions": {
            "expected_minutes_mode": (
                "auto from historical availability"
                if expected_minutes <= 0
                else "manual override"
            ),
            "manual_expected_minutes": (
                None
                if expected_minutes <= 0
                else expected_minutes
            ),
            "rate_shrinkage_minutes": 900,
            "start_gw": start_gw,
            "horizon": horizon,
            "bench_points_in_objective": True,
            "bench_weights": {
                "bench_1": BENCH1_WEIGHT,
                "bench_2": BENCH2_WEIGHT,
                "bench_3": BENCH3_WEIGHT,
                "reserve_gk": RESERVE_GK_WEIGHT,
            },
            "bench_order_optimised_each_gameweek": True,
            "captaincy_each_gameweek": True,
            "vice_captain_optimised": False,
            "vice_captain_method":
                "highest GW1 xPts among non-captain starters",
            "player_specific_minutes": expected_minutes <= 0,
            "historical_player_matching":
                "persistent FPL player code",
            "current_availability_adjustment": True,
            "availability_source":
                "live FPL status/chance_of_playing_next_round/news",
        },
        "candidate_count": len(candidates),
        "total_cost": round(total_cost, 1),
        "money_remaining": round(
            budget - total_cost, 1
        ),
        "projected_xi_xpts": round(
            xi_total, 3
        ),
        "weighted_bench_xpts": round(
            weighted_bench_total, 3
        ),
        "gw1_captain_bonus_xpts": round(
            gw1_captain_bonus, 3
        ),
        "captain_bonus_xpts": round(
            captain_bonus_total, 3
        ),
        "objective_xpts": round(
            objective_xpts, 3
        ),
        "gw1": {
            "captain": {
                "id": gw1_captain_player["id"],
                "name": gw1_captain_player["name"],
                "xpts": gw_xpts.get(
                    (gw1_captain_player["id"], start_gw),
                    0.0,
                ),
            },
            "vice_captain": {
                "id": vice_player["id"],
                "name": vice_player["name"],
                "xpts": gw_xpts.get(
                    (vice_player["id"], start_gw),
                    0.0,
                ),
            },
            "bench": gw1_lineup["bench"],
        },
        "weekly_lineups": weekly_lineups,
        "squad": squad,
    }
