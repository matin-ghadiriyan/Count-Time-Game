"""
app/pages/socket_on/__init__.py — Socket event registration.

Responsibilities of this file:
    - Define and register all SocketIO events
    - Basic input validation and access checks
    - Delegate the core logic to room_manager and the database layer
    - Emit events only to members of the same Room

Why here? Per the requested architecture, real-time game events live in
app/pages/socket_on and are separate from the HTTP routes.

Design pattern:
    Socket handler = thin layer
    RoomManager    = source of truth for game state
    Database       = stores the final result

This separation keeps the game logic testable and leaves the handlers
responsible only for real-time communication.
"""

from datetime import datetime

from flask import current_app, request, session
from flask_login import current_user
from flask_socketio import emit, join_room, leave_room

from ...extensions import db, socketio
from ...models import (
    Game,
    GamePlayer,
    GameStatus,
    PlayerResult,
    User,
)
from .room_manager import RoomManager, RoomState, room_manager


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _current_user_or_none() -> User | None:
    """Get the authenticated user inside the socket context.

    Flask-Login works with current_user in SocketIO as long as the session
    cookie is sent. To be safe, the user_id is also read from the session.
    """
    if current_user and current_user.is_authenticated:
        return current_user
    user_id = session.get("_user_id")
    if user_id:
        return db.session.get(User, int(user_id))
    return None


def _error(message: str, event: str = "error") -> None:
    """Send a standard error only to that client."""
    emit(event, {"ok": False, "message": message})


def _room_payload(room) -> dict:
    """Build the shared payload for Room-related events."""
    return {
        "room_code": room.code,
        "state": room.state,
        "host_id": room.host_id,
        "capacity": room.capacity,
        "players": room.public_players(),
        "player_count": len(room.players),
    }


def _broadcast_room_state(room) -> None:
    """Send the updated Room state to all members."""
    socketio.emit("room_state", _room_payload(room), to=room.code)


# ------------------------------------------------------------------
# Connect and disconnect
# ------------------------------------------------------------------
@socketio.on("connect")
def handle_connect():
    """Initial socket connection.

    The user must be authenticated; otherwise the connection is rejected
    to prevent guests from emitting events.
    """
    user = _current_user_or_none()
    if user is None:
        return False  # connection rejected
    emit("connected", {"ok": True, "username": user.username})


@socketio.on("disconnect")
def handle_disconnect():
    """Handle a player disconnecting.

    If a player drops mid-game, their state is marked as disconnected and
    the other Room members are notified. The player is not fully removed so
    that a reconnect can preserve their previous result.
    """
    sid = request.sid
    room = room_manager.find_room_by_sid(sid)
    if room is None:
        return

    player = next(
        (p for p in room.players.values() if p.sid == sid), None
    )
    if player is None:
        return

    room_manager.mark_disconnected(room.code, player.user_id)

    # Notify the other Room members
    socketio.emit(
        "player_disconnected",
        {"user_id": player.user_id, "username": player.username},
        to=room.code,
    )
    _broadcast_room_state(room)

    # If the disconnected player held the turn, advance it so the game doesn't lock up.
    if room.state == RoomState.RUNNING and room.current_player_id() == player.user_id:
        next_id, all_done = room_manager.advance_turn(room.code)
        socketio.emit(
            "turn_changed",
            {
                "current_player_id": next_id,
                "all_done": all_done,
                "room_code": room.code,
            },
            to=room.code,
        )
        if all_done:
            _finalize_game(room)

    # If the Room no longer has connected players, remove it.
    if all(not p.connected for p in room.players.values()):
        room_manager.remove_room(room.code)


# ------------------------------------------------------------------
# Joining a Room
# ------------------------------------------------------------------
@socketio.on("join_room")
def handle_join_room(data):
    """Join a user to a Room and bind the SID to the SocketIO room.

    Validation:
        - The user must be authenticated
        - The Room code must be valid
        - The Room must not be full
        - The game must not be running
    """
    user = _current_user_or_none()
    if user is None:
        return _error("ابتدا وارد حساب کاربری شوید.")

    if not isinstance(data, dict):
        return _error("داده‌ی ورودی نامعتبر است.")

    room_code = str(data.get("room_code", "")).strip().upper()
    if not room_code or not room_code.isalnum() or len(room_code) > 12:
        return _error("کد Room نامعتبر است.")

    capacity = current_app.config.get("ROOM_CAPACITY", 8)
    room, error = room_manager.join(
        code=room_code,
        user_id=user.id,
        username=user.username,
        sid=request.sid,
        capacity=capacity,
    )
    if error or room is None:
        return _error(error or "ورود به Room ممکن نشد.")

    join_room(room.code)

    emit("joined_room", {"ok": True, **_room_payload(room)})
    _broadcast_room_state(room)


