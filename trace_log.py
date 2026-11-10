"""工具执行日志：逐行追加JSON，不参与模型context。"""

import json
from datetime import datetime, timezone
from pathlib import Path


TRACE_PATH = Path(__file__).with_name("logs") / "tool_calls.jsonl"


def write_trace(event: str, **fields) -> None:
    record = {
        "time": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "event": event,
        **fields,
    }
    try:
        TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with TRACE_PATH.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as error:
        print(f"[日志写入失败] {error}")
