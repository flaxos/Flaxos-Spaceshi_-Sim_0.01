import json
import socket
import sys
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from android_update.pydroid_manager import (
    PydroidUpdateManager,
    create_update_api_routes,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
SOCKET_TIMEOUT = 3

app = Flask(__name__)

# Initialize update manager and add API routes
update_manager = PydroidUpdateManager(str(Path(__file__).parent.parent))
create_update_api_routes(app, update_manager)


def send_socket_command(host: str, port: int, payload: dict[str, Any]) -> Any:
    message = json.dumps(payload) + "\n"
    with socket.create_connection((host, port), timeout=SOCKET_TIMEOUT) as sock:
        sock.sendall(message.encode("utf-8"))
        buffer = b""
        while b"\n" not in buffer:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buffer += chunk

    if not buffer:
        return {"ok": False, "error": "no response"}

    line = buffer.split(b"\n", 1)[0].decode("utf-8")
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return {"ok": False, "error": "invalid json", "raw": line}


@app.get("/")
def index() -> str:
    return render_template(
        "index.html",
        default_host=DEFAULT_HOST,
        default_port=DEFAULT_PORT,
    )


@app.post("/api/send")
def api_send():
    payload = request.get_json(silent=True) or {}
    host = payload.get("host", DEFAULT_HOST)
    port = int(payload.get("port", DEFAULT_PORT))
    command = payload.get("payload")

    if not isinstance(command, dict):
        return jsonify({"ok": False, "error": "payload must be an object"}), 400

    try:
        response = send_socket_command(host, port, command)
    except OSError as exc:
        return jsonify({"ok": False, "error": str(exc)})

    if isinstance(response, dict) and response.get("ok") is False:
        return jsonify(
            {
                "ok": False,
                "error": response.get("error", "server error"),
                "response": response,
            }
        )

    return jsonify({"ok": True, "response": response})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
