"""交互入口：读取输入、调用运行层、展示回复。"""

from runtime import run_turn
from sessions import clear_history, get_session, load_sessions, save_sessions


def main() -> None:
    sessions = load_sessions()
    current_session_id = "window1"
    print("最小 Agent：对话、工具、会话与基础压缩。输入 /exit 退出。")
    print(f"已恢复 {len(sessions)} 个会话。")
    print("当前会话：window1；输入 /session window2 切换会话。")
    print("输入 /clear 清除当前会话的消息与摘要，保留待办。")

    while True:
        user_input = input(f"[{current_session_id}] 你：").strip()

        if user_input == "/exit":
            save_sessions(sessions)
            break
        if not user_input:
            continue
        if user_input == "/clear":
            clear_history(get_session(sessions, current_session_id))
            save_sessions(sessions)
            print("当前会话的消息与摘要已清除，待办已保留。")
            continue
        if user_input == "/session":
            print("用法：/session 会话名，例如 /session window2")
            continue
        if user_input.startswith("/session "):
            current_session_id = user_input.split(maxsplit=1)[1].strip()
            print(f"已切换到：{current_session_id}")
            continue

        session = get_session(sessions, current_session_id)
        answer = run_turn(session, user_input)
        save_sessions(sessions)
        print(f"助手：{answer}")


if __name__ == "__main__":
    main()
