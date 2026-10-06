"""
qwen-idea-mcp v1.7 — MCP-сервер для ИИ-разработки Minecraft-модов (NeoForge/Fabric/Forge)
через IntelliJ IDEA: файлы с бэкапами, Gradle, логи/краш-репорты, GUI-автоматизация,
детект формата мода (probe_mod), журнал событий для IDEA-плагина (ai_events.jsonl).
Все инструменты несут MCP-аннотации (readOnly/destructive/idempotent/openWorld).
Конфигурация: mod_config.json (или env QWEN_MCP_CONFIG), автодетект JAVA_HOME и IDEA.
Транспорты: python server.py sse | streamable-http | stdio
"""
import base64
import functools
import inspect
import json
import os
import re
import shutil
import subprocess
import time
import tomllib
import zipfile
from pathlib import Path

import anyio
import mss
import pyautogui
import pygetwindow as gw
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

# ---------- конфигурация: в коде нет личных путей ----------
SERVER_ROOT = Path(__file__).resolve().parent
BACKUP_ROOT = SERVER_ROOT / "backups"
LOG_ROOT = SERVER_ROOT / "logs"
STATE_FILE = SERVER_ROOT / "state.json"
DEBUG_LOG = SERVER_ROOT / "server_debug.log"
EVENTS_FILE = SERVER_ROOT / "ai_events.jsonl"
CONFIG_FILE = Path(os.environ.get("QWEN_MCP_CONFIG",
                                  str(SERVER_ROOT / "mod_config.json")))

# ---------- MCP-аннотации инструментов (spec 2025-06-18) ----------
A_READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                         idempotentHint=True, openWorldHint=False)
A_READ_OPEN = ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                              idempotentHint=True, openWorldHint=True)
A_CONF = ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                         idempotentHint=True, openWorldHint=False)
A_OVERWRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                              idempotentHint=True, openWorldHint=False)
A_DESTR = ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                          idempotentHint=False, openWorldHint=False)
A_DESTR_OPEN = ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                               idempotentHint=False, openWorldHint=True)
A_OPEN_ACT = ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                             idempotentHint=False, openWorldHint=True)
A_OPEN_IDEM = ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                              idempotentHint=True, openWorldHint=True)


def _detect_java_home() -> str:
    env = os.environ.get("JAVA_HOME", "")
    if env and Path(env).is_dir():
        return env
    g = Path.home() / ".gradle" / "jdks"
    if g.is_dir():
        for d in sorted((x for x in g.iterdir() if x.is_dir()), reverse=True):
            if (d / "bin" / "java.exe").is_file():
                return str(d)
    return ""


def _detect_idea_exe() -> str:
    custom = os.environ.get("IDEA_PATH", "")
    if custom and Path(custom).is_file():
        return custom
    roots = [Path(r"C:\Program Files\JetBrains"),
             Path.home() / "AppData" / "Local" / "JetBrains" / "Toolbox" / "apps"]
    for base in roots:
        if not base.is_dir():
            continue
        for d in sorted(base.glob("**/IntelliJ IDEA*"), reverse=True):
            cand = d / "bin" / "idea64.exe"
            if cand.is_file():
                return str(cand)
    return ""


def _load_config() -> dict:
    cfg = {
        "loader": "neoforge",
        "project_root": "",
        "java_home": "",
        "idea_path": "",
        "host": "127.0.0.1",
        "port": 8765,
        "logs": {
            "client_latest": "run/client/logs/latest.log",
            "client_debug": "run/client/logs/debug.log",
            "crash_dirs": ["run/client/crash-reports", "run/crash-reports"],
        },
    }
    if CONFIG_FILE.is_file():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    if not cfg["java_home"]:
        cfg["java_home"] = _detect_java_home()
    if not cfg["idea_path"]:
        cfg["idea_path"] = _detect_idea_exe()
    return cfg


CFG = _load_config()
PROJECT_ROOT = (Path(CFG["project_root"]).resolve()
                if CFG["project_root"] else SERVER_ROOT)
DEFAULT_JAVA_HOME = CFG["java_home"]

