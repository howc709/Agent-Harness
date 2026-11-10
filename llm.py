"""模型通信层：向配置指定的兼容API发送消息，返回一条assistant消息。"""

import json
import os
import ssl
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def complete(messages: list[dict], tools: list[dict] | None = None) -> dict:
    config_path = Path(__file__).with_name("settings.local.json")
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    api_key = os.environ.get("MOONSHOT_API_KEY") or config["api_key"]

    payload = {"model": config["model"], "messages": messages}

    if tools:
        payload["tools"] = tools
    request = Request(

        url=config["base_url"].rstrip("/") + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    for attempt in range(3):
        try:
            with urlopen(request, timeout=90) as response:
                data = json.loads(response.read().decode("utf-8"))
            break
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            print(f"[API错误] HTTP {error.code}：{detail}")
            retry_after = error.headers.get("Retry-After") if error.headers else None
            if retry_after:
                print(f"[API提示] Retry-After：{retry_after}")
            raise
        except URLError as error:
            if not isinstance(error.reason, ssl.SSLEOFError) or attempt == 2:
                raise
            delay = attempt + 1
            print(f"[网络重试] TLS连接中断，{delay}秒后重发当前请求（重试{attempt + 1}/2）")
            time.sleep(delay)

    return data["choices"][0]["message"]
