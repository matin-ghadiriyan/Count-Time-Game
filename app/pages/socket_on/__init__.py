"""
app/pages/socket_on/__init__.py — ثبت Socket Eventها

مسئولیت این فایل:
    - تعریف و ثبت تمام SocketIO Eventها
    - اعتبارسنجی اولیه‌ی ورودی و بررسی دسترسی
    - واگذاری منطق اصلی به room_manager و لایه‌ی دیتابیس
    - ارسال Event به اعضای همان Room

چرا این‌جا؟ طبق معماری درخواستی، Eventهای Real-Time بازی داخل
app/pages/socket_on قرار می‌گیرند و از Routeهای HTTP جدا هستند.

الگوی طراحی:
    Socket Handler = لایه‌ی نازک (thin layer)
    RoomManager   = منبع حقیقت وضعیت بازی (game state)
    Database      = ذخیره‌ی نتیجه‌ی نهایی

این جداسازی باعث می‌شود منطق بازی قابل تست باشد و Handlerها فقط
مسئول ارتباط Real-Time باشند.
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
# ابزارهای کمکی
# ------------------------------------------------------------------
def _current_user_or_none() -> User | None:
    """دریافت کاربر احراز هویت‌شده در Context سوکت.

    Flask-Login در SocketIO با current_user کار می‌کند به شرطی که Session
    کوکی ارسال شده باشد. برای اطمینان، user_id را از session نیز می‌خوانیم.
    """
    if current_user and current_user.is_authenticated:
        return current_user
    user_id = session.get("_user_id")
    if user_id:
        return db.session.get(User, int(user_id))
    return None


def _error(message: str, event: str = "error") -> None:
    """ارسال خطای استاندارد فقط به همان Client."""
    emit(event, {"ok": False, "message": message})


def _room_payload(room) -> dict:
    """ساخت بدنه‌ی مشترک برای رویدادهای مربوط به Room."""
    return {
        "room_code": room.code,
        "state": room.state,
        "host_id": room.host_id,
        "capacity": room.capacity,
        "players": room.public_players(),
        "player_count": len(room.players),
    }


def _broadcast_room_state(room) -> None:
    """ارسال وضعیت به‌روز Room به همه‌ی اعضا."""
    socketio.emit("room_state", _room_payload(room), to=room.code)


# ------------------------------------------------------------------
# اتصال و قطع اتصال
# ------------------------------------------------------------------
@socketio.on("connect")
def handle_connect():
    """اتصال اولیه‌ی سوکت.

    کاربر باید احراز هویت شده باشد؛ در غیر این صورت اتصال رد می‌شود تا
    از ارسال Event توسط مهمان‌ها جلوگیری شود.
    """
    user = _current_user_or_none()
    if user is None:
        return False  # اتصال رد می‌شود
    emit("connected", {"ok": True, "username": user.username})


@socketio.on("disconnect")
def handle_disconnect():
    """مدیریت قطع اتصال بازیکن.

    اگر بازیکن وسط بازی قطع شود، وضعیتش به‌عنوان disconnected علامت می‌خورد
    و سایر اعضای Room مطلع می‌شوند. حذف کامل بازیکن انجام نمی‌شود تا اگر
    دوباره وصل شد، بتواند نتیجه‌ی قبلی‌اش را حفظ کند.
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

    # اطلاع‌رسانی به سایر اعضای Room
    socketio.emit(
        "player_disconnected",
        {"user_id": player.user_id, "username": player.username},
        to=room.code,
    )
    _broadcast_room_state(room)

    # اگر بازیکنِ قطع‌شده نوبت‌دار بود، نوبت را جلو می‌بریم تا بازی قفل نشود.
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

    # اگر Room دیگر بازیکن متصل ندارد، پاک شود.
    if all(not p.connected for p in room.players.values()):
        room_manager.remove_room(room.code)


