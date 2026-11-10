"""运行层：调用模型、执行工具，并将结果写回消息历史。"""

import json
from time import perf_counter
from urllib.error import URLError
from uuid import uuid4
from context import build_context
from llm import complete
from tools import TOOL_REGISTRY
from trace_log import write_trace
from validation import validate_arguments


def execute_tool_call(tool_call: dict, session: dict):
    """执行一条工具调用，成功返回结果，已知调用错误返回可序列化的失败信息。"""
    try:
        function = tool_call["function"]
        arguments = json.loads(function["arguments"])
        if function["name"] not in TOOL_REGISTRY:
            raise ValueError("未知的工具名")
        tool = TOOL_REGISTRY[function["name"]]
        validate_arguments(arguments, tool["definition"]["function"]["parameters"])
        tool_handler = tool["handler"]

        if tool.get("needs_session", False):
            return tool_handler(session, **arguments)
        return tool_handler(**arguments)
    except (ValueError, TypeError, ZeroDivisionError) as error:
        return {"error": {"type": type(error).__name__, "message": str(error)}}


def run_turn(session: dict, user_input: str, max_steps: int = 5) -> str:
    """处理一次用户输入；最多请求模型max_steps次。"""
    messages = session["messages"]
    turn_id = uuid4().hex
    definitions = []
    for tool in TOOL_REGISTRY.values():
        definitions.append(tool["definition"])

    messages.append({"role": "user", "content": user_input})
    for step in range(max_steps):
        print(f"[模型] 本条输入内第 {step + 1}/{max_steps} 次请求")

        try:
            context = build_context(session)

            print(f"[Context] 保存历史 {len(messages)} 条，本次发送 {len(context)} 条")
            assistant = complete(context, tools=definitions)
        except (URLError, TimeoutError, ConnectionError) as error:
            print(f"[请求中断] {type(error).__name__}：{error}")
            failure = "本次模型请求失败，历史与已执行的工具结果已保留。可稍后输入“继续”，不要重复新增同一待办。"

            messages.append({"role": "assistant", "content": failure})
            return failure

        messages.append(assistant)
        tool_calls = assistant.get("tool_calls") or []

        if not tool_calls:
            return assistant.get("content") or ""

        for tool_call in tool_calls:
            print(f"[工具] {tool_call['function']['name']} 参数：{tool_call['function']['arguments']}")

            trace_fields = {
                "session_id": session["id"],
                "turn_id": turn_id,
                "step": step + 1,
                "tool_call_id": tool_call["id"],
                "tool": tool_call["function"]["name"],
            }
            write_trace("tool_start", **trace_fields, arguments=tool_call["function"]["arguments"])
            started = perf_counter()
            result = execute_tool_call(tool_call, session)
            failed = isinstance(result, dict) and "error" in result
            write_trace(
                "tool_end", **trace_fields,
                status="error" if failed else "ok",
                duration_ms=round((perf_counter() - started) * 1000, 3),
                result=result,
            )
            print(f"[结果] {result}")

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": json.dumps(result, ensure_ascii=False),
            })

    return "本次已达到模型请求次数上限，请缩小任务范围后重试。"
