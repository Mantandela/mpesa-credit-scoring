"""Home: greeting header with Check score and Apply; the score card (with the score chart), the estimated limit, the top
score drags, Business health and the latest applications. Laptop: two columns; phone: the same blocks stacked."""
from app import components as ui, service
from app.pages import chart_points, checks_and_result

N_LATEST = 3
ACTIONS = (("Check score", "head_score", "score", "primary"), ("Apply", "head_apply", "apply", "secondary"))


def render(conn, user) -> None:
    checks, result = checks_and_result(conn, user)        # one checks query: the latest 5 (card and chart)
    hello = f"{ui.greeting()}, {ui.first_name(user)}".rstrip(", ")
    if result is None:
        ui.page_header(user, hello)
        ui.no_score_card()                                # one friendly card, nothing else
        return
    ui.page_header(user, hello, f"Last check · {ui.date_time(result['created_at'])}", actions=ACTIONS)
    apps = service.list_applications(conn, user["id"])[:N_LATEST]
    left, right = ui.two_columns("home", "fixed")
    with left:
        ui.score_card(result, chart_points(checks, result))
        ui.limit_card(result)
        ui.drags_card(result)
    with right:
        ui.health_card(result)
        ui.latest_apps_card(apps)
