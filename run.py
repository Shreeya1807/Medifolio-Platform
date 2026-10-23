import os
from backend.platform_app import create_app

app = create_app()
socketio = app.extensions["socketio"]
if __name__ == "__main__":
    socketio.run(
        app,
        host="127.0.0.1",
        port=int(os.environ.get("PORT", "5001")),
        allow_unsafe_werkzeug=True,
    )