# ------------------------------------------------------------------
# عضویت در Room
# ------------------------------------------------------------------
@socketio.on("join_room")
def handle_join_room(data):
    """ورود کاربر به Room و اتصال SID به اتاق SocketIO.

    اعتبارسنجی:
        - کاربر احراز هویت شده باشد
        - کد Room معتبر باشد
        - ظرفیت Room پر نباشد
        - بازی در حال اجرا نباشد
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
    """خروج کاربر از Room."""
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
# شروع و توقف بازی
# ------------------------------------------------------------------
@socketio.on("start_game")
def handle_start_game(data):
    """شروع بازی توسط میزبان.

    این Event دو کاربرد دارد:
        1. اگر Room در حالت WAITING باشد، میزبان می‌تواند بازی را استارت بزند
           تا همه‌ی بازیکنان وارد فاز RUNNING شوند.
        2. زمان شروع هر بازیکن از لحظه‌ای که خودش دکمه‌ی Start را می‌زند
           توسط سرور ثبت می‌شود.

    تفکیک این دو حالت با فیلد action انجام می‌شود:
        action = "begin"  → شروع کل بازی توسط میزبان
        action = "self"   → ثبت زمان شروع فردی (پیش‌فرض)
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

    # --- حالت ۱: شروع کل بازی توسط میزبان ---
    if action == "begin":
        if room.host_id != user.id:
            return _error("فقط میزبان می‌تواند بازی را شروع کند.")
        if room.state != RoomState.WAITING:
            return _error("بازی قبلاً شروع شده است.")
        if len([p for p in room.players.values() if p.connected]) < 1:
            return _error("حداقل یک بازیکن متصل لازم است.")

        room.state = RoomState.RUNNING
        # ساخت ترتیب نوبت‌ها بر اساس بازیکنان متصل
        room.build_turn_order()
        started_at = datetime.utcnow()

        # ثبت یک رکورد Game در دیتابیس
        game = Game(
            room_id=room.code,
            status=GameStatus.RUNNING.value,
            started_at=started_at,
        )
        db.session.add(game)
        db.session.flush()  # برای گرفتن id قبل از commit

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

    # --- حالت ۲: ثبت زمان شروع فردی ---
    if room.state != RoomState.RUNNING:
        return _error("بازی هنوز شروع نشده است.")

    start_time, error = room_manager.start_player(room.code, user.id)
    if error:
        return _error(error)

    emit("player_started", {"ok": True, "user_id": user.id})
    _broadcast_room_state(room)


@socketio.on("stop_game")
def handle_stop_game(data):
    """توقف زمان توسط بازیکن.

    زمان سپری‌شده فقط در سرور و با time.perf_counter محاسبه می‌شود؛
    Client هیچ مقداری برای زمان ارسال نمی‌کند.
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

    # زمان سپری‌شده به خودِ بازیکن نشان داده نمی‌شود؛ فقط حریفان آن را
    # می‌بینند تا بازیکن مجبور شود زمان را حدس بزند.
    emit(
        "player_stopped",
        {
            "ok": True,
            "user_id": user.id,
            "username": user.username,
            "elapsed_time": None,
        },
    )
    # اطلاع‌رسانی به حریفان همراه با نمایش زمان واقعی
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
    """ثبت حدس زمان بازیکن پس از توقف.

    بازیکن بعد از زدن دکمه‌ی Stop، در یک اینپوت تعداد ثانیه‌های سپری‌شده
    را حدس می‌زند. اختلاف حدس با زمان واقعی در سرور محاسبه و ذخیره
    می‌شود؛ برنده کسی است که کمترین اختلاف را داشته باشد.
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

    # ارسال نتیجه‌ی حدس همین بازیکن به خودش
    emit(
        "player_guessed",
        {
            "ok": True,
            "user_id": user.id,
            "username": user.username,
            "guess_diff": guess_diff,
        },
    )

    # انتقال نوبت به بازیکن بعدی
    next_id, all_done = room_manager.advance_turn(room.code)
    socketio.emit(
        "turn_changed",
        {"current_player_id": next_id, "all_done": all_done, "room_code": room.code},
        to=room.code,
    )
    _broadcast_room_state(room)

    # اگر همه‌ی نوبت‌ها تمام شد، بازی نهایی شود.
    if all_done:
        _finalize_game(room)


# ------------------------------------------------------------------
# نهایی‌سازی بازی
# ------------------------------------------------------------------
def _finalize_game(room) -> None:
    """پایان بازی: تعیین برنده، ذخیره در DB، به‌روزرسانی آمار و ارسال نتیجه.

    این تابع فقط از داخل Handlerها صدا زده می‌شود و به‌صورت داخلی روی
    Room قفل منطقی دارد (RoomManager عملیات را اتمی نگه می‌دارد).
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

        # --- به‌روزرسانی رکورد بازیکنان و آمار Userها ---
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

            # فقط بازیکنانی که در راند شرکت کرده‌اند آمار games_played می‌گیرند.
            if user_obj and player.has_stopped:
                user_obj.games_played += 1

        if winner_id is not None:
            game.winner_id = winner_id
            if winner_username is None:
                winner_user = db.session.get(User, winner_id)
                winner_username = winner_user.username if winner_user else None

        db.session.commit()

    # --- ارسال نتیجه به اعضای Room ---
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
# پینگ سبک برای بررسی سلامت اتصال
# ------------------------------------------------------------------
@socketio.on("ping_game")
def handle_ping(data):
    """پاسخ سریع به Client برای اطمینان از زنده‌بودن اتصال."""
    emit("pong_game", {"ok": True})
