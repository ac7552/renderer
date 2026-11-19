"""python -m renderer [--host 127.0.0.1] [--port 8000]: the fitting room page and its API, on this machine."""

from __future__ import annotations

import argparse
import sys
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from .server import App


class Server(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class Handler(WSGIRequestHandler):
    def log_request(self, code="-", size="-"):
        # The method, the path and the status: never the query string (a pasted link) or the body (measurements).
        path = self.path.split("?", 1)[0]
        sys.stderr.write(f"{self.command} {path} {code}\n")

    def log_message(self, format, *args):  # noqa: A002 - the standard library's name
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m renderer", description="Serve the fitting room page and its API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    options = parser.parse_args(argv)
    with make_server(options.host, options.port, App(), server_class=Server, handler_class=Handler) as server:
        print(f"The fitting room is at http://{options.host}:{options.port}/", file=sys.stderr)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
