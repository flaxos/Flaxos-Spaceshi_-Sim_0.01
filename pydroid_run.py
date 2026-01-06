import argparse
import threading

from mobile_ui.app import app as mobile_app
from server.run_server import _serve


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run sim server + mobile UI in one process (Pydroid-friendly)."
    )
    parser.add_argument("--server-host", default="127.0.0.1")
    parser.add_argument("--server-port", type=int, default=8765)
    parser.add_argument("--dt", type=float, default=0.1)
    parser.add_argument("--fleet-dir", default="hybrid_fleet")
    parser.add_argument("--ui-host", default="0.0.0.0")
    parser.add_argument("--ui-port", type=int, default=5000)
    args = parser.parse_args()

    server_thread = threading.Thread(
        target=_serve,
        args=(args.server_host, args.server_port, args.dt, args.fleet_dir),
        daemon=True,
    )
    server_thread.start()
    print(
        "Mobile UI running at "
        f"http://{args.ui_host}:{args.ui_port} -> "
        f"server {args.server_host}:{args.server_port}"
    )
    mobile_app.run(host=args.ui_host, port=args.ui_port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