@socketio.on("leave_room")
def handle_leave_room(data):
    """Remove a user from a Room."""
    user = _current_user_or_none()
    if user is None:
        return _error("ابتدا وارد حساب کاربری شوید.")

    room_code = str((data or {}).get("room_code", "")).strip().upper()
    room = room_manager.get_room(room_code)
    if room is None:
        return _error("Room یافت نشد.")

    leave_room(room.code)
    updated = room_manager.leave(room.code, user.id)

    if updated is not None:
        socketio.emit(
            "player_left",
            {"user_id": user.id, "username": user.username},
            to=updated.code,
        )
        _broadcast_room_state(updated)

    emit("left_room", {"ok": True, "room_code": room_code})


# ------------------------------------------------------------------
# Starting and stopping the game
# ------------------------------------------------------------------
@socketio.on("start_game")
def handle_start_game(data):
    """Start the game, initiated by the host.

    This event serves two purposes:
        1. If the Room is in WAITING, the host can start the game so every
           player enters the RUNNING phase.
        2. Each player's start time is recorded by the server the moment
           that player presses their own Start button.

    The two modes are distinguished by the action field:
        action = "begin"  -> start the whole game (host)
        action = "self"   -> record an individual start time (default)
    """
    user = _current_user_or_none()
    if user is None:
        return _error("ابتدا وارد حساب کاربری شوید.")

    if not isinstance(data, dict):
        return _error("داده‌ی ورودی نامعتبر است.")

    room_code = str(data.get("room_code", "")).strip().upper()
    action = str(data.get("action", "self")).lower()

    room = room_manager.get_room(room_code)
    if room is None:
        return _error("Room یافت نشد.")
    if user.id not in room.players:
        return _error("شما عضو این Room نیستید.")

    # --- Mode 1: start the whole game (host) ---
    if action == "begin":
        if room.host_id != user.id:
            return _error("فقط میزبان می‌تواند بازی را شروع کند.")
        if room.state != RoomState.WAITING:
            return _error("بازی قبلاً شروع شده است.")
        if len([p for p in room.players.values() if p.connected]) < 1:
            return _error("حداقل یک بازیکن متصل لازم است.")

        room.state = RoomState.RUNNING
        # Build the turn order from the connected players
        room.build_turn_order()
        started_at = datetime.utcnow()

        # Create a Game record in the database
        game = Game(
            room_id=room.code,
            status=GameStatus.RUNNING.value,
            started_at=started_at,
        )
        db.session.add(game)
        db.session.flush()  # get the id before commit

        room.game_db_id = game.id
        for player in room.players.values():
            db.session.add(
                GamePlayer(game_id=game.id, user_id=player.user_id)
            )
        db.session.commit()

        socketio.emit(
            "game_started",
            {"room_code": room.code, "game_id": game.id},
            to=room.code,
        )
        _broadcast_room_state(room)
        return

    # --- Mode 2: record an individual start time ---
    if room.state != RoomState.RUNNING:
        return _error("بازی هنوز شروع نشده است.")

    start_time, error = room_manager.start_player(room.code, user.id)
    if error:
        return _error(error)

    emit("player_started", {"ok": True, "user_id": user.id})
    _broadcast_room_state(room)


@socketio.on("stop_game")
def handle_stop_game(data):
    """Stop the timer for a player.

    The elapsed time is computed only on the server with time.perf_counter;
    the client never sends any time value.
    """
    user = _current_user_or_none()
    if user is None:
        return _error("ابتدا وارد حساب کاربری شوید.")

    if not isinstance(data, dict):
        return _error("داده‌ی ورودی نامعتبر است.")

    room_code = str(data.get("room_code", "")).strip().upper()
    room = room_manager.get_room(room_code)
    if room is None:
        return _error("Room یافت نشد.")
    if user.id not in room.players:
        return _error("شما عضو این Room نیستید.")

    elapsed, error = room_manager.stop_player(room.code, user.id)
    if error:
        return _error(error)

    # The elapsed time is not shown to the player themselves; only the
    # opponents see it, forcing the player to guess the time.
    emit(
        "player_stopped",
        {
            "ok": True,
            "user_id": user.id,
            "username": user.username,
            "elapsed_time": None,
        },
    )
    # Notify the opponents along with the real elapsed time
    socketio.emit(
        "opponent_elapsed",
        {
            "user_id": user.id,
            "username": user.username,
            "elapsed_time": elapsed,
        },
        to=room.code,
        skip_sid=request.sid,
    )
    _broadcast_room_state(room)
    return


