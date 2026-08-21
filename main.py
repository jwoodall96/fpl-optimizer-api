from fastapi import FastAPI, HTTPException
import requests

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

    history_lookup = get_historical_lookup()

    historical = history_lookup.get(
        player["web_name"].strip().lower()
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

    history_lookup = get_historical_lookup()

    historical = history_lookup.get(
        player["web_name"].strip().lower()
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
