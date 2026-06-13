from __future__ import annotations

import argparse
import asyncio
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from agentic_runtime.server import RuntimeServer


def run(host: str = "127.0.0.1", port: int = 8765, mock: bool = True) -> None:
    runtime = RuntimeServer.create(mock=mock)
    service = runtime.kernel_service

    class Handler(BaseHTTPRequestHandler):
        def _json(self, status: int, data: dict) -> None:
            payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:
            if self.path == "/status":
                self._json(200, service.status())
                return
            if self.path == "/core/status":
                self._json(200, service.core_status())
                return
            self._json(404, {"success": False, "error_code": "NOT_FOUND"})

        def do_POST(self) -> None:
            if self.path == "/core/refresh":
                self._json(200, runtime.config_manager.refresh().to_dict())
                return
            self._json(404, {"success": False, "error_code": "NOT_FOUND"})

        def log_message(self, format: str, *args) -> None:
            return

    ThreadingHTTPServer((host, port), Handler).serve_forever()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="agenticd")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--mock", action="store_true", default=True)
    args = parser.parse_args(argv)
    run(args.host, args.port, mock=args.mock)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
