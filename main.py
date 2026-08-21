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
