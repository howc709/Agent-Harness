"""用确定的模型响应检查完整Runtime；不访问API、不修改真实会话文件。"""

import json
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from runtime import run_turn
from sessions import create_session, load_sessions, save_sessions


def tool_message(name, arguments, call_id="runtime-check"):
    return {"role": "assistant", "content": None, "tool_calls": [{
        "id": call_id, "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }]}


class RuntimeChecks(unittest.TestCase):
    def setUp(self):
        trace = patch("runtime.write_trace")
        trace.start()
        self.addCleanup(trace.stop)

    def test_direct_answer_and_followup(self):
        session = create_session("direct")

        requests = []

        def model(messages, tools):
            requests.append(json.loads(json.dumps(messages)))
            return {"role": "assistant", "content": "已记住" if len(requests) == 1 else "蓝鲸七号"}

        with patch("runtime.complete", side_effect=model):
            self.assertEqual(run_turn(session, "暗号是蓝鲸七号"), "已记住")
            self.assertEqual(run_turn(session, "暗号是什么？"), "蓝鲸七号")
        self.assertEqual(requests[1][1]["content"], "暗号是蓝鲸七号")
        self.assertEqual(requests[1][2]["content"], "已记住")

    def test_multiple_tools_and_pairing(self):
        session = create_session("tools")
        assistant = tool_message("calculator", {"a": 2, "b": 3, "op": "add"}, "calc")
        assistant["tool_calls"] += tool_message("search", {"query": "session"}, "search")["tool_calls"]
        with patch("runtime.complete", side_effect=[assistant, {"role": "assistant", "content": "结果是5"}]) as model:
            self.assertEqual(run_turn(session, "计算并搜索"), "结果是5")
        self.assertEqual(model.call_count, 2)
        results = [m for m in session["messages"] if m["role"] == "tool"]
        self.assertEqual([m["tool_call_id"] for m in results], ["calc", "search"])
        self.assertEqual(json.loads(results[0]["content"]), 5)
        self.assertTrue(json.loads(results[1]["content"])["mock"])

    def test_step_limit(self):
        session = create_session("limit")
        with patch("runtime.complete", return_value=tool_message("calculator", {"a": 2, "b": 3, "op": "add"})) as model:
            self.assertIn("上限", run_turn(session, "计算", max_steps=2))
        self.assertEqual(model.call_count, 2)
        self.assertEqual(len([m for m in session["messages"] if m["role"] == "tool"]), 2)

    def test_tool_followup_uses_previous_result(self):
        session = create_session("followup")
        requests = []
        replies = iter([
            tool_message("calculator", {"a": 137, "b": 29, "op": "multiply"}, "first"),
            {"role": "assistant", "content": "3973"},
            tool_message("calculator", {"a": 3973, "b": 2, "op": "multiply"}, "followup"),
            {"role": "assistant", "content": "7946"},
        ])

        def model(messages, tools):
            requests.append(deepcopy(messages))
            return next(replies)

        with patch("runtime.complete", side_effect=model):
            self.assertEqual(run_turn(session, "计算137乘29"), "3973")
            self.assertEqual(run_turn(session, "刚才的结果再乘2"), "7946")
        previous_results = [m for m in requests[2] if m["role"] == "tool"]
        self.assertEqual(json.loads(previous_results[0]["content"]), 3973)
        results = [json.loads(m["content"]) for m in session["messages"] if m["role"] == "tool"]
        self.assertEqual(results, [3973, 7946])

    def test_tool_error_is_fed_back_and_model_can_continue(self):
        session = create_session("tool-error")
        replies = [
            tool_message("calculator", {"a": 7, "b": 0, "op": "divide"}, "bad"),
            tool_message("calculator", {"a": 15, "b": 4, "op": "multiply"}, "good"),
            {"role": "assistant", "content": "除零失败，随后计算得到60"},
        ]
        with patch("runtime.complete", side_effect=replies):
            self.assertIn("60", run_turn(session, "先算7除以0，再算15乘4"))
        results = [m for m in session["messages"] if m["role"] == "tool"]
        self.assertEqual([m["tool_call_id"] for m in results], ["bad", "good"])
        self.assertEqual(json.loads(results[0]["content"])["error"]["type"], "ZeroDivisionError")
        self.assertEqual(json.loads(results[1]["content"]), 60)

    def test_http_failure_before_tools(self):
        session = create_session("http")
        error = HTTPError("https://example.invalid", 429, "rate limited", {}, None)
        with patch("runtime.complete", side_effect=error):
            answer = run_turn(session, "你好")
        self.assertIn("失败", answer)
        self.assertEqual(session["messages"][-1], {"role": "assistant", "content": answer})
        self.assertEqual(session["todos"], [])

    def test_failure_after_todo_then_save_and_continue(self):
        session = create_session("recover")
        replies = [
            tool_message("todo", {"action": "add", "text": "复习Agent"}),
            URLError("simulated disconnect"),
            {"role": "assistant", "content": "已新增复习Agent"},
        ]
        with patch("runtime.complete", side_effect=replies) as model:
            self.assertIn("失败", run_turn(session, "新增待办"))
            self.assertEqual(len(session["todos"]), 1)
            with TemporaryDirectory() as directory:
                path = Path(directory) / "sessions.json"
                save_sessions({"recover": session}, path)
                restored = load_sessions(path)["recover"]
            self.assertEqual(run_turn(restored, "继续"), "已新增复习Agent")
        self.assertEqual(model.call_count, 3)
        self.assertEqual(restored["todos"], [{"id": 1, "text": "复习Agent", "done": False}])
        results = [m for m in restored["messages"] if m["role"] == "tool"]
        self.assertEqual(len(results), 1, "恢复后没有重复执行新增工具")
        self.assertEqual(results[0]["tool_call_id"], "runtime-check")

    def test_summary_request_failure(self):
        session = create_session("summary-failure")
        with patch("runtime.build_context", side_effect=URLError("summary disconnect")):
            with patch("runtime.complete") as model:
                self.assertIn("失败", run_turn(session, "继续聊天"))
        model.assert_not_called()
        self.assertEqual(session["summary_turns"], 0)
        self.assertEqual(session["messages"][-1]["role"], "assistant")


if __name__ == "__main__":
    unittest.main()
