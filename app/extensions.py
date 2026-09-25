"""
app/extensions.py — Global extension instances.

This file is only responsible for instantiating the extensions, not for
initializing them. Initialization happens in app/__init__.py via
init_app. This separation lets models and modules access db without
creating circular imports.

Why here? In Flask projects, extensions.py is the standard pattern to
avoid circular imports between app, models, and routes.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_socketio import SocketIO
from flask_wtf.csrf import CSRFProtect

# --- Database ORM ---
db = SQLAlchemy()

# --- Authentication ---
login_manager = LoginManager()
login_manager.login_view = "pages.login"
login_manager.login_message = "برای ادامه باید وارد حساب کاربری خود شوید."
login_manager.login_message_category = "warning"

# --- Real-time (Flask-SocketIO) ---
# async_mode defaults to threading so it can run without eventlet.
socketio = SocketIO(
    cors_allowed_origins="*",
    async_mode="threading",
    ping_timeout=30,
    ping_interval=10,
    logger=False,
    engineio_logger=False,
)

# --- CSRF protection for forms ---
csrf = CSRFProtect()
