"""Local integration tests against the aplus mock portal."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MOCK_ROOT = Path("/Users/tutu/Github/aplus-mock-portal")
MOCK_ROOT = Path(os.environ.get("APLUS_MOCK_PORTAL_ROOT", str(DEFAULT_MOCK_ROOT))).expanduser()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@unittest.skipUnless(MOCK_ROOT.exists(), "aplus mock portal not available on this machine")
class MockPortalIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.port = _free_port()
        self.base_url = f"http://127.0.0.1:{self.port}/student/"
        self.server = subprocess.Popen(
            [sys.executable, "-m", "src.server", "--host", "127.0.0.1", "--port", str(self.port)],
            cwd=MOCK_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.addCleanup(self._stop_server)
        self._wait_until_ready()

    def _stop_server(self) -> None:
        if self.server.poll() is None:
            self.server.terminate()
            try:
                self.server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server.kill()

    def _wait_until_ready(self) -> None:
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                with urlopen(self.base_url, timeout=1):
                    return
            except Exception:
                time.sleep(0.2)
        self.fail("Mock portal did not become ready in time.")

    def _run_attend(self, *args: str) -> dict:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT / "src")
        result = subprocess.run(
            [sys.executable, "-m", "always_attend", *args],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        return json.loads(result.stdout)

    def _reset_mock(self) -> None:
        request = Request(f"http://127.0.0.1:{self.port}/mock/reset", method="POST")
        with urlopen(request, timeout=5):
            return

    def test_inspect_and_handoff_use_live_mock_portal(self) -> None:
        inspect_payload = self._run_attend("inspect", "state", "--target", self.base_url, "--json")
        self.assertGreater(len(inspect_payload["data"]["items"]), 0)

        handoff_payload = self._run_attend(
            "handoff",
            "--target",
            self.base_url,
            "--sources",
            "attendance",
            "--json",
        )
        self.assertGreater(len(handoff_payload["data"]["open_items"]), 0)
        self.assertEqual(handoff_payload["data"]["artifacts"], [])

    def test_submit_plan_executes_against_live_mock_portal(self) -> None:
        self._reset_mock()
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_path = Path(temp_dir) / "plan.json"
            plan_path.write_text(
                json.dumps(
                    [
                        {
                            "course_code": "FIT1045",
                            "week": 12,
                            "slot": "Lecture 01",
                            "code": "M8YHB",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            payload = self._run_attend("submit", "--plan", str(plan_path), "--target", self.base_url, "--json")

        self.assertEqual(payload["data"]["runs"][0]["summary"]["success"], True)
        self.assertEqual(payload["data"]["runs"][0]["summary"]["codes_submitted"]["FIT1045"], 1)


if __name__ == "__main__":
    unittest.main()
