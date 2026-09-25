"""
app/extensions.py — نمونه‌های سراسری Extensionها

مسئولیت این فایل فقط ساختن (instantiate) کردن Extensionها است، نه
مقداردهی اولیه. مقداردهی اولیه در app/__init__.py و با init_app انجام
می‌شود. این جداسازی باعث می‌شود مدل‌ها و ماژول‌ها بتوانند بدون
ایجاد Circular Import به db دسترسی داشته باشند.

چرا این‌جا؟ چون در پروژه‌های Flask، extensions.py الگوی استاندارد برای
جلوگیری از import چرخه‌ای بین app، models و routes است.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_socketio import SocketIO
from flask_wtf.csrf import CSRFProtect

# --- دیتابیس ORM ---
db = SQLAlchemy()

# --- احراز هویت ---
login_manager = LoginManager()
login_manager.login_view = "pages.login"
login_manager.login_message = "برای ادامه باید وارد حساب کاربری خود شوید."
login_manager.login_message_category = "warning"

# --- Real-Time (Flask-SocketIO) ---
# async_mode به‌صورت پیش‌فرض threading است تا بدون eventlet هم اجرا شود.
socketio = SocketIO(
    cors_allowed_origins="*",
    async_mode="threading",
    ping_timeout=30,
    ping_interval=10,
    logger=False,
    engineio_logger=False,
)

# --- محافظت CSRF برای فرم‌ها ---
csrf = CSRFProtect()
