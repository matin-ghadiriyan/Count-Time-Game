"""
app/__init__.py — Application Factory پروژه Count Time Game

مسئولیت این فایل:
    - ساخت نمونه‌ی Flask
    - بارگذاری تنظیمات از config.py
    - مقداردهی اولیه‌ی Extensionها (db، login_manager، socketio، csrf)
    - ثبت Blueprint صفحات
    - ثبت Socket Eventها با import ماژول socket_on
    - ساخت جداول دیتابیس در اولین اجرا و ایجاد جدول‌های لازم

چرا Application Factory؟
    این الگو در Flask استاندارد است و اجازه می‌دهد نمونه‌ی اپ در تست‌ها
    یا محیط‌های مختلف با تنظیمات متفاوت ساخته شود. همچنین از ایجاد
    چرخه‌ی import بین app، models و routes جلوگیری می‌کند.

ترتیب مقداردهی مهم است:
    1) db و login_manager و socketio متصل شوند.
    2) Blueprint صفحات ثبت شود.
    3) ماژول socket_on import شود تا Eventها ثبت شوند.
    4) جداول دیتابیس ساخته شوند.
"""

from flask import Flask

from config import get_config
from .extensions import csrf, db, login_manager, socketio
from .models import User


def create_app(config_name: str | None = None) -> Flask:
    """ساخت و پیکربندی نمونه‌ی اپلیکیشن Count Time Game."""

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # --- بارگذاری تنظیمات ---
    app.config.from_object(get_config(config_name))

    # --- مقداردهی Extensionها ---
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # SocketIO با async_mode مشخص‌شده در تنظیمات راه‌اندازی می‌شود.
    socketio.init_app(
        app,
        async_mode=app.config.get("SOCKETIO_ASYNC_MODE", "threading"),
        cors_allowed_origins="*",
        ping_timeout=app.config.get("SOCKETIO_PING_TIMEOUT", 30),
        ping_interval=app.config.get("SOCKETIO_PING_INTERVAL", 10),
    )

    # --- User Loader برای Flask-Login ---
    @login_manager.user_loader
    def load_user(user_id: str) -> User | None:
        return db.session.get(User, int(user_id))

    # --- ثبت Blueprint صفحات ---
    from .pages.routes import bp as pages_bp

    app.register_blueprint(pages_bp)

    # --- ثبت Socket Eventها ---
    # این import باعث اجرای decoratorهای @socketio.on می‌شود.
    # مهم است که بعد از socketio.init_app انجام شود.
    from .pages.socket_on import (  # noqa: F401
        handle_connect,
        handle_disconnect,
        handle_join_room,
        handle_leave_room,
        handle_ping,
        handle_start_game,
        handle_stop_game,
    )

    # --- CSRF برای SocketIO غیرفعال می‌شود ---
    # SocketIO از CSRF Token پشتیبانی نمی‌کند؛ امنیت سوکت با بررسی
    # احراز هویت و عضویت در Room تضمین می‌شود.
    csrf.exempt(pages_bp)

    # --- ساخت جداول دیتابیس ---
    with app.app_context():
        db.create_all()

    return app
