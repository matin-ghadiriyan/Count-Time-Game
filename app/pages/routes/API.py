from flask import jsonify , Blueprint
from app.models import User

API = Blueprint("API", __name__ , url_prefix="/api")

# ----------------------------------------------------------------
# Lightweight API (optional for charts/statistics)
# ----------------------------------------------------------------
@API.route("/leaderboard")
def api_leaderboard():
    """JSON version of the scorecard for possible front-end consumption."""
    users = (
        User.query.filter(User.games_played > 0)
        .order_by(User.wins.desc(), User.games_played.asc())
        .limit(50)
        .all()
    )
    return jsonify(
        [
            {
                "username": u.username,
                "wins": u.wins,
                "losses": u.losses,
                "games_played": u.games_played,
            }
            for u in users
        ]
    )
