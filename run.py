"""
run.py — Entry point for the Count Time Game project.

This file only runs the server. The app is built in app/__init__.py and
here we simply grab the instance and call socketio.run.

Why socketio.run and not app.run?
    Because Flask-SocketIO needs a server that supports WebSocket.
    socketio.run automatically picks the right engine (threading/eventlet)
    and uses a safe reloader in debug mode.
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
