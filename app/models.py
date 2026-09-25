"""
app/models.py — Database models for Count Time Game.

This file is responsible only for defining the data structures (tables)
and their relationships. No game logic or complex queries are written
here; that work happens in the routes and socket_on layers.

Why here? Per the requested architecture, all models are kept in a single
models.py so that navigation stays simple for a project of this size.

Models:
    - User       : user account and overall player stats
    - Game       : one game round in a Room
    - GamePlayer : each player's result in a game (association table)
"""

from datetime import datetime
from enum import Enum

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


class GameStatus(str, Enum):
    """Possible states of a game. Because it is a str, it is stored directly in the DB."""

    WAITING = "WAITING"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"


class PlayerResult(str, Enum):
    """Each player's result at the end of the game."""

    WINNER = "WINNER"
    LOSER = "LOSER"
    DISCONNECTED = "DISCONNECTED"
    NO_RESULT = "NO_RESULT"


class User(UserMixin, db.Model):
    """Player account.

    UserMixin provides the methods required by Flask-Login
    (is_authenticated, get_id, ...) so they don't need to be implemented
    manually.
    """

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    # --- Overall stats ---
    games_played = db.Column(db.Integer, nullable=False, default=0)
    wins = db.Column(db.Integer, nullable=False, default=0)
    losses = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # --- Relationships ---
    # A user can appear in many games and many GamePlayer records.
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

    # --- Password management ---
    def set_password(self, raw_password: str) -> None:
        """The password is never stored as plaintext; only as a hash."""
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        """Safely compare the entered password with the stored hash."""
        return check_password_hash(self.password_hash, raw_password)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.username}>"


class Game(db.Model):
    """One game round in a specific Room.

    room_id is the Room code (e.g. ABC123) and repeats across different
    rounds of the same Room; that is why it is not unique but is indexed.
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

    # --- Relationships ---
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
    """A player's result in a specific game.

    This association table links User and Game and stores the elapsed time
    and the result.
    """

    __tablename__ = "game_players"
    __table_args__ = (
        db.UniqueConstraint("game_id", "user_id", name="uq_game_user"),
    )

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    # Time computed on the server; may be empty until Stop is pressed.
    elapsed_time = db.Column(db.Float, nullable=True)
    # The player's guess of the elapsed time and its difference from the real time.
    guessed_time = db.Column(db.Float, nullable=True)
    guess_diff = db.Column(db.Float, nullable=True)
    result = db.Column(db.String(16), nullable=False, default=PlayerResult.NO_RESULT.value)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # --- Relationships ---
    game = db.relationship("Game", back_populates="players")
    user = db.relationship("User", back_populates="game_players")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<GamePlayer game={self.game_id} user={self.user_id} time={self.elapsed_time}>"
