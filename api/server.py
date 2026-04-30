from __future__ import annotations

import json
import os
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from api.battery_config import load_battery_config, save_battery_config

HOST = "127.0.0.1"
PORT = int(os.getenv("BATTERY_CONFIG_API_PORT", "8001"))


class ApiHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self) -> None:
        self._send_json({}, status=HTTPStatus.NO_CONTENT)

    def do_GET(self) -> None:
        if self._path != "/api/battery-config":
            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
            return

        self._send_json(asdict(load_battery_config()))

    def do_PUT(self) -> None:
        self._save_config()

    def do_POST(self) -> None:
        self._save_config()

    def _save_config(self) -> None:
        if self._path != "/api/battery-config":
            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
            return

        try:
            payload = self._read_json_body()
            if not isinstance(payload, dict):
                raise ValueError("Request body must be a JSON object")
            config = save_battery_config(payload)
        except (json.JSONDecodeError, ValueError) as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        self._send_json(asdict(config))

    @property
    def _path(self) -> str:
        return urlparse(self.path).path

    def _read_json_body(self) -> Any:
        length = int(self.headers.get("content-length", "0"))
        raw_body = self.rfile.read(length)
        return json.loads(raw_body.decode("utf-8") or "{}")

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = b"" if status == HTTPStatus.NO_CONTENT else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, PUT, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), ApiHandler)
    print(f"Battery config API listening on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
