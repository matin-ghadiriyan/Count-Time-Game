"""
app/__init__.py — Application Factory for the Count Time Game project.

Responsibilities of this file:
    - Create the Flask instance
    - Load settings from config.py
    - Initialize extensions (db, login_manager, socketio, csrf)
    - Register the page blueprints
    - Register Socket.IO events by importing the socket_on module
    - Create the database tables on first run

Why an Application Factory?
    This is the standard Flask pattern and lets the app instance be built
    with different settings for tests or different environments. It also
    avoids import cycles between app, models, and routes.

Initialization order matters:
    1) db, login_manager, and socketio are attached.
    2) Page blueprints are registered.
    3) The socket_on module is imported so events are registered.
    4) The database tables are created.
"""

from flask import Flask

from config import get_config
from .extensions import csrf, db, login_manager, socketio
from .models import User


def create_app(config_name: str | None = None) -> Flask:
    """Create and configure the Count Time Game application instance."""

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # --- Load settings ---
    app.config.from_object(get_config(config_name))

    # --- Initialize extensions ---
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # SocketIO starts with the async_mode specified in the settings.
    socketio.init_app(
        app,
        async_mode=app.config.get("SOCKETIO_ASYNC_MODE", "threading"),
        cors_allowed_origins="*",
        ping_timeout=app.config.get("SOCKETIO_PING_TIMEOUT", 30),
        ping_interval=app.config.get("SOCKETIO_PING_INTERVAL", 10),
    )

    # --- User loader for Flask-Login ---
    @login_manager.user_loader
    def load_user(user_id: str) -> User | None:
        return db.session.get(User, int(user_id))

    # --- Register page blueprints ---
    from .pages.routes import blueprints

    for bp in blueprints():
        app.register_blueprint(bp)

    # --- Register Socket.IO events ---
    # This import triggers the @socketio.on decorators.
    # It must run after socketio.init_app.
    from .pages.socket_on import (  # noqa: F401
        handle_connect,
        handle_disconnect,
        handle_join_room,
        handle_leave_room,
        handle_ping,
        handle_start_game,
        handle_stop_game,
        handle_submit_guess,
    )

    # --- Create database tables ---
    with app.app_context():
        db.create_all()

    return app