SKIP_DIRS = {".git", ".gradle", ".idea", "build", "run", "out"}
WRITE_DENY_DIRS = SKIP_DIRS | {"gradle"}
WRITE_DENY_FILES = {"gradlew", "gradlew.bat"}

SERVER_INSTRUCTIONS = (
    "MCP-сервер разработки Minecraft-мода (NeoForge/Fabric) в IntelliJ IDEA. "
    "Первый запуск: если ping показывает WARNING или чужой путь — спроси у пользователя "
    "абсолютный путь к проекту мода и вызови configure(project_root=...). "
    "Основной цикл: grep/read_file -> patch_file/write_file -> run_gradle('compileJava') -> "
    "stop_client() -> run_gradle('runClient', background=True) -> wait(45) -> "
    "get_logs(source='run', filter_regex='ERROR|Exception') -> screenshot(target='minecraft'). "
    "Правила: перед patch_file всегда read_file; runClient ТОЛЬКО с background=True; "
    "перед новым runClient всегда stop_client(); краш-репорты с mode='head'; "
    "бэкапы правок автоматические; после важной правки вызывай show_in_idea."
)

mcp = FastMCP("qwen-idea-mcp", host=CFG["host"], port=CFG["port"],
              instructions=SERVER_INSTRUCTIONS)


# ---------- чёрный ящик и события ----------

def _dbg(msg: str):
    with open(DEBUG_LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def _emit_event(tool: str, file: str = "", lines=None, summary: str = "",
                status: str = "ok"):
    """Структурное событие для IDEA-плагина и журнала (контракт ai_events.jsonl)."""
    try:
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "tool": tool,
               "file": file, "lines": lines, "summary": summary[:300],
               "status": status}
        with open(EVENTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def traced(fn):
    if inspect.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def awrapper(*a, **kw):
            _dbg(f"START {fn.__name__} kw={kw}")
            try:
                r = await fn(*a, **kw)
                _dbg(f"END   {fn.__name__}")
                return r
            except Exception as e:
                _dbg(f"EXC   {fn.__name__}: {type(e).__name__}: {e}")
                raise
        return awrapper

    @functools.wraps(fn)
    def wrapper(*a, **kw):
        _dbg(f"START {fn.__name__} kw={kw}")
        try:
            r = fn(*a, **kw)
            _dbg(f"END   {fn.__name__}")
            return r
        except Exception as e:
            _dbg(f"EXC   {fn.__name__}: {type(e).__name__}: {e}")
            raise
    return wrapper


# ---------- helpers ----------

def _safe_path(rel: str) -> Path:
    target = (PROJECT_ROOT / rel).resolve()
    if not str(target).startswith(str(PROJECT_ROOT)):
        raise ValueError(f"Path escapes project root: {rel}")
    return target


def _writable(rel: str) -> Path:
    p = _safe_path(rel)
    parts = p.relative_to(PROJECT_ROOT).parts
    if any(part in WRITE_DENY_DIRS for part in parts[:-1]):
        raise ValueError(f"Write denied (service dir): {rel}")
    if p.name in WRITE_DENY_FILES:
        raise ValueError(f"Write denied (critical file): {p.name}")
    return p


def _backup(p: Path) -> str:
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    rel = str(p.relative_to(PROJECT_ROOT)).replace("\\", "__").replace("/", "__")
    dst = BACKUP_ROOT / f"{stamp}__{rel}"
    shutil.copy2(p, dst)
    return str(dst)


def _load_state() -> dict:
    if STATE_FILE.is_file():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_state(st: dict):
    STATE_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def _pid_alive(pid: int) -> bool:
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                         capture_output=True, stdin=subprocess.DEVNULL).stdout
    return str(pid).encode() in out


def _decode_bytes(b: bytes) -> str:
    """Пробуем UTF-8, fallback на cp1251 (Windows-консоли пишут кириллицу в cp1251)."""
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("cp1251", errors="replace")


