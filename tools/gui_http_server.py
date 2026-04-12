#!/usr/bin/env python3

from __future__ import annotations

import argparse
import functools
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class NoCacheHTTPRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve GUI files with no-cache headers")
    parser.add_argument("port", type=int, help="Port to bind")
    parser.add_argument("--bind", default="127.0.0.1", help="Bind address")
    parser.add_argument("--directory", default=os.getcwd(), help="Directory to serve")
    args = parser.parse_args()

    handler = functools.partial(NoCacheHTTPRequestHandler, directory=args.directory)
    server = ThreadingHTTPServer((args.bind, args.port), handler)

    print(f"Serving {args.directory} on http://{args.bind}:{args.port}/ (cache disabled)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
