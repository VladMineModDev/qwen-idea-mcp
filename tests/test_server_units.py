"""Оффлайн-юниты для qwen-idea-mcp: безопасность путей, детект модов, декодирование."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server as S


def test_safe_path_inside_project():
    p = S._safe_path("src/main/java")
    assert p == (S.PROJECT_ROOT / "src/main/java").resolve()


def test_safe_path_escape_rejected():
    with pytest.raises(ValueError):
        S._safe_path("../../etc/passwd")


def test_writable_denies_gradlew():
    with pytest.raises(ValueError):
        S._writable("gradlew.bat")


def test_writable_denies_service_dirs():
    with pytest.raises(ValueError):
        S._writable(".idea/workspace.xml")


def test_probe_detects_neoforge(tmp_path):
    (tmp_path / "META-INF").mkdir()
    (tmp_path / "META-INF" / "neoforge.mods.toml").write_text(
        '[[mods]]\nmodId="demo"\nversion="1.0"\n', encoding="utf-8")
    res = S._probe(S._probe_reader_dir(tmp_path))
    assert res[0]["loader"] == "neoforge"
    assert res[0]["modId"] == "demo"


def test_probe_detects_fabric(tmp_path):
    (tmp_path / "fabric.mod.json").write_text(
        '{"id": "demof", "version": "2.0", "depends": {"minecraft": ">=1.21"}}',
        encoding="utf-8")
    res = S._probe(S._probe_reader_dir(tmp_path))
    assert res[0]["loader"] == "fabric"
    assert res[0]["minecraft"] == ">=1.21"


def test_probe_unknown(tmp_path):
    assert S._probe(S._probe_reader_dir(tmp_path)) == [{"loader": "unknown"}]


def test_decode_bytes_cp1251_fallback():
    assert S._decode_bytes("привет".encode("cp1251")) == "привет"


def test_decode_bytes_utf8_first():
    assert S._decode_bytes("привет".encode("utf-8")) == "привет"


EXPECTED_HINTS = {
    "ping": (True, False, True, False),
    "configure": (False, False, True, False),
    "list_files": (True, False, True, False),
    "read_file": (True, False, True, False),
    "write_file": (False, False, True, False), 
    "patch_file": (False, False, True, False), 
    "delete_file": (False, False, True, False),
    "grep": (True, False, True, False),
    "run_gradle": (False, False, False, True),
    "client_status": (True, False, True, False),
    "stop_client": (False, False, True, True), 
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
    "ai_decisions": (True, False, True, False),
}


@pytest.mark.parametrize("name,hints", sorted(EXPECTED_HINTS.items()))
def test_every_tool_has_explicit_hints(name, hints):
    """Каждый инструмент зарегистрирован и несёт все 4 хинта явно (M8ven/OpenAI)."""
    tool = S.mcp._tool_manager.get_tool(name)
    assert tool is not None, f"tool {name} not registered"
    ann = tool.annotations
    assert ann is not None, f"{name}: annotations missing"
    got = (ann.readOnlyHint, ann.destructiveHint,
           ann.idempotentHint, ann.openWorldHint)
    assert got == hints, f"{name}: hints {got} != expected {hints}"