# ---------- файлы ----------

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
@traced
def ping() -> str:
    """Проверка связи + состояние конфигурации."""
    msg = f"pong | loader={CFG['loader']} | project={PROJECT_ROOT}"
    if not CFG["project_root"]:
        msg += (" | WARNING: project_root not set — спроси у пользователя путь "
                "к проекту мода и вызови configure(project_root=...)")
    if not DEFAULT_JAVA_HOME:
        msg += " | WARNING: java_home not detected — задай в mod_config.json или JAVA_HOME"
    return msg


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False))
@traced
def configure(project_root: str, java_home: str = "", idea_path: str = "",
              loader: str = "") -> str:
    """Первичная настройка (один раз): сохранить пути в mod_config.json и применить
    без перезапуска демона. ИИ: спроси у пользователя абсолютный путь к проекту мода
    и вызови этот инструмент."""
    global PROJECT_ROOT, DEFAULT_JAVA_HOME
    p = Path(project_root).resolve()
    if not p.is_dir():
        return f"ERROR: directory not found: {project_root}"
    warn = ""
    if not (p / "gradlew.bat").is_file() and not (p / "gradlew").is_file():
        warn = (" WARNING: в папке нет gradlew — точно корень проекта мода? "
                "Конфиг сохранён, но gradle-задачи не запустятся.")
    data = {}
    if CONFIG_FILE.is_file():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["project_root"] = str(p)
    if java_home:
        data["java_home"] = java_home
    if idea_path:
        data["idea_path"] = idea_path
    if loader:
        data["loader"] = loader
    CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    new = _load_config()
    CFG.clear()
    CFG.update(new)
    PROJECT_ROOT = Path(CFG["project_root"]).resolve()
    DEFAULT_JAVA_HOME = CFG["java_home"]
    _emit_event("configure", "", None, f"project_root={p}")
    return (f"OK: config saved to {CONFIG_FILE} | project={PROJECT_ROOT} | "
            f"java={DEFAULT_JAVA_HOME or 'NOT DETECTED'} | loader={CFG['loader']}.{warn}")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
@traced
def list_files(rel_dir: str = "", pattern: str = "**/*") -> str:
    """Список файлов в директории проекта (относительно корня)."""
    base = _safe_path(rel_dir)
    if not base.exists():
        return f"Directory not found: {rel_dir}"
    items = []
    for p in base.glob(pattern):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        rel = p.relative_to(PROJECT_ROOT)
        items.append(f"[{'D' if p.is_dir() else 'F'}] {rel}")
    return "\n".join(items[:500]) or "(empty)"


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
@traced
def read_file(rel_path: str, max_bytes: int = 200_000) -> str:
    """Прочитать содержимое файла проекта."""
    p = _safe_path(rel_path)
    if not p.is_file():
        return f"File not found: {rel_path}"
    data = p.read_bytes()
    text = data[:max_bytes].decode("utf-8", errors="replace")
    if len(data) > max_bytes:
        text += f"\n\n...[truncated, total {len(data)} bytes]"
    return text


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False))
@traced
def write_file(rel_path: str, content: str) -> str:
    """Создать новый файл или полностью перезаписать существующий (старая версия уходит в backup)."""
    p = _writable(rel_path)
    existed = p.is_file()
    b = _backup(p) if existed else None
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    msg = f"OK: {'updated' if existed else 'created'} {rel_path} ({len(content)} chars)"
    if b:
        msg += f" | backup: {b}"
    _emit_event("write_file", rel_path, [1, content.count("\n") + 1],
                "created" if not existed else "updated")
    return msg


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
@traced
def patch_file(rel_path: str, old_text: str, new_text: str, replace_all: bool = False) -> str:
    """Точечная замена фрагмента текста. Ошибка, если фрагмент не найден или неоднозначен."""
    p = _writable(rel_path)
    if not p.is_file():
        return f"File not found: {rel_path}"
    src = p.read_text(encoding="utf-8")
    count = src.count(old_text)
    if count == 0:
        return f"ERROR: fragment not found in {rel_path}. Проверь точное совпадение с отступами."
    if count > 1 and not replace_all:
        return f"ERROR: fragment found {count} times. Уточни контекст или replace_all=True."
    idx = src.find(old_text)
    start_line = src[:idx].count("\n") + 1
    end_line = start_line + old_text.count("\n")
    b = _backup(p)
    p.write_text(src.replace(old_text, new_text) if replace_all
                 else src.replace(old_text, new_text, 1), encoding="utf-8")
    _emit_event("patch_file", rel_path, [start_line, end_line],
                f"replaced {count if replace_all else 1} occurrence(s)")
    return f"OK: replaced {count if replace_all else 1} occurrence(s) in {rel_path} | backup: {b}"


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
@traced
def delete_file(rel_path: str) -> str:
    """Удалить файл (сначала копия в backup)."""
    p = _writable(rel_path)
    if not p.is_file():
        return f"File not found: {rel_path}"
    b = _backup(p)
    p.unlink()
    _emit_event("delete_file", rel_path, None, "deleted")
    return f"OK: deleted {rel_path} | backup: {b}"


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
@traced
def grep(pattern: str, rel_dir: str = "", file_glob: str = "*.java",
         case_sensitive: bool = False, max_results: int = 50) -> str:
    """Поиск по коду (regex). Возвращает файл:строка: содержимое строки."""
    base = _safe_path(rel_dir)
    rx = re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)
    out = []
    for p in base.rglob(file_glob):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            if rx.search(line):
                out.append(f"{p.relative_to(PROJECT_ROOT)}:{i}: {line.strip()[:160]}")
                if len(out) >= max_results:
                    return "\n".join(out) + f"\n...[limit {max_results}]"
    return "\n".join(out) or "Nothing found"


