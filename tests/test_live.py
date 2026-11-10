import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from runtime import run_turn
from sessions import create_session


@unittest.skipUnless(os.environ.get("AGENT_LIVE_TEST") == "1", "set AGENT_LIVE_TEST=1 to call the real API")
class LiveTests(unittest.TestCase):
    def test_real_calculator_and_followup(self):
        session = create_session("live-test")
        with TemporaryDirectory() as directory:
            with patch("trace_log.TRACE_PATH", Path(directory) / "trace.jsonl"):
                run_turn(session, "必须用calculator工具计算137乘29。")
                answer = run_turn(session, "把刚才的结果再乘以2，也请使用calculator工具。")
        results = [json.loads(m["content"]) for m in session["messages"] if m["role"] == "tool"]
        self.assertIn(3973, results)
        self.assertIn(7946, results)
        self.assertIn("7946", answer.replace(",", "").replace("，", ""))