@socketio.on("submit_guess")
def handle_submit_guess(data):
    """Record a player's time guess after stopping.

    After pressing Stop, the player guesses the elapsed seconds in an
    input. The difference between the guess and the real time is computed
    and stored on the server; the winner is the one with the smallest
    difference.
    """
    user = _current_user_or_none()
    if user is None:
        return _error("ابتدا وارد حساب کاربری شوید.")

    if not isinstance(data, dict):
        return _error("داده‌ی ورودی نامعتبر است.")

    room_code = str(data.get("room_code", "")).strip().upper()
    room = room_manager.get_room(room_code)
    if room is None:
        return _error("Room یافت نشد.")
    if user.id not in room.players:
        return _error("شما عضو این Room نیستید.")

    raw_guess = data.get("guessed_time")
    try:
        guessed_time = float(raw_guess)
    except (TypeError, ValueError):
        return _error("مقدار حدس نامعتبر است.")

    guess_diff, error = room_manager.submit_guess(
        room.code, user.id, guessed_time
    )
    if error:
        return _error(error)

    # Send this player's guess result back to them
    emit(
        "player_guessed",
        {
            "ok": True,
            "user_id": user.id,
            "username": user.username,
            "guess_diff": guess_diff,
        },
    )

    # Advance the turn to the next player
    next_id, all_done = room_manager.advance_turn(room.code)
    socketio.emit(
        "turn_changed",
        {"current_player_id": next_id, "all_done": all_done, "room_code": room.code},
        to=room.code,
    )
    _broadcast_room_state(room)

    # If all turns are done, finalize the game.
    if all_done:
        _finalize_game(room)


# ------------------------------------------------------------------
# Game finalization
# ------------------------------------------------------------------
def _finalize_game(room) -> None:
    """End the game: determine the winner, save to DB, update stats, emit result.

    This function is only called from inside the handlers and relies on the
    logical lock on the Room (RoomManager keeps operations atomic).
    """
    if room.state == RoomState.FINISHED:
        return

    room.state = RoomState.FINISHED

    winner_id, results = room_manager.determine_winner(room)
    finished_at = datetime.utcnow()

    game = db.session.get(Game, room.game_db_id) if room.game_db_id else None
    winner_username = None

    if game is not None:
        game.status = GameStatus.FINISHED.value
        game.finished_at = finished_at

        # --- Update player records and User stats ---
        for player in room.players.values():
            record = GamePlayer.query.filter_by(
                game_id=game.id, user_id=player.user_id
            ).first()
            if record is None:
                continue

            if player.has_stopped and player.elapsed_time is not None:
                record.elapsed_time = player.elapsed_time
            if player.has_guessed:
                record.guessed_time = player.guessed_time
                record.guess_diff = player.guess_diff

            user_obj = db.session.get(User, player.user_id)

            if not player.connected and not player.has_stopped:
                record.result = PlayerResult.DISCONNECTED.value
            elif player.user_id == winner_id:
                record.result = PlayerResult.WINNER.value
                if user_obj:
                    user_obj.wins += 1
                    winner_username = user_obj.username
            elif player.has_stopped:
                record.result = PlayerResult.LOSER.value
                if user_obj:
                    user_obj.losses += 1
            else:
                record.result = PlayerResult.NO_RESULT.value

            # Only players who took part in the round get a games_played stat.
            if user_obj and player.has_stopped:
                user_obj.games_played += 1

        if winner_id is not None:
            game.winner_id = winner_id
            if winner_username is None:
                winner_user = db.session.get(User, winner_id)
                winner_username = winner_user.username if winner_user else None

        db.session.commit()

    # --- Send the result to the Room members ---
    payload = {
        "room_code": room.code,
        "game_id": room.game_db_id,
        "winner_id": winner_id,
        "winner": winner_username,
        "results": results,
        "finished_at": finished_at.isoformat(),
    }
    socketio.emit("game_finished", payload, to=room.code)
    _broadcast_room_state(room)


# ------------------------------------------------------------------
# Lightweight ping to check connection health
# ------------------------------------------------------------------
@socketio.on("ping_game")
def handle_ping(data):
    """Quick reply to the client to confirm the connection is alive."""
    emit("pong_game", {"ok": True})
