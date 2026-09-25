"""
config.py — تنظیمات مرکزی پروژه Count Time Game

این فایل مسئول خواندن متغیرهای محیطی از .env و تبدیل آن‌ها به
کلاس‌های تنظیمات Flask است. هیچ منطق بازی اینجا نیست؛ فقط
پیکربندی (Secret Key، دیتابیس، ظرفیت Room و ...).

چرا این‌جا؟ چون Flask از الگوی «Config Objects» پشتیبانی می‌کند و
نگه‌داشتن تنظیمات در یک فایل، تست‌پذیری و تغییر محیط را ساده می‌کند.
"""

import os
from datetime import timedelta

from dotenv import load_dotenv

# خواندن فایل .env از ریشه‌ی پروژه
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


class Config:
    """تنظیمات پایه که در همه‌ی محیط‌ها مشترک است."""

    # --- امنیت ---
    SECRET_KEY = os.getenv("SECRET_KEY", "count-time-game-dev-secret")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    # --- دیتابیس ---
    # پیش‌فرض SQLite است؛ با تنظیم DATABASE_URL در .env می‌توان به MySQL سوییچ کرد.
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(BASE_DIR, 'count_time_game.db')}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    # --- تنظیمات بازی Count Time Game ---
    ROOM_CAPACITY = int(os.getenv("ROOM_CAPACITY", "8"))
    ROOM_CODE_LENGTH = 6
    # حداقل و حداکثر زمان مجاز برای ثبت نتیجه (ضد تقلب)
    MIN_VALID_TIME = 0.05
    MAX_VALID_TIME = 120.0

    # --- SocketIO ---
    SOCKETIO_ASYNC_MODE = os.getenv("SOCKETIO_ASYNC_MODE", "threading")
    SOCKETIO_PING_TIMEOUT = 30
    SOCKETIO_PING_INTERVAL = 10

    # --- عمومی ---
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


# نگاشت نام محیط به کلاس تنظیمات
config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}


def get_config(name: str | None = None) -> type[Config]:
    """دریافت کلاس تنظیمات بر اساس نام محیط (پیش‌فرض: development)."""
    env = (name or os.getenv("FLASK_ENV") or "development").lower()
    return config_by_name.get(env, DevelopmentConfig)