# ---------- gradle и логи ----------

@mcp.tool(annotations=A_OPEN_ACT)
@traced
async def run_gradle(task: str, background: bool = False, timeout: int = 900,
                     java_home: str = "") -> str:
    """Запустить задачу gradle (build, compileJava, runClient...).
    background=True — отделить процесс (для runClient), вывод идёт в logs/run_*.log."""
    jh = java_home or DEFAULT_JAVA_HOME
    if not jh:
        return "ERROR: java_home not set: задай в mod_config.json или переменную JAVA_HOME"
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["JAVA_HOME"] = jh
    cmd = ["cmd", "/c", "gradlew.bat", *task.split()]
    log_path = LOG_ROOT / f"{'run' if background else 'gradle'}_{time.strftime('%Y%m%d-%H%M%S')}.log"
    fh = open(log_path, "wb")
    try:
        proc = subprocess.Popen(
            cmd, cwd=PROJECT_ROOT, stdout=fh, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, env=env,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    except Exception as e:
        fh.close()
        return f"ERROR launching gradle: {e}"

    if background:
        _save_state({"pid": proc.pid, "log": str(log_path), "task": task,
                     "started": time.strftime("%Y%m%d-%H%M%S")})
        _emit_event("run_gradle", "", None, f"background {task} pid={proc.pid}")
        return (f"OK: launched '{task}' in background, pid={proc.pid}, log={log_path}. "
                f"Следи через get_logs(source='run').")

    def _wait() -> int:
        try:
            return proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True, stdin=subprocess.DEVNULL)
            return -1

    code = await anyio.to_thread.run_sync(_wait)
    fh.close()
    out = _decode_bytes(log_path.read_bytes())
    tail = "\n".join(out.splitlines()[-120:])
    hint = ""
    if code != 0 and "JAVA_HOME" in out:
        hint = f"\n[HINT] Проблема с JAVA_HOME ({jh})."
    if code != 0 and "not recognized" in out:
        hint = f"\n[HINT] gradlew.bat не найден — проверь project_root в mod_config.json."
    _emit_event("run_gradle", "", None, f"{task} exit={code}",
                "ok" if code == 0 else "error")
    return f"exit={code} | full log: {log_path}\n--- tail ---\n{tail}{hint}"


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
@traced
def client_status() -> str:
    """Жив ли фоновый процесс runClient."""
    st = _load_state()
    if not st.get("pid"):
        return "No background client launched."
    return (f"task={st.get('task')} pid={st['pid']} "
            f"alive={_pid_alive(st['pid'])} log={st.get('log')}")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True))
