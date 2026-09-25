"""
run.py — نقطه‌ی ورود پروژه Count Time Game

مسئولیت این فایل فقط اجرای سرور است. ساخت اپ در app/__init__.py انجام
می‌شود و اینجا فقط نمونه گرفته و socketio.run صدا زده می‌شود.

چرا socketio.run و نه app.run؟
    چون Flask-SocketIO نیاز به سروری دارد که از WebSocket پشتیبانی کند.
    socketio.run به‌صورت خودکار موتور مناسب (threading/eventlet) را
    برمی‌گزیند و در حالت debug از reloader امن استفاده می‌کند.
"""

import os

from app import create_app
from app.extensions import socketio

app = create_app(os.getenv("FLASK_ENV", "development"))

if __name__ == "__main__":
    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=app.config.get("DEBUG", True),
        allow_unsafe_werkzeug=True,
    )
