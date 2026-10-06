"""Заменяет annotations=A_КОНСТАНТА на явные литералы ToolAnnotations(...)
   ради статических аудиторов (M8ven / OpenAI directory)."""
import re
from pathlib import Path

MAP = {
    "ping": (True, False, True, False),
    "configure": (False, False, True, False),
    "list_files": (True, False, True, False),
    "read_file": (True, False, True, False),
    "write_file": (False, True, True, False),
    "patch_file": (False, True, False, False),
    "delete_file": (False, True, False, False),
    "grep": (True, False, True, False),
    "run_gradle": (False, False, False, True),
    "client_status": (True, False, True, False),
    "stop_client": (False, True, False, True),
    "get_logs": (True, False, True, False),
    "screenshot": (True, False, True, True),
    "focus_window": (False, False, True, True),
    "maximize_window": (False, False, True, True),
    "list_windows": (True, False, True, True),
    "press_key": (False, False, False, True),
    "type_text": (False, False, False, True),
    "click_at": (False, False, False, True),
    "get_mouse_position": (True, False, True, True),
    "wait": (True, False, True, False),
    "open_idea": (False, False, False, True),
    "show_in_idea": (False, False, True, True),
    "recent_activity": (True, False, True, False),
    "ai_events": (True, False, True, False),
    "project_brief": (True, False, True, False),
    "probe_mod": (True, False, True, False),
}

lines = Path("server.py").read_text(encoding="utf-8").splitlines(keepends=True)
out, replaced = [], 0
for i, line in enumerate(lines):
    if re.match(r"\s*@mcp\.tool\(annotations=A_\w+\)\s*$", line):
        j = i + 1
        while j < len(lines) and not lines[j].strip().startswith("def "):
            j += 1
        dm = re.match(r"\s*def (\w+)", lines[j]) if j < len(lines) else None
        if dm and dm.group(1) in MAP:
            ro, de, idm, ow = MAP[dm.group(1)]
            indent = line[:len(line) - len(line.lstrip())]
            line = (f"{indent}@mcp.tool(annotations=ToolAnnotations("
                    f"readOnlyHint={ro}, destructiveHint={de}, "
                    f"idempotentHint={idm}, openWorldHint={ow}))\n")
            replaced += 1
    out.append(line)
Path("server.py").write_text("".join(out), encoding="utf-8")
print(f"replaced {replaced} decorators (expected 27)")