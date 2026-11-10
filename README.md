# Minimal Agent

用 Python 标准库实现的命令行 Agent。核心 Runtime 自行实现，使用真实 LLM API，根据工具 Schema 决定直接回答或调用工具。

## 运行

需要 Python 3.10+，无第三方依赖。在仓库根目录执行：

```powershell
Copy-Item settings.example.json settings.local.json
```

填写配置中的 `base_url`、`model`、`api_key`，然后运行：

```powershell
python main.py
```

服务需要兼容 `/chat/completions`，所选模型需要支持工具调用。`base_url` 填到版本路径，例如 `https://api.moonshot.cn/v1`，不包含 `/chat/completions`。`MOONSHOT_API_KEY` 环境变量存在且非空时，优先使用它作为密钥。

| 命令 | 行为 |
| --- | --- |
| `/session window2` | 创建或切换到指定会话 |
| `/session window1` | 返回原会话继续对话 |
| `/clear` | 清除当前会话消息和摘要，保留待办，立即保存 |
| `/exit` | 保存并退出 |

工具包括 calculator（加减乘除）、search（固定演示资料的关键词检索，明确标记 mock）和 todo（新增、列出、完成待办）。例如：

```text
用工具计算137乘29。
把刚才的结果再乘以2。
在演示资料中搜索session。
新增待办：复习Agent循环。
列出待办。
完成id为1的待办。
```

## 设计

一次任务的流程是：用户输入 → 构建 context → 请求模型 → 解析工具调用 → 校验并执行 → 回填工具结果 → 再次请求模型或返回答案。

| 文件 | 职责 |
| --- | --- |
| main.py | 交互命令、会话切换和保存 |
| runtime.py | 模型与工具循环、结果回填、请求次数限制 |
| llm.py | HTTP API 请求与响应读取 |
| tools.py | 工具 Schema、实现和注册表 |
| validation.py | 当前工具使用的基础参数规则校验 |
| sessions.py | 会话创建、清理、JSON 保存和恢复 |
| context.py | 轮次分组、上下文组装、增量摘要 |
| trace_log.py | JSONL 工具执行日志 |

工具注册表关联 Schema 与 Python handler，LLM 只能看到声明。todo 所属的 session 由 Runtime 注入，不允许模型通过参数选择别的会话。参数错误、未知工具、非法 JSON 和除零等错误会转成对应的工具结果，模型可以据此调整或解释。

默认每次用户输入最多执行5次主循环模型请求，摘要请求及网络重发单独产生 HTTP 请求。网络失败时保留已执行的工具结果并返回说明，入口仍会保存状态；稍后输入“继续”可以基于已有结果续聊。

响应中的 `content` 用于最终答复，`tool_calls` 用于执行工具，参数通过 JSON 解析。每条结果通过 `tool_call_id` 对应调用。服务商若返回推理字段，完整 assistant 消息会一并保存；没有返回的内部思考不作推测。

## Memory 与 context

每个 session 独立持有 `messages`、`todos`、`summary` 和 `summary_turns`。每轮返回后将会话集合写入 `data/sessions.json`，先写临时文件再替换正式文件；启动时自动恢复。

**召回时机**：每次主循环请求模型之前，包括工具执行完毕后的下一次请求。**放置方式**：系统规则 → 标为历史记录的 assistant 摘要 → 尚未摘要的完整消息轮次。todo 状态不自动整份注入，而由模型通过工具按需读取。

context 序列化后超过6000字符时，把较早轮次合入已有摘要，默认保留最近3轮原文。轮次从 user 消息开始，包含该轮所有 assistant/tool 消息，避免截断工具配对。原始历史与待办不删除，摘要和覆盖进度持久化，相同历史不重复摘要。

这是基础压缩：6000字符是触发阈值，不是 token 硬上限。程序采用单进程串行执行和会话内记忆。模型摘要与最终文字可能失真；开发中出现过工具已列出待办、模型却回答为空的情况，原始状态与 trace 可用于核对。

## 执行日志

工具执行时追加 `logs/tool_calls.jsonl`。每次调用包含 `tool_start` 和 `tool_end`，记录 UTC 时间、session_id、turn_id、循环步数、tool_call_id、工具名、原始参数、结果、状态和毫秒耗时。

```powershell
Get-Content -LiteralPath logs/tool_calls.jsonl -Encoding utf8 -Tail 10
```

使用 `turn_id` 和 `tool_call_id` 配对开始与结束。已知工具错误也会记录。日志不进入模型输入，`/clear` 不删除日志。

## 测试

不需要密钥即可运行离线测试：

```powershell
python -m unittest discover -s tests -v
```

| 测试文件 | 覆盖内容 |
| --- | --- |
| test_tools.py | 工具注册、计算、mock 搜索、todo、参数拒绝与工具错误 |
| test_runtime.py | 直接回答及追问、多工具配对、循环上限、API 失败与恢复 |
| test_state_context.py | 会话隔离、保存恢复、按轮分组、增量压缩及复用 |
| test_cli_trace.py | `/clear` 立即保存并保留待办、成功与失败的文件 trace |
| test_llm.py | 请求 payload、响应字段、HTTP 错误、TLS 重试及次数限制 |
| test_live.py | 可选的真实 API 计算与工具追问 |

离线测试使用确定的模型响应检查控制流。配置好本地密钥后，可运行真实 API 测试：

```powershell
$env:AGENT_LIVE_TEST = "1"
python -m unittest discover -s tests -p test_live.py -v
Remove-Item Env:AGENT_LIVE_TEST
```

手动核对：在 window1 新增并完成待办，切换 window2 应独立；退出重启后分别续聊；`/clear` 后旧聊天清除，工具仍可列出原待办。摘要内容的事实准确性需要结合实际输出检查。

## 开发记录

见 [PROMPTS.md](PROMPTS.md)，包括总体约束、四个开发阶段及排错和需求补充。配置示例不含密钥；本地配置、会话数据、日志和缓存均已加入 `.gitignore`。
