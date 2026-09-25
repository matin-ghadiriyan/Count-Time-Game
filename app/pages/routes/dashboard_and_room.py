from flask import render_template , Blueprint , redirect , url_for , flash
from flask_login import current_user , login_required
from app.models import User , Game , GamePlayer , PlayerResult
import random
from app.extensions import db

DashboardAndRoom = Blueprint("DashboardAndRoom", __name__)

# ----------------------------------------------------------------
# helper functions
# ----------------------------------------------------------------
def _generate_room_code(length: int = 6) -> str:
    """Generate a random room code with uppercase letters and digits (no special characters)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(random.choices(alphabet, k=length))

# ----------------------------------------------------------------
# dashboard and room
# ----------------------------------------------------------------
@DashboardAndRoom.route("/dashboard")
@login_required
def dashboard():
    """The dashboard: create/join room and user's rating."""
    return render_template("dashboard.html")


@DashboardAndRoom.route("/create-room", methods=["POST"])
@login_required
def create_room():
    """Create a new Room code and redirect the user to the game page of that Room.

    Note: The Room itself is created in the server memory (socket_on/room_manager).
    Here only the code is generated and the user is redirected to the game page.
    """
    room_code = _generate_room_code()
    return redirect(url_for("pages.game_room", room_code=room_code))


@DashboardAndRoom.route("/room/<room_code>")
@login_required
def game_room(room_code: str):
    """The game page. Real-time joining of the Room by Socket."""
    room_code = room_code.strip().upper()
    if not room_code.isalnum() or len(room_code) > 12:
        flash("کد Room نامعتبر است.", "danger")
        return redirect(url_for("pages.dashboard"))

    return render_template(
        "game.html",
        room_code=room_code,
        username=current_user.username,
    )


@DashboardAndRoom.route("/results/<int:game_id>")
@login_required
def results(game_id: int):
    """Final results page for a finished game.

    This page is shown after the game ends and includes:
        - The correct (reference) time
        - Each player's time and their guess
        - The difference between each guess and the real time
        - A ranked table for 1st, 2nd, 3rd, etc.
    """
    game = db.session.get(Game, game_id)
    if game is None:
        flash("بازی موردنظر یافت نشد.", "danger")
        return redirect(url_for("pages.dashboard"))

    records = (
        GamePlayer.query.filter_by(game_id=game.id)
        .join(User)
        .order_by(GamePlayer.guess_diff.asc().nullslast())
        .all()
    )

    # --- Build rows using the real values stored in the database ---
    rows = []
    for record in records:
        player = record.user
        rows.append(
            {
                "user_id": player.id,
                "username": player.username,
                "time": record.elapsed_time,
                "guess": record.guessed_time,
                "diff": record.guess_diff,
                "result": record.result,
                "is_me": player.id == current_user.id,
            }
        )

    # Reference (correct) time: the average of the real times recorded this round.
    real_times = [r["time"] for r in rows if r["time"] is not None]
    reference_time = (
        round(sum(real_times) / len(real_times), 3) if real_times else None
    )

    # Ranking: the winner first, then by the smallest actual difference.
    def _rank_key(row):
        if row["result"] == PlayerResult.WINNER.value:
            return (0, row["diff"] if row["diff"] is not None else float("inf"))
        if row["diff"] is None:
            return (2, float("inf"))
        return (1, row["diff"])

    rows.sort(key=_rank_key)
    for index, row in enumerate(rows):
        row["rank"] = index + 1

    best_diff = None
    diffs = [r["diff"] for r in rows if r["diff"] is not None]
    if diffs:
        best_diff = min(diffs)

    return render_template(
        "results.html",
        room_code=game.room_id,
        winner=game.winner.username if game.winner else None,
        finished_at=(
            game.finished_at.strftime("%Y-%m-%d %H:%M") if game.finished_at else None
        ),
        rows=rows,
        reference_time=reference_time,
        best_diff=best_diff,
    )