@traced
def stop_client() -> str:
    """Остановить фоновый runClient (вместе с дочерними процессами)."""
    st = _load_state()
    if not st.get("pid"):
        return "No background client to stop."
    subprocess.run(["taskkill", "/PID", str(st["pid"]), "/T", "/F"],
                   capture_output=True, stdin=subprocess.DEVNULL)
    _save_state({})
    return f"OK: killed pid {st['pid']} tree."


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
@traced
def get_logs(source: str = "latest", lines: int = 150, mode: str = "tail",
             filter_regex: str = "") -> str:
    """Читает логи. source: latest | debug | crash | run.
    latest/debug — логи клиента; crash — свежий краш-репорт (читай с mode='head');
    run — лог фонового runClient. filter_regex — показать только строки с шаблоном."""
    lg = CFG["logs"]
    if source == "latest":
        p = PROJECT_ROOT / lg["client_latest"]
    elif source == "debug":
        p = PROJECT_ROOT / lg["client_debug"]
    elif source == "crash":
        dirs = [PROJECT_ROOT / d for d in lg["crash_dirs"]]
        cands = sorted((f for d in dirs if d.is_dir() for f in d.glob("crash-*.txt")),
                       key=lambda f: f.stat().st_mtime)
        if not cands:
            return "No crash reports found."
        p = cands[-1]
    elif source == "run":
        st = _load_state()
        p = Path(st["log"]) if st.get("log") else None
        if p is None or not p.is_file():
            logs = sorted(LOG_ROOT.glob("run_*.log"), key=lambda f: f.stat().st_mtime)
            if not logs:
                return "No background run logs yet."
            p = logs[-1]
    else:
        return f"Unknown source: {source}"
    if not p.is_file():
        return f"Log not found: {p}"
    ls = _decode_bytes(p.read_bytes()).splitlines()
    if filter_regex:
        rx = re.compile(filter_regex, re.IGNORECASE)
        ls = [l for l in ls if rx.search(l)]
    sel = ls[-lines:] if mode == "tail" else ls[:lines]
    return f"[{p.name}] shown {len(sel)} of {len(ls)} lines (mode={mode})\n" + "\n".join(sel)


# ---------- GUI ----------

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
@traced
def screenshot(target: str = "minecraft", save_path: str = "") -> str:
    """Скриншот окна (target: 'minecraft' | 'idea' | 'screen' | подстрока заголовка).
    save_path — куда сохранить PNG; если пусто, возвращается base64."""
    try:
        win = None
        if target != "screen":
            key = {"minecraft": "Minecraft", "idea": "IntelliJ IDEA"}.get(target, target)
            windows = gw.getWindowsWithTitle(key)
            if not windows:
                return f"ERROR: window '{key}' not found."
            win = windows[0]
        with mss.mss() as sct:
            if win:
                monitor = {"top": win.top, "left": win.left,
                           "width": win.width, "height": win.height}
            else:
                monitor = sct.monitors[0]
            img = sct.grab(monitor)
        if save_path:
            p = Path(save_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            mss.tools.to_png(img.rgb, img.size, output=str(p))
            return f"OK: screenshot saved to {p} ({img.width}x{img.height})"
        png_data = mss.tools.to_png(img.rgb, img.size)
        return f"data:image/png;base64,{base64.b64encode(png_data).decode()}"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True))
@traced
def focus_window(title: str) -> str:
    """Вывести окно на передний план по заголовку."""
    windows = gw.getWindowsWithTitle(title)
    if not windows:
        return f"ERROR: Window with title '{title}' not found."
    win = windows[0]
    try:
        if win.isMinimized:
            win.restore()
        win.activate()
        return f"OK: focused '{win.title}' ({win.width}x{win.height} at {win.left},{win.top})"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True))
