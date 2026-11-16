import json
import os
import socket
import subprocess
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).parents[1]


class _GatewayHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.__class__.requests.append({
            "path": self.path,
            "payload": json.loads(body.decode() or "{}"),
        })
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"accepted":true}')

    def log_message(self, format: str, *args: object) -> None:
        return


@unittest.skipUnless(os.getenv("PIA_TEST_POSTGRES_DSN"), "requires isolated PostgreSQL integration database")
class PushAcceptanceTest(unittest.TestCase):
    def test_external_push_acceptance_script_persists_delivery(self):
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import make_conninfo
        from pia_runtime.models import new_id

        schema = new_id("push_test")
        admin = psycopg.connect(os.environ["PIA_TEST_POSTGRES_DSN"], autocommit=True)
        self.addCleanup(admin.close)
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        self.addCleanup(lambda: admin.execute(
            sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)),
        ))
        dsn = make_conninfo(os.environ["PIA_TEST_POSTGRES_DSN"], options=f"-csearch_path={schema}")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            api_port = sock.getsockname()[1]
        _GatewayHandler.requests = []
        gateway = ThreadingHTTPServer(("127.0.0.1", 0), _GatewayHandler)
        thread = threading.Thread(target=gateway.serve_forever, daemon=True)
        thread.start()
        try:
            result = subprocess.run(
                ["bash", "scripts/push-acceptance.sh"],
                cwd=ROOT,
                env={
                    **os.environ,
                    "PIA_POSTGRES_DSN": dsn,
                    "PIA_WEB_PUSH_GATEWAY_URL": (
                        f"http://127.0.0.1:{gateway.server_port}/push"
                    ),
                    "PIA_PUSH_ACCEPTANCE_WEB_TOKEN": "web-acceptance-token",
                    "PIA_PUSH_ACCEPTANCE_PORT": str(api_port),
                },
                capture_output=True,
                text=True,
                timeout=30,
            )
        finally:
            gateway.shutdown()
            gateway.server_close()
            thread.join(timeout=5)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("EXTERNAL PUSH ACCEPTANCE PASS web", result.stdout + result.stderr)
        self.assertTrue(_GatewayHandler.requests)
        self.assertEqual(
            _GatewayHandler.requests[-1]["payload"]["devices"][0]["push_token"],
            "web-acceptance-token",
        )


if __name__ == "__main__":
    unittest.main()
