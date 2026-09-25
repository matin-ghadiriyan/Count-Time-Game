"""
app/pages/routes/__init__.py — مسیرهای HTTP (Blueprint صفحات)

مسئولیت این فایل:
    - احراز هویت (ثبت‌نام / ورود / خروج)
    - ساخت Room و ورود به Room (صفحات)
    - نمایش Leaderboard و History
    - API سبک برای خواندن اطلاعات اتاق

منطق بازی و زمان‌سنجی اینجا نیست؛ فقط نمایش صفحه و اعتبارسنجی ورودی.
دلیل قرارگیری در این فایل: طبق معماری درخواستی، تمامی Routeهای مربوط به
صفحات داخل app/pages/routes قرار می‌گیرند.
"""

import random
import string

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from ...extensions import db
from ...models import Game, GamePlayer, PlayerResult, User

bp = Blueprint("pages", __name__)


def _generate_room_code(length: int = 6) -> str:
    """ساخت کد تصادفی Room با حروف بزرگ و اعداد (بدون کاراکترهای گیج‌کننده)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(random.choices(alphabet, k=length))


# ----------------------------------------------------------------
# احراز هویت
# ----------------------------------------------------------------
@bp.route("/")
def index():
    """صفحه‌ی اصلی: اگر کاربر وارد شده باشد به داشبورد می‌رود، وگرنه Landing."""
    if current_user.is_authenticated:
        return redirect(url_for("pages.dashboard"))
    return render_template("index.html")


@bp.route("/register", methods=["GET", "POST"])
def register():
    """ثبت‌نام کاربر جدید. رمز عبور فقط به‌صورت hash ذخیره می‌شود."""
    if current_user.is_authenticated:
        return redirect(url_for("pages.dashboard"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm_password") or ""

        # --- اعتبارسنجی ورودی ---
        if not (3 <= len(username) <= 32):
            flash("نام کاربری باید بین ۳ تا ۳۲ کاراکتر باشد.", "danger")
        elif not username.isalnum():
            flash("نام کاربری فقط می‌تواند شامل حروف و اعداد باشد.", "danger")
        elif len(password) < 6:
            flash("رمز عبور باید حداقل ۶ کاراکتر باشد.", "danger")
        elif password != confirm:
            flash("تکرار رمز عبور مطابقت ندارد.", "danger")
        elif User.query.filter_by(username=username).first() is not None:
            flash("این نام کاربری قبلاً ثبت شده است.", "danger")
        else:
            user = User(username=username)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("حساب کاربری با موفقیت ساخته شد. خوش آمدید!", "success")
            return redirect(url_for("pages.dashboard"))

    return render_template("register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    """ورود کاربر. پس از ورود، به داشبورد هدایت می‌شود."""
    if current_user.is_authenticated:
        return redirect(url_for("pages.dashboard"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        user = User.query.filter_by(username=username).first()
        if user is None or not user.check_password(password):
            flash("نام کاربری یا رمز عبور اشتباه است.", "danger")
        else:
            login_user(user, remember=True)
            flash("خوش آمدید!", "success")
            return redirect(url_for("pages.dashboard"))

    return render_template("login.html")


@bp.route("/logout")
@login_required
def logout():
    """خروج از حساب کاربری."""
    logout_user()
    flash("با موفقیت خارج شدید.", "info")
    return redirect(url_for("pages.index"))


# ----------------------------------------------------------------
# داشبورد و Room
# ----------------------------------------------------------------
@bp.route("/dashboard")
@login_required
def dashboard():
    """داشبورد اصلی: فرم ساخت/ورود به Room و خلاصه‌ی آمار کاربر."""
    return render_template("dashboard.html")


@bp.route("/create-room", methods=["POST"])
@login_required
def create_room():
    """ساخت یک کد Room جدید و هدایت کاربر به صفحه‌ی بازی همان Room.

    نکته: خودِ Room در حافظه‌ی سرور ساخته می‌شود (socket_on/room_manager).
    اینجا فقط کد تولید و کاربر به صفحه‌ی بازی هدایت می‌شود.
    """
    room_code = _generate_room_code()
    return redirect(url_for("pages.game_room", room_code=room_code))


@bp.route("/room/<room_code>")
@login_required
def game_room(room_code: str):
    """صفحه‌ی بازی. اعتبارسنجی نهایی عضویت در Room هنگام اتصال Socket انجام می‌شود."""
    room_code = room_code.strip().upper()
    if not room_code.isalnum() or len(room_code) > 12:
        flash("کد Room نامعتبر است.", "danger")
        return redirect(url_for("pages.dashboard"))

    return render_template(
        "game.html",
        room_code=room_code,
        username=current_user.username,
    )


# ----------------------------------------------------------------
# Leaderboard و History
# ----------------------------------------------------------------
@bp.route("/leaderboard")
def leaderboard():
    """جدول بازیکنان برتر بر اساس تعداد برد و نسبت برد."""
    users = (
        User.query.filter(User.games_played > 0)
        .order_by(User.wins.desc(), User.games_played.asc())
        .limit(50)
        .all()
    )
    return render_template("leaderboard.html", users=users)


@bp.route("/history")
@login_required
def history():
    """تاریخچه‌ی بازی‌های کاربر فعلی."""
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


# ----------------------------------------------------------------
# API سبک (اختیاری برای نمودار/آمار)
# ----------------------------------------------------------------
@bp.route("/api/leaderboard")
def api_leaderboard():
    """نسخه‌ی JSON جدول امتیازات برای مصرف احتمالی در فرانت."""
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
