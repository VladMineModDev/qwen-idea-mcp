"""
Qwen <-> IntelliJ IDEA MCP server. v4
Фикс stdio (stdin=DEVNULL у всех дочерних процессов) + чёрный ящик server_debug.log.
"""
import inspect
import functools
import json
import os
import re
import shutil
import subprocess
import time
import pyautogui
import mss
import pygetwindow as gw
from pathlib import Path

import anyio
from mcp.server.fastmcp import FastMCP

PROJECT_ROOT = Path(r"C:\Your\Path\To\Mod").resolve()
SERVER_ROOT = Path(__file__).resolve().parent
BACKUP_ROOT = SERVER_ROOT / "backups"
LOG_ROOT = SERVER_ROOT / "logs"
STATE_FILE = SERVER_ROOT / "state.json"
DEBUG_LOG = SERVER_ROOT / "server_debug.log"
DEFAULT_JAVA_HOME = r"C:\Path\To\JDK-21"

SKIP_DIRS = {".git", ".gradle", ".idea", "build", "run", "out"}
WRITE_DENY_DIRS = SKIP_DIRS | {"gradle"}
WRITE_DENY_FILES = {"gradlew", "gradlew.bat"}

SERVER_INSTRUCTIONS = (
    "MCP-сервер разработки Minecraft-мода (NeoForge 1.21.1) в IntelliJ IDEA. "
    "Основной цикл: grep/read_file -> patch_file/write_file -> run_gradle('compileJava') -> "
    "stop_client() -> run_gradle('runClient', background=True) -> wait(45) -> "
    "get_logs(source='run', filter_regex='ERROR|Exception') -> screenshot(target='minecraft'). "
    "Правила: перед patch_file всегда read_file (точное совпадение фрагмента); "
    "runClient ТОЛЬКО с background=True; перед новым runClient всегда stop_client(); "
    "краш-репорты читать с mode='head'; бэкапы правок автоматические в qwen-idea-mcp/backups."
)

mcp = FastMCP("qwen-idea-mcp", host="127.0.0.1", port=8765,
              instructions=SERVER_INSTRUCTIONS)


# ---------- чёрный ящик ----------

