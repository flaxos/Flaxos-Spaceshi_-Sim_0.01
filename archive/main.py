"""Legacy server entry point updated for the new hybrid runner."""

import time
from sim.socket_listener import start_socket_listener
from hybrid_runner import HybridRunner


def main(host: str = "127.0.0.1", port: int = 9999):
    """Start the simulation runner and socket server."""
    runner = HybridRunner()
    runner.load_ships()
    runner.start()

    start_socket_listener(host, port, runner)
    print(f"Server listening on {host}:{port}. Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        runner.stop()


if __name__ == "__main__":
    main()

