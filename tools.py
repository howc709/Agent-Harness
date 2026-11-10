"""工具层：保存工具定义，并提供真正执行计算的Python函数。"""


def calculator(a: float, b: float, op: str) -> float:
    """对两个数执行add/subtract/multiply/divide中的一种运算。"""

    if op == "add":
        return a + b
    elif op == "subtract":
        return a - b
    elif op == "multiply":
        return a * b

    elif op == "divide":
        return a / b
    raise ValueError("不支持的运算")


CALCULATOR_DEFINITION = {
    "type": "function",
    "function": {
        "name": "calculator",

        "description": "需要执行两个数的加减乘除时调用，以得到计算结果",
        "parameters": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "第一个数"},
                "b": {"type": "number", "description": "第二个数"},
                "op": {
                    "type": "string",
                    "enum": ["add", "subtract", "multiply", "divide"],
                    "description": "运算名称，依次表示加、减、乘、除",
                },
            },

            "required": ["a", "b", "op"],
            "additionalProperties": False,
        },
    },
}


SEARCH_DOCUMENTS = [
    {
        "id": "demo-session",
        "title": "session隔离",
        "content": "每个session分别保存自己的消息和待办，切换会话时取回对应状态。",
    },
    {
        "id": "demo-agent",
        "title": "Agent循环",
        "content": "模型提出工具调用，本地执行并回填结果，再请求模型判断下一步。",
    },
    {
        "id": "demo-todo",
        "title": "todo工具",
        "content": "todo用于新增、列出和完成待办；待办的实际状态由程序保存。",
    },
]


def search(query: str) -> dict:
    """在固定演示资料的标题或正文中按关键词检索。"""
    results = []

    for doc in SEARCH_DOCUMENTS:
        if query in doc["title"] or query in doc["content"]:
            results.append(doc)

    return {"mock": True, "query": query, "results": results}


SEARCH_DEFINITION = {
    "type": "function",
    "function": {
        "name": "search",

        "description": "本地mock检索资料，使用query查询本地资料的标题和内容，返回匹配的所有资料",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "核心检索关键词，例如session、Agent、todo"},
            },

            "required": ["query"],
            "additionalProperties": False,
        },
    },
}


def todo(session: dict, action: str, text: str = "", task_id: int | None = None) -> dict:
    """在当前session中新增、列出或完成待办。session由Runtime传入。"""
    todos = session["todos"]

    if action == "add":
        if not text.strip():
            raise ValueError("新增待办需要非空text")

        task = ({
            "id": len(todos) + 1,
            "text": text,
            "done": False,
        })
        todos.append(task)

        return {"task": task}

    elif action == "list":
        return {"tasks": todos}

    elif action == "complete":
        for task in todos:
            if task["id"] == task_id:
                task["done"] = True
                return {"task": task}

        raise ValueError("未找到对应待办")

    raise ValueError("不支持的待办操作")


TODO_DEFINITION = {
    "type": "function",
    "function": {
        "name": "todo",
        "description": "管理当前会话的待办。add新增，list列出全部，complete完成指定id的待办。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["add", "list", "complete"]},
                "text": {"type": "string", "description": "新增待办的内容，action为add时提供"},
                "task_id": {"type": "integer", "description": "要完成的待办id，action为complete时提供"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}


TOOL_REGISTRY = {
    "calculator": {
        "definition": CALCULATOR_DEFINITION,
        "handler": calculator,
    },

    "search":{
        "definition": SEARCH_DEFINITION,
        "handler": search,
    },

    "todo":{
        "definition": TODO_DEFINITION,
        "handler": todo,
        "needs_session": True,
    }
}
