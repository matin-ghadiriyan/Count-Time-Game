"""
app/models.py — مدل‌های دیتابیس Count Time Game

این فایل تنها مسئول تعریف ساختار داده‌ها (Tables) و روابط آن‌ها است.
هیچ منطق بازی یا کوئری پیچیده‌ای اینجا نوشته نمی‌شود؛ آن کار در لایه‌ی
routes و socket_on انجام می‌شود.

چرا این‌جا؟ طبق معماری درخواستی، همه‌ی مدل‌ها در یک فایل models.py
نگه‌داری می‌شوند تا برای پروژه‌ای با این اندازه، خوانایی و ناوبری ساده بماند.

مدل‌ها:
    - User       : حساب کاربری و آمار کلی بازیکن
    - Game       : یک راند بازی در یک Room
    - GamePlayer : نتیجه‌ی هر بازیکن در یک بازی (جدول واسط)
"""

from datetime import datetime
from enum import Enum

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


class GameStatus(str, Enum):
    """وضعیت‌های ممکن یک بازی. چون str است، مستقیماً در دیتابیس ذخیره می‌شود."""

    WAITING = "WAITING"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"


class PlayerResult(str, Enum):
    """نتیجه‌ی هر بازیکن در پایان بازی."""

    WINNER = "WINNER"
    LOSER = "LOSER"
    DISCONNECTED = "DISCONNECTED"
    NO_RESULT = "NO_RESULT"


class User(UserMixin, db.Model):
    """حساب کاربری بازیکن.

    UserMixin متدهای موردنیاز Flask-Login (is_authenticated, get_id و ...)
    را فراهم می‌کند تا نیازی به پیاده‌سازی دستی نباشد.
    """

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    # --- آمار کلی ---
    games_played = db.Column(db.Integer, nullable=False, default=0)
    wins = db.Column(db.Integer, nullable=False, default=0)
    losses = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # --- روابط ---
    # یک کاربر می‌تواند در چندین بازی و چندین رکورد GamePlayer حاضر باشد.
    game_players = db.relationship(
        "GamePlayer",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    won_games = db.relationship(
        "Game",
        back_populates="winner",
        foreign_keys="Game.winner_id",
        lazy="selectin",
    )

    # --- مدیریت رمز عبور ---
    def set_password(self, raw_password: str) -> None:
        """رمز عبور هرگز به‌صورت plaintext ذخیره نمی‌شود؛ فقط hash."""
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        """مقایسه‌ی امن رمز ورودی با hash ذخیره‌شده."""
        return check_password_hash(self.password_hash, raw_password)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.username}>"


class Game(db.Model):
    """یک راند بازی در یک Room مشخص.

    room_id همان کد Room است (مثلاً ABC123) و بین راندهای مختلف یک Room
    تکرار می‌شود؛ به همین دلیل unique نیست ولی index دارد.
    """

    __tablename__ = "games"

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.String(12), nullable=False, index=True)
    status = db.Column(
        db.String(16), nullable=False, default=GameStatus.WAITING.value
    )

    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    winner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    # --- روابط ---
    winner = db.relationship(
        "User", back_populates="won_games", foreign_keys=[winner_id]
    )
    players = db.relationship(
        "GamePlayer",
        back_populates="game",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Game #{self.id} room={self.room_id} status={self.status}>"


class GamePlayer(db.Model):
    """نتیجه‌ی یک بازیکن در یک بازی خاص.

    این جدول واسط بین User و Game است و زمان سپری‌شده و نتیجه را نگه می‌دارد.
    """

    __tablename__ = "game_players"
    __table_args__ = (
        db.UniqueConstraint("game_id", "user_id", name="uq_game_user"),
    )

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    # زمان محاسبه‌شده در سرور؛ می‌تواند تا لحظه‌ی Stop خالی باشد.
    elapsed_time = db.Column(db.Float, nullable=True)
    result = db.Column(db.String(16), nullable=False, default=PlayerResult.NO_RESULT.value)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # --- روابط ---
    game = db.relationship("Game", back_populates="players")
    user = db.relationship("User", back_populates="game_players")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<GamePlayer game={self.game_id} user={self.user_id} time={self.elapsed_time}>"
