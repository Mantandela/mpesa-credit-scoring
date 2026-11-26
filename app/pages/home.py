"""Home: "Good <time of day>, <first name>" with Check score on the right. Row 1: the hero score card (with the score
over time) and, beside it, the estimated limit and Quick actions. Row 2: "Your financial life", the Business health
tiles. Row 3: Recent activity (score checks and applications). Laptop: two columns in row 1; phone: stacked."""
from app import components as ui, service
from app.pages import chart_points, checks_and_result

ACTIONS = (("Check score", "head_score", "score", "primary"),)


def render(conn, user) -> None:
    checks, result = checks_and_result(conn, user)        # one checks query: the latest 5 (card, chart and activity)
    hello = f"{ui.greeting()}, {ui.first_name(user)}".rstrip(", ")
    if result is None:
        ui.page_header(user, hello, "Home")               # the card below has the one Check score button
        ui.no_score_card()                                # one friendly card, nothing else
        return
    ui.page_header(user, hello, "Home", actions=ACTIONS)
    apps = service.list_applications(conn, user["id"])
    left, right = ui.two_columns("home", "fixed")
    with left:
        ui.score_hero(result, chart_points(checks, result))
    with right:
        ui.limit_card(result)
        ui.quick_actions()
    ui.health_tiles(result["pillars"])
    ui.activity_card(checks, apps)
