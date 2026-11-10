import json
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from context import build_context, split_turns
from sessions import create_session, get_session, load_sessions, save_sessions
from tools import todo


def make_history():
    session = create_session("context")
    for text in ["暗号是蓝鲸七号", "用Python开发Agent", "代码保持简单", "保留关键事实"]:
        session["messages"].extend([
            {"role": "user", "content": text},
            {"role": "assistant", "content": "好的"},
        ])
    session["messages"].extend([
        {"role": "user", "content": "计算2加3"},
        {"role": "assistant", "content": None, "tool_calls": [{
            "id": "calc", "type": "function",
            "function": {"name": "calculator", "arguments": '{"a":2,"b":3,"op":"add"}'},
        }]},
        {"role": "tool", "tool_call_id": "calc", "content": "5"},
        {"role": "assistant", "content": "结果是5"},
        {"role": "user", "content": "暗号和计算结果是什么？"},
    ])
    todo(session, "add", text="完成笔试")
    return session


class StateContextTests(unittest.TestCase):
    def test_session_isolation_and_return_to_same_session(self):
        sessions = {}
        first, second = get_session(sessions, "window1"), get_session(sessions, "window2")
        self.assertIs(get_session(sessions, "window1"), first)
        self.assertIsNot(first["messages"], second["messages"])
        self.assertIsNot(first["todos"], second["todos"])
        first["messages"].append({"role": "user", "content": "蓝鲸七号"})
        todo(first, "add", text="复习Agent")
        self.assertEqual(todo(second, "list"), {"tasks": []})
        todo(second, "add", text="整理材料")
        todo(first, "complete", task_id=1)
        self.assertFalse(second["todos"][0]["done"])
        self.assertEqual(len(second["messages"]), 1)

    def test_storage_roundtrip(self):
        session = make_history()
        session.update(summary="历史摘要", summary_turns=4)
        other = create_session("other")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "data" / "sessions.json"
            self.assertEqual(load_sessions(path), {})
            sessions = {session["id"]: session, "other": other}
            save_sessions(sessions, path)
            self.assertEqual(load_sessions(path), sessions)
            todo(session, "complete", task_id=1)
            save_sessions(sessions, path)
            self.assertTrue(load_sessions(path)[session["id"]]["todos"][0]["done"])
            self.assertFalse(path.with_suffix(".tmp").exists())

    def test_context_groups_preserve_tool_pairs(self):
        session = make_history()
        before = deepcopy(session)
        turns = split_turns(session["messages"][1:])
        self.assertEqual([len(turn) for turn in turns], [2, 2, 2, 2, 4, 1])
        context = build_context(session)
        self.assertEqual(context, session["messages"])
        self.assertIsNot(context, session["messages"])
        self.assertEqual(session, before)

    def test_compression_cache_recovery_and_incremental_update(self):
        session = make_history()
        before = deepcopy(session)
        with patch("context.complete", return_value={"content": "暗号蓝鲸七号，使用Python，代码简单。"}) as model:
            context = build_context(session, max_chars=1, keep_turns=2)
            self.assertEqual(build_context(session, max_chars=1, keep_turns=2), context)
        self.assertEqual(model.call_count, 1)
        self.assertEqual(session["summary_turns"], 4)
        self.assertEqual(session["messages"], before["messages"])
        self.assertEqual(session["todos"], before["todos"])
        self.assertEqual([m["role"] for m in context], ["system", "assistant", "user", "assistant", "tool", "assistant", "user"])
        self.assertEqual(context[3]["tool_calls"][0]["id"], context[4]["tool_call_id"])
        with TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            save_sessions({"context": session}, path)
            restored = load_sessions(path)["context"]
        with patch("context.complete") as model:
            self.assertEqual(build_context(restored, max_chars=1, keep_turns=2), context)
        model.assert_not_called()
        old_summary = restored["summary"]
        for text in ["下一步", "继续"]:
            restored["messages"].extend([
                {"role": "user", "content": text}, {"role": "assistant", "content": "好的"},
            ])
        with patch("context.complete", return_value={"content": "更新后的摘要"}) as model:
            build_context(restored, max_chars=1, keep_turns=2)
        request = json.loads(model.call_args.args[0][1]["content"])
        self.assertEqual(request["已有摘要"], old_summary)
        self.assertEqual(len(request["新增历史轮次"]), 2)
        self.assertEqual(restored["summary_turns"], 6)

    def test_failed_summary_does_not_advance_coverage(self):
        session = make_history()
        before = deepcopy(session)
        with patch("context.complete", return_value={"content": "  "}):
            with self.assertRaises(ValueError):
                build_context(session, max_chars=1, keep_turns=2)
        self.assertEqual(session, before)

    def test_current_turn_must_be_retained(self):
        with self.assertRaises(ValueError):
            build_context(make_history(), keep_turns=0)
