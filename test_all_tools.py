"""
Автотест всех инструментов qwen-idea-mcp.
Обходит Qwen-клиент, подключается к SSE-демону напрямую.
Использование: .venv/Scripts/activate  ->  python test_all_tools.py
"""
import asyncio
import os
import sys
import time
from pathlib import Path

import anyio
from mcp import ClientSession
from mcp.client.sse import sse_client

URL = os.environ.get("MCP_URL", "http://127.0.0.1:8765/sse")
PROJECT_ROOT = r"C:\Users\Home\Desktop\skulkevo-template-1.21.1"
TEST_FILE = "src/main/java/com/example/sculkecho/_mcp_autotest.java"


def ok(name, text):
    preview = (text or "").splitlines()[0][:120] if text else "(empty)"
    print(f"  ✅ {name:<24} → {preview}")


def fail(name, text):
    print(f"  ❌ {name:<24} → {(text or '')[:200]}")


async def call(session: ClientSession, name: str, **kw) -> str:
    res = await session.call_tool(name, {k: v for k, v in kw.items() if v is not None})
    if res.content and hasattr(res.content[0], "text"):
        return res.content[0].text
    return repr(res)


async def main():
    print(f"Connecting to {URL} ...")
    async with sse_client(URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            print(f"Found {len(tools)} tools: {', '.join(t.name for t in tools)}\n")

            # --- безопасные read-only инструменты ---
            print("[1/6] Базовые инструменты")
            ok("ping", await call(session, "ping"))
            ok("project_brief", await call(session, "project_brief"))
            ok("list_files", await call(session, "list_files", rel_dir=""))
            ok("read_file", await call(session, "read_file", rel_path="build.gradle"))
            ok("grep", await call(session, "grep", pattern="public class"))
            ok("recent_activity", await call(session, "recent_activity", lines=5))

            # --- настройка ---
            print("\n[2/6] Настройка (безопасно, перезаписывает mod_config.json)")
            ok("configure", await call(session, "configure", project_root=PROJECT_ROOT))
            ok("ping после configure", await call(session, "ping"))

            # --- файловые правки (на тестовом файле, потом чистим) ---
            print("\n[3/6] Файловые правки (на тестовом файле)")
            ok("write_file", await call(session, "write_file", rel_path=TEST_FILE,
                                        content="// autotest\nclass Autotest {}"))
            ok("read_file после write", await call(session, "read_file", rel_path=TEST_FILE))
            ok("patch_file", await call(session, "patch_file", rel_path=TEST_FILE,
                                        old_text="class Autotest", new_text="class Autotest2"))
            ok("delete_file", await call(session, "delete_file", rel_path=TEST_FILE))

            # --- gradle ---
            print("\n[4/6] Сборка (compileJava — только проверка компиляции, игру не запускает)")
            gradle_res = await call(session, "run_gradle", task="compileJava")
            if "exit=0" in gradle_res:
                ok("run_gradle compileJava", gradle_res)
            else:
                fail("run_gradle compileJava", gradle_res)

            # --- GUI ---
            print("\n[5/6] GUI")
            ok("get_mouse_position", await call(session, "get_mouse_position"))
            ok("list_windows", await call(session, "list_windows", filter_text=""))
            ok("wait", await call(session, "wait", seconds=1))
            # screenshot в файл
            ss_path = str(Path(__file__).parent / "autotest_screenshot.png")
            ok("screenshot", await call(session, "screenshot", target="screen", save_path=ss_path))

            # --- анализ модов ---
            print("\n[6/6] Анализ")
            ok("probe_mod (папка)", await call(session, "probe_mod", target=PROJECT_ROOT))

            # --- состояние клиента (безопасно, если не запущен) ---
            ok("client_status", await call(session, "client_status"))
            ok("stop_client", await call(session, "stop_client"))

            print(f"\n✅ Автотест завершён. Скриншот: {ss_path}")
            print(f"Проверь также server_debug.log: там должны быть START/END для всех инструментов.")


if __name__ == "__main__":
    anyio.run(main, backend="asyncio")