@traced
def maximize_window(title: str) -> str:
    """Развернуть окно на весь экран."""
    windows = gw.getWindowsWithTitle(title)
    if not windows:
        return f"ERROR: Window with title '{title}' not found."
    win = windows[0]
    try:
        if not win.isMaximized:
            win.maximize()
        return f"OK: maximized '{win.title}'"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
@traced
def list_windows(filter_text: str = "") -> str:
    """Список заголовков открытых окон (опционально фильтр по подстроке)."""
    titles = [t for t in gw.getAllTitles() if isinstance(t, str) and t.strip()]
    if filter_text:
        titles = [t for t in titles if filter_text.lower() in t.lower()]
    return "\n".join(titles[:50]) or "(no windows)"


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
@traced
def press_key(keys: str, interval: float = 0.1) -> str:
    """Нажать клавишу или комбинацию (например: 'f5', 'ctrl+s', 'enter')."""
    try:
        parts = [k.strip() for k in keys.lower().split("+")]
        pyautogui.hotkey(*parts, interval=interval)
        return f"OK: pressed {keys}"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
@traced
def type_text(text: str, interval: float = 0.03) -> str:
    """Набрать текст с клавиатуры (команды в игре, поля ввода). Только латиница/ASCII."""
    try:
        pyautogui.write(text, interval=interval)
        return f"OK: typed {len(text)} chars"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
@traced
def click_at(x: int, y: int, button: str = "left", clicks: int = 1) -> str:
    """Кликнуть по координатам экрана (button: 'left' | 'right' | 'middle')."""
    try:
        pyautogui.click(x=x, y=y, button=button, clicks=clicks)
        return f"OK: clicked ({x}, {y}) button={button} clicks={clicks}"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
@traced
def get_mouse_position() -> str:
    """Получить текущие координаты мыши."""
    x, y = pyautogui.position()
    return f"Mouse at ({x}, {y})"


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
@traced
def wait(seconds: float = 5.0) -> str:
    """Пауза между действиями (ожидание загрузки мира и т.п.), максимум 120 сек."""
    time.sleep(min(seconds, 120.0))
    return f"OK: waited {seconds}s"


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
@traced
def open_idea(project: str = "") -> str:
    """Открыть проект в IntelliJ IDEA (путь из конфига / автодетект)."""
    root = Path(project) if project else PROJECT_ROOT
    idea_exe = Path(CFG["idea_path"]) if CFG["idea_path"] else None
    if idea_exe is None or not idea_exe.is_file():
        return ("ERROR: IDEA not found. Задай idea_path в mod_config.json "
                "или переменную окружения IDEA_PATH")
    subprocess.Popen([str(idea_exe), str(root)], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=subprocess.DETACHED_PROCESS)
    return f"OK: opening IDEA for {root}"


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True))
@traced
def show_in_idea(rel_path: str, line: int = 0) -> str:
    """Открыть файл в запущенной IntelliJ IDEA (чтобы человек видел правку вживую)."""
    idea_exe = CFG["idea_path"]
    if not idea_exe or not Path(idea_exe).is_file():
        return "ERROR: IDEA not detected (idea_path в mod_config.json или IDEA_PATH)"
    p = _safe_path(rel_path)
    args = [idea_exe, "--line", str(line), str(p)] if line else [idea_exe, str(p)]
    subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, creationflags=subprocess.DETACHED_PROCESS)
    return f"OK: asked IDEA to open {rel_path}" + (f" line {line}" if line else "")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
@traced
def recent_activity(lines: int = 30) -> str:
    """Журнал вызовов сервера (кто, что и когда вызвал) — живое наблюдение за работой ИИ."""
    if not DEBUG_LOG.is_file():
        return "(empty)"
    ls = DEBUG_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(ls[-lines:])


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
@traced
def ai_events(last_n: int = 20, file_filter: str = "") -> str:
    """Структурный журнал действий ИИ (jsonl): tool, file, lines, summary.
    Этот же файл читает будущий IDEA-плагин (контракт ai_events.jsonl)."""
    if not EVENTS_FILE.is_file():
        return "(empty)"
    ls = EVENTS_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    if file_filter:
        ls = [l for l in ls if file_filter in l]
    return "\n".join(ls[-last_n:]) or "(empty)"


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
@traced
def project_brief() -> str:
    """Динамическое досье проекта: загрузчик, mod id, пакеты, ресурсы.
    ИИ получает контекст отсюда, а не из жёстких инструкций."""
    if not CFG["project_root"]:
        return "ERROR: project not configured — вызови configure(project_root=...)"
    info = {"loader": CFG["loader"], "project_root": str(PROJECT_ROOT),
            "java_home": DEFAULT_JAVA_HOME or "NOT DETECTED",
            "idea": CFG["idea_path"] or "NOT DETECTED",
            "mods": _probe(_probe_reader_dir(PROJECT_ROOT / "src" / "main" / "resources"))}
    src = PROJECT_ROOT / "src" / "main" / "java"
    pkgs = []
    if src.is_dir():
        for d in sorted(src.rglob("*")):
            if d.is_dir() and any(f.suffix == ".java" for f in d.iterdir()):
                pkgs.append(str(d.relative_to(PROJECT_ROOT)))
    info["java_packages"] = pkgs[:30]
    res = PROJECT_ROOT / "src" / "main" / "resources"
    info["has_assets"] = (res / "assets").is_dir()
    info["has_data"] = (res / "data").is_dir()
    return json.dumps(info, ensure_ascii=False, indent=2)


# ---------- universal launcher (ModRun), кирпич 1 ----------

def _probe_reader_dir(root: Path):
    def rd(name):
        f = root / name
        return f.read_text(encoding="utf-8", errors="replace") if f.is_file() else None
    return rd


def _probe_reader_zip(z: zipfile.ZipFile):
    names = set(z.namelist())

    def rd(name):
        return z.read(name).decode("utf-8", errors="replace") if name in names else None
    return rd


def _probe(rd) -> list:
    out = []
    nf = rd("META-INF/neoforge.mods.toml")
    fg = rd("META-INF/mods.toml")
    if nf or fg:
        try:
            data = tomllib.loads(nf or fg)
            m = (data.get("mods") or [{}])[0]
            mc = ""
            for v in (data.get("dependencies") or {}).values():
                for d in (v if isinstance(v, list) else [v]):
                    if isinstance(d, dict) and d.get("modId") == "minecraft":
                        mc = d.get("versionRange", "")
            out.append({"loader": "neoforge" if nf else "forge",
                        "modId": m.get("modId"), "version": m.get("version"),
                        "minecraft": mc})
        except Exception as e:
            out.append({"loader": "toml-parse-error", "error": str(e)})
    fb = rd("fabric.mod.json")
    if fb:
        try:
            d = json.loads(fb)
            out.append({"loader": "fabric", "modId": d.get("id"),
                        "version": d.get("version"),
                        "minecraft": (d.get("depends") or {}).get("minecraft")})
        except Exception as e:
            out.append({"loader": "fabric-json-error", "error": str(e)})
    qt = rd("quilt.mod.json")
    if qt:
        try:
            ql = (json.loads(qt) or {}).get("quilt_loader", {})
            out.append({"loader": "quilt", "modId": ql.get("id"),
                        "version": ql.get("version")})
        except Exception:
            pass
    return out or [{"loader": "unknown"}]


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
@traced
def probe_mod(target: str) -> str:
    """Определить формат мода (.jar или папка исходников): загрузчик, modId, версия, версия MC.
    Кирпич 1 универсального загрузчика ModRun."""
    p = Path(target).resolve()
    if not p.exists():
        return f"ERROR: not found: {target}"
    if p.is_dir():
        root = p / "src" / "main" / "resources"
        res = _probe(_probe_reader_dir(root if root.is_dir() else p))
    elif p.suffix.lower() == ".jar":
        with zipfile.ZipFile(p) as z:
            res = _probe(_probe_reader_zip(z))
    else:
        return "ERROR: expected .jar file or source directory"
    return json.dumps(res, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    import sys
    t = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    _dbg(f"SERVER BOOT transport={t}")
    mcp.run(transport=t)