from flask import render_template , Blueprint
from flask_login import current_user
from app.models import User , GamePlayer , Game
from flask_login import login_required

LeaderboardAndHistory = Blueprint("LeaderboardAndHistory", __name__)

# ----------------------------------------------------------------
# Leaderboard and History
# ----------------------------------------------------------------
@LeaderboardAndHistory.route("/leaderboard")
def leaderboard():
    """Top players table based on number of wins and win ratio."""
    users = (
        User.query.filter(User.games_played > 0)
        .order_by(User.wins.desc(), User.games_played.asc())
        .limit(50)
        .all()
    )
    return render_template("leaderboard.html", users=users)


@LeaderboardAndHistory.route("/history")
@login_required
def history():
    """The current user's game history."""
    records = (
        GamePlayer.query.filter_by(user_id=current_user.id)
        .join(Game)
        .order_by(GamePlayer.created_at.desc())
        .limit(50)
        .all()
    )

    history_items = []
    for record in records:
        game = record.game
        winner_name = game.winner.username if game.winner else None
        history_items.append(
            {
                "game_id": game.id,
                "room_id": game.room_id,
                "result": record.result,
                "elapsed_time": record.elapsed_time,
                "winner": winner_name,
                "finished_at": game.finished_at,
            }
        )

    return render_template("history.html", items=history_items)