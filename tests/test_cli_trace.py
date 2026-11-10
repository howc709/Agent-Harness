"""清理命令与文件trace的集成验收；使用临时目录，不改真实会话。"""

import json
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from main import main
from runtime import run_turn
from sessions import create_session, load_sessions, save_sessions


class FinishChecks(unittest.TestCase):
    def test_clear_command_preserves_todos_and_other_session(self):
        sessions = {name: create_session(name) for name in ("window1", "window2")}
        first = sessions["window1"]
        first["messages"].extend([
            {"role": "user", "content": "旧消息"},
            {"role": "assistant", "content": "旧回答"},
        ])
        first["todos"] = [{"id": 1, "text": "保留待办", "done": False}]
        first.update(summary="旧摘要", summary_turns=1)
        before = deepcopy(sessions)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "sessions.json"
            with patch("main.load_sessions", return_value=sessions):
                with patch("main.save_sessions", side_effect=lambda value: save_sessions(value, path)) as save:
                    def read_input(prompt):
                        if save.call_count == 0:
                            return "/clear"
                        self.assertEqual(len(load_sessions(path)["window1"]["messages"]), 1)
                        return "/exit"

                    with patch("builtins.input", side_effect=read_input):
                        with patch("runtime.complete") as model:
                            main()
                    model.assert_not_called()
            restored = load_sessions(path)
        first = restored["window1"]
        self.assertEqual(first["messages"], [before["window1"]["messages"][0]])
        self.assertEqual(first["todos"], before["window1"]["todos"])
        self.assertEqual((first["summary"], first["summary_turns"]), ("", 0))
        self.assertEqual(restored["window2"], before["window2"])
        with patch("runtime.complete", return_value={"role": "assistant", "content": "新回答"}) as model:
            self.assertEqual(run_turn(first, "新消息"), "新回答")
        self.assertEqual([m["role"] for m in model.call_args.args[0]], ["system", "user"])

    def test_tool_trace_success_and_failure(self):
        session = create_session("trace-demo")
        calls = [
            {"id": "divide-zero", "type": "function", "function": {
                "name": "calculator", "arguments": '{"a":7,"b":0,"op":"divide"}',
            }},
            {"id": "add-todo", "type": "function", "function": {
                "name": "todo", "arguments": '{"action":"add","text":"记录日志"}',
            }},
        ]
        replies = [
            {"role": "assistant", "content": None, "tool_calls": calls},
            {"role": "assistant", "content": "计算失败，待办新增成功"},
        ]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "tool_calls.jsonl"
            with patch("trace_log.TRACE_PATH", path):
                with patch("runtime.complete", side_effect=replies):
                    run_turn(session, "计算并新增待办")
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([r["event"] for r in records], ["tool_start", "tool_end"] * 2)
        self.assertEqual(len({r["turn_id"] for r in records}), 1)
        self.assertTrue(all(r["session_id"] == "trace-demo" and r["step"] == 1 and r["time"] for r in records))
        self.assertEqual(records[0]["tool_call_id"], records[1]["tool_call_id"])
        self.assertEqual(records[2]["tool_call_id"], records[3]["tool_call_id"])
        self.assertEqual(json.loads(records[0]["arguments"])["b"], 0)
        self.assertEqual(records[1]["status"], "error")
        self.assertEqual(records[1]["result"]["error"]["type"], "ZeroDivisionError")
        self.assertEqual(records[3]["status"], "ok")
        self.assertEqual(records[3]["result"]["task"], session["todos"][0])
        self.assertTrue(all(r["duration_ms"] >= 0 for r in records if r["event"] == "tool_end"))


if __name__ == "__main__":
    unittest.main()
