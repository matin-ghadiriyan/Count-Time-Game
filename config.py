"""
config.py — Central configuration for the Count Time Game project.

This file reads environment variables from .env and turns them into
Flask config classes. No game logic lives here; only configuration
(secret key, database, room capacity, ...).

Why here? Flask supports the "Config Objects" pattern, and keeping the
settings in one file makes testing and switching environments easier.
"""

import os
from datetime import timedelta

from dotenv import load_dotenv

# Read the .env file from the project root
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


class Config:
    """Base settings shared by all environments."""

    # --- Security ---
    SECRET_KEY = os.getenv("SECRET_KEY", "count-time-game-dev-secret")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    # --- Database ---
    # SQLite is the default; set DATABASE_URL in .env to switch to MySQL.
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(BASE_DIR, 'count_time_game.db')}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    # --- Count Time Game settings ---
    ROOM_CAPACITY = int(os.getenv("ROOM_CAPACITY", "8"))
    ROOM_CODE_LENGTH = 6
    # Minimum and maximum allowed time for a result (anti-cheat)
    MIN_VALID_TIME = 0.05
    MAX_VALID_TIME = 120.0

    # --- SocketIO ---
    SOCKETIO_ASYNC_MODE = os.getenv("SOCKETIO_ASYNC_MODE", "threading")
    SOCKETIO_PING_TIMEOUT = 30
    SOCKETIO_PING_INTERVAL = 10

    # --- General ---
    APP_NAME = "Count Time Game"
    JSON_SORT_KEYS = False


class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True


class TestingConfig(Config):
    DEBUG = False
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


# Map of environment name to config class
config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}


def get_config(name: str | None = None) -> type[Config]:
    """Get the config class by environment name (default: development)."""
    env = (name or os.getenv("FLASK_ENV") or "development").lower()
    return config_by_name.get(env, DevelopmentConfig)
