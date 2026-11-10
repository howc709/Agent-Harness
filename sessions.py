"""会话层：创建、取回会话，并将会话字典保存到本地JSON文件。"""

import json
from pathlib import Path


STATE_PATH = Path(__file__).with_name("data") / "sessions.json"

SYSTEM_PROMPT = (
    "你是一个简洁、准确的中文助手。涉及数值运算时使用calculator工具。"
    "查询本地演示资料时使用search工具，只传核心关键词。"
    "search只检索固定mock资料，不是联网搜索。"
    "新增、列出、完成待办必须调用todo工具，以工具结果为准。"
    "不确定要完成哪项时，先用todo列出或询问用户。"
    "根据工具实际结果回答，没有匹配时明确说明。"
)


def create_session(session_id: str) -> dict:
    return {
        "id": session_id,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}],
        "todos": [],
        "summary": "",
        "summary_turns": 0,
    }


def get_session(sessions: dict, session_id: str) -> dict:
    """不存在则创建，存在则取回同一个session，不覆盖历史。"""

    if session_id not in sessions:
        sessions[session_id] = create_session(session_id)

    return sessions[session_id]


def clear_history(session: dict) -> None:
    """清除当前会话的对话与摘要，保留会话身份和真实待办。"""
    session["messages"] = [{"role": "system", "content": SYSTEM_PROMPT}]

    session["summary"] = ""
    session["summary_turns"] = 0


def load_sessions(path: Path = STATE_PATH) -> dict:
    """启动时读取保存的会话；首次运行没有文件则返回空字典。"""
    if not path.exists():
        return {}

    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_sessions(sessions: dict, path: Path = STATE_PATH) -> None:
    """保存整个会话集合；先写临时文件，写完后再替换正式文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")

    temporary_path.write_text(json.dumps(sessions), encoding="utf-8")

    temporary_path.replace(path)
