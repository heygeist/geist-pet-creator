from __future__ import annotations

import base64
import io
import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "geist-pet-creator" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from generate_candidates import ProviderConfig, call_provider, decode_image, set_base_url  # noqa: E402


def encoded_fixture() -> str:
    image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    for x in range(8, 24):
        for y in range(8, 24):
            image.putpixel((x, y), (255, 122, 51, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class MockProviderHandler(BaseHTTPRequestHandler):
    received: dict[str, object] = {}

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        type(self).received = {
            "path": self.path,
            "authorization": self.headers.get("Authorization"),
            "body": body,
        }
        payload = json.dumps(
            {"data": [{"b64_json": encoded_fixture()}], "usage": {"cost": 0.001}}
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *_args: object) -> None:
        return


class MockProviderTests(unittest.TestCase):
    def test_local_mock_receives_request_without_provider_credential(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), MockProviderHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            set_base_url(f"http://127.0.0.1:{server.server_port}/api/v1")
            with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}, clear=False):
                payload = call_provider(
                    ProviderConfig(model="openai/gpt-image-2"),
                    "original orange square fixture",
                    [],
                    retries=0,
                )
            image, cost = decode_image(payload)
            self.assertEqual(image.size, (32, 32))
            self.assertEqual(cost, 0.001)
            self.assertEqual(MockProviderHandler.received["path"], "/api/v1/images")
            self.assertIsNone(MockProviderHandler.received["authorization"])
            body = MockProviderHandler.received["body"]
            self.assertIsInstance(body, dict)
            self.assertEqual(body["model"], "openai/gpt-image-2")
        finally:
            set_base_url(None)
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