def _dbg(msg: str):
    with open(DEBUG_LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def traced(fn):
    """Логирует START/END/EXC каждого вызова инструмента в server_debug.log."""
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


# ---------- файлы ----------

@mcp.tool()
@traced
def ping() -> str:
    """Проверка связи с MCP-сервером."""
    return f"pong | project={PROJECT_ROOT}"


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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
    return msg


@mcp.tool()
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
    b = _backup(p)
    p.write_text(src.replace(old_text, new_text) if replace_all
                 else src.replace(old_text, new_text, 1), encoding="utf-8")
    return f"OK: replaced {count if replace_all else 1} occurrence(s) in {rel_path} | backup: {b}"


@mcp.tool()
@traced
def delete_file(rel_path: str) -> str:
    """Удалить файл (сначала копия в backup)."""
    p = _writable(rel_path)
    if not p.is_file():
        return f"File not found: {rel_path}"
    b = _backup(p)
    p.unlink()
    return f"OK: deleted {rel_path} | backup: {b}"


@mcp.tool()
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

@mcp.tool()
@traced
async def run_gradle(task: str, background: bool = False, timeout: int = 900,
                     java_home: str = "") -> str:
    """Запустить задачу gradle (build, compileJava, runClient...).
    background=True — отделить процесс (для runClient), вывод идёт в logs/run_*.log."""
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["JAVA_HOME"] = java_home or DEFAULT_JAVA_HOME
    cmd = ["cmd", "/c", "gradlew.bat", *task.split()]
    log_path = LOG_ROOT / f"{'run' if background else 'gradle'}_{time.strftime('%Y%m%d-%H%M%S')}.log"
    
    # Открываем файл, но НЕ закрываем — пусть живёт (мы в долгоживущем процессе)
    fh = open(log_path, "wb")
    
    try:
        # DETACHED_PROCESS вместо CREATE_NEW_PROCESS_GROUP — надёжнее на Windows
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
    fh.close()  # для синхронного запуска закрываем после wait
    out = log_path.read_text(encoding="utf-8", errors="replace")
    tail = "\n".join(out.splitlines()[-120:])
    hint = ""
    if code != 0 and "JAVA_HOME" in out:
        hint = f"\n[HINT] Проблема с JAVA_HOME ({env['JAVA_HOME']})."
    return f"exit={code} | full log: {log_path}\n--- tail ---\n{tail}{hint}"

@mcp.tool()
@traced
def client_status() -> str:
    """Жив ли фоновый процесс runClient."""
    st = _load_state()
    if not st.get("pid"):
        return "No background client launched."
    return (f"task={st.get('task')} pid={st['pid']} "
            f"alive={_pid_alive(st['pid'])} log={st.get('log')}")


@mcp.tool()
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


@mcp.tool()
@traced
def get_logs(source: str = "latest", lines: int = 150, mode: str = "tail",
             filter_regex: str = "") -> str:
    """Читает логи. source: latest | debug | crash | run.
    latest/debug — run/client/logs; crash — свежий краш-репорт (читай с mode='head');
    run — лог фонового runClient. filter_regex — показать только строки с шаблоном."""
    if source == "latest":
        p = PROJECT_ROOT / "run" / "client" / "logs" / "latest.log"
    elif source == "debug":
        p = PROJECT_ROOT / "run" / "client" / "logs" / "debug.log"
    elif source == "crash":
        dirs = [PROJECT_ROOT / "run" / "client" / "crash-reports",
                PROJECT_ROOT / "run" / "crash-reports"]
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
    ls = p.read_text(encoding="utf-8", errors="replace").splitlines()
    if filter_regex:
        rx = re.compile(filter_regex, re.IGNORECASE)
        ls = [l for l in ls if rx.search(l)]
    sel = ls[-lines:] if mode == "tail" else ls[:lines]
    return f"[{p.name}] shown {len(sel)} of {len(ls)} lines (mode={mode})\n" + "\n".join(sel)

# ---------- шаг 4: GUI ----------

@mcp.tool()
@traced
def screenshot(target: str = "minecraft", save_path: str = "") -> str:
    """Сделать скриншот окна (target: 'minecraft' | 'idea' | 'screen' | путь к окну).
    save_path — куда сохранить (если пусто, возвращается base64)."""
    try:
        if target == "minecraft":
            windows = gw.getWindowsWithTitle("Minecraft")
            if not windows:
                return "ERROR: Minecraft window not found. Запусти runClient."
            win = windows[0]
        elif target == "idea":
            windows = gw.getWindowsWithTitle("IntelliJ IDEA")
            if not windows:
                return "ERROR: IntelliJ IDEA window not found."
            win = windows[0]
        elif target == "screen":
            win = None
        else:
            windows = gw.getWindowsWithTitle(target)
            if not windows:
                return f"ERROR: Window with title '{target}' not found."
            win = windows[0]

        with mss.mss() as sct:
            if win:
                monitor = {"top": win.top, "left": win.left,
                           "width": win.width, "height": win.height}
            else:
                monitor = sct.monitors[0]  # весь экран
            img = sct.grab(monitor)
            
        if save_path:
            p = Path(save_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            mss.tools.to_png(img.rgb, img.size, output=str(p))
            return f"OK: screenshot saved to {p} ({img.width}x{img.height})"
        
        # base64 для возврата в чат
        import base64
        png_data = mss.tools.to_png(img.rgb, img.size)
        return f"data:image/png;base64,{base64.b64encode(png_data).decode()}"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
@traced
def press_key(keys: str, interval: float = 0.1) -> str:
    """Нажать клавишу или комбинацию (например: 'f5', 'ctrl+s', 'enter', 'w').
    interval — задержка между клавишами в комбинации."""
    try:
        parts = [k.strip() for k in keys.lower().split("+")]
        pyautogui.hotkey(*parts, interval=interval)
        return f"OK: pressed {keys}"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


@mcp.tool()
@traced
def click_at(x: int, y: int, button: str = "left", clicks: int = 1) -> str:
    """Кликнуть по координатам экрана (button: 'left' | 'right' | 'middle')."""
    try:
        pyautogui.click(x=x, y=y, button=button, clicks=clicks)
        return f"OK: clicked ({x}, {y}) button={button} clicks={clicks}"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


@mcp.tool()
@traced
def get_mouse_position() -> str:
    """Получить текущие координаты мыши."""
    x, y = pyautogui.position()
    return f"Mouse at ({x}, {y})"

@mcp.tool()
@traced
def list_windows(filter_text: str = "") -> str:
    """Список заголовков открытых окон (опционально фильтр по подстроке)."""
    titles = [w.title for w in gw.getAllTitles() if w.title.strip()]
    if filter_text:
        titles = [t for t in titles if filter_text.lower() in t.lower()]
    return "\n".join(titles[:50]) or "(no windows)"


@mcp.tool()
@traced
def type_text(text: str, interval: float = 0.03) -> str:
    """Набрать текст с клавиатуры (команды в игре, поля ввода). Только латиница/ASCII."""
    try:
        pyautogui.write(text, interval=interval)
        return f"OK: typed {len(text)} chars"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


@mcp.tool()
@traced
def wait(seconds: float = 5.0) -> str:
    """Пауза между действиями (ожидание загрузки мира и т.п.), максимум 120 сек."""
    time.sleep(min(seconds, 120.0))
    return f"OK: waited {seconds}s"


@mcp.tool()
@traced
def open_idea(project: str = "") -> str:
    """Открыть проект в IntelliJ IDEA (автопоиск idea64.exe)."""
    root = Path(project) if project else PROJECT_ROOT
    idea_exe = None
    base = Path(r"C:\Program Files\JetBrains")
    if base.is_dir():
        for d in sorted(base.glob("IntelliJ IDEA*"), reverse=True):
            cand = d / "bin" / "idea64.exe"
            if cand.is_file():
                idea_exe = cand
                break
    if idea_exe is None:
        return "ERROR: idea64.exe not found in C:\\Program Files\\JetBrains"
    subprocess.Popen([str(idea_exe), str(root)], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=subprocess.DETACHED_PROCESS)
    return f"OK: opening IDEA for {root}"

if __name__ == "__main__":
    import sys
    t = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    _dbg(f"SERVER BOOT transport={t}")
    mcp.run(transport=t)