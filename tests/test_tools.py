import json
import unittest

from runtime import execute_tool_call
from sessions import create_session
from tools import TOOL_REGISTRY, calculator, search, todo


def call(session, name, arguments):
    return execute_tool_call({
        "id": "tool-test",
        "function": {
            "name": name,
            "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments),
        },
    }, session)


class ToolTests(unittest.TestCase):
    def test_calculator(self):
        for op, expected in [("add", 9), ("subtract", 5), ("multiply", 14), ("divide", 3.5)]:
            with self.subTest(op=op):
                self.assertEqual(calculator(7, 2, op), expected)
        with self.assertRaises(ZeroDivisionError):
            calculator(7, 0, "divide")

    def test_mock_search(self):
        result = search("session")
        self.assertTrue(result["mock"])
        self.assertEqual(result["results"][0]["id"], "demo-session")
        self.assertEqual(search("没有这个关键词")["results"], [])

    def test_registration(self):
        self.assertEqual(set(TOOL_REGISTRY), {"calculator", "search", "todo"})
        for name, tool in TOOL_REGISTRY.items():
            self.assertEqual(tool["definition"]["function"]["name"], name)
            self.assertTrue(tool["definition"]["function"]["description"])
            self.assertEqual(tool["definition"]["function"]["parameters"]["type"], "object")
            self.assertTrue(callable(tool["handler"]))
        self.assertNotIn("session", TOOL_REGISTRY["todo"]["definition"]["function"]["parameters"]["properties"])

    def test_todo_business_constraints(self):
        session = create_session("todo")
        self.assertEqual(todo(session, "list"), {"tasks": []})
        first = todo(session, "add", text="复习Agent")["task"]
        second = todo(session, "add", text="整理材料")["task"]
        self.assertEqual((first["id"], second["id"]), (1, 2))
        todo(session, "complete", task_id=1)
        self.assertEqual([t["done"] for t in session["todos"]], [True, False])
        for arguments in [{"action": "add", "text": "  "}, {"action": "complete", "task_id": 99}]:
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                todo(session, **arguments)

    def test_invalid_parameters_do_not_change_state(self):
        session = create_session("validation")
        cases = [
            ("calculator", {"a": 2, "b": 3}),
            ("calculator", {"a": "2", "b": 3, "op": "add"}),
            ("calculator", {"a": True, "b": 3, "op": "add"}),
            ("calculator", {"a": 2, "b": 3, "op": "power"}),
            ("calculator", [2, 3, "add"]),
            ("todo", {"action": "complete", "task_id": 1.5}),
            ("todo", {"action": "add", "text": "不能新增", "session": "other"}),
        ]
        for name, arguments in cases:
            with self.subTest(name=name, arguments=arguments):
                self.assertEqual(call(session, name, arguments)["error"]["type"], "ValueError")
        self.assertEqual(session["todos"], [])

    def test_tool_errors_are_serializable_and_recoverable(self):
        session = create_session("errors")
        cases = [
            ("unknown", {}, "ValueError"),
            ("calculator", "{", "JSONDecodeError"),
            ("calculator", {"a": 7, "b": 0, "op": "divide"}, "ZeroDivisionError"),
        ]
        for name, arguments, expected in cases:
            with self.subTest(name=name, arguments=arguments):
                result = call(session, name, arguments)
                self.assertEqual(result["error"]["type"], expected)
                self.assertTrue(result["error"]["message"])
                json.dumps(result)
        self.assertEqual(call(session, "calculator", {"a": 15, "b": 4, "op": "multiply"}), 60)
