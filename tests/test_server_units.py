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


def test_all_tools_have_annotations():
    """Главный тест для M8ven: у каждого инструмента все 4 хинта заданы явно."""
    for tool in S.mcp._tool_manager.list_tools():
        ann = tool.annotations
        assert ann is not None, f"{tool.name}: no annotations"
        for hint in ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"):
            assert getattr(ann, hint) is not None, f"{tool.name}: {hint} is None"