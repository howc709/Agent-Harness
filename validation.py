"""检查当前工具Schema使用的基础参数规则。"""


def validate_arguments(arguments, schema: dict) -> None:
    """验证失败抛ValueError；通过时直接结束，不返回计算结果。"""
    if not isinstance(arguments, dict):
        raise ValueError("工具参数必须是JSON对象")

    properties = schema["properties"]
    for name in schema.get("required", []):
        if name not in arguments:
            raise ValueError(f"缺少参数：{name}")

    allowed_types = {
        "string": [str],
        "number": [int, float],
        "integer": [int],
    }
    for name, value in arguments.items():
        if name not in properties:
            if schema.get("additionalProperties", True) is False:
                raise ValueError(f"不允许的参数：{name}")
            continue

        rule = properties[name]
        expected_type = rule["type"]

        if type(value) not in allowed_types[expected_type]:
            raise ValueError(f"{name}应为{expected_type}类型")

        if "enum" in rule and value not in rule["enum"]:
            raise ValueError(f"参数{name}不在允许值中：{rule['enum']}")
