# 🎮 qwen-idea-mcp

**MCP-сервер для AI-разработки Minecraft-модов через IntelliJ IDEA**

[![Release](https://img.shields.io/badge/release-v1.5.0-blue)](https://github.com/VladMineModDev/qwen-idea-mcp/releases)
![Minecraft](https://img.shields.io/badge/Minecraft-1.21.1-brightgreen)
![NeoForge](https://img.shields.io/badge/NeoForge-21.1.248-orange)
![Fabric](https://img.shields.io/badge/Fabric-ready-yellow)
![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Позволяет ИИ-ассистенту (Qwen, Claude, GPT, Cherry Studio, Cline и др.) **полноценно работать с проектом мода**: читать и редактировать код, запускать сборку и Minecraft-клиент, анализировать логи и краш-репорты, делать скриншоты игры и управлять окнами — всё это через единый MCP-протокол.

Разработан в процессе вайбкодинга мода Sculk Echo с помощью Qwen AI.

---

## ✨ Возможности

### 📁 Файловая система (6 инструментов)
- Чтение, создание, удаление файлов с **автоматическими бэкапами**
- Точечное патчинг кода (search & replace с проверками: не нашёл / неоднозначно)
- Поиск по коду (grep с regex)
- Защита от случайной правки служебных директорий (`.gradle`, `.idea`, `build`, `run`, `gradlew*`)

### 🔨 Сборка и запуск (4 инструмента)
- Запуск Gradle-задач (`build`, `compileJava`, `runClient` и др.)
- Фоновый запуск Minecraft-клиента с логированием вывода в файл
- Мониторинг статуса запущенного клиента
- Корректная остановка процесса (вместе с деревом дочерних)

### 📊 Логи и отладка (1 инструмент, 4 источника)
- Чтение `latest.log`, `debug.log`, свежих краш-репортов, логов фонового запуска
- Фильтрация по regex (`ERROR|Exception|Missing`)
- Режимы `tail`/`head` (краш-репорты с головы)

### 🖥️ GUI-автоматизация (9 инструментов)
- Скриншоты окон Minecraft, IDEA и всего экрана
- Управление окнами (фокус, разворачивание, список)
- Нажатие клавиш и комбинаций (`f3`, `ctrl+s`, `enter`)
- Клики по координатам, ввод ASCII-текста, паузы

### 👀 Наблюдение и интеграция (3 инструмента)
- `show_in_idea` — открыть файл в запущенной IDEA (человек видит правки вживую)
- `recent_activity` — журнал вызовов сервера (кто, что и когда вызвал)
- `project_brief` — динамическое досье проекта (загрузчик, modId, пакеты)

### 🧪 Анализ модов (2 инструмента)
- `probe_mod` — определение формата мода (NeoForge/Forge/Fabric/Quilt, modId, версии)
- `ping` — проверка связи + состояние конфигурации

### ⚙️ Настройка (1 инструмент)
- `configure(project_root=...)` — первый запуск через чат, без ручного редактирования конфигов

---

## 🚀 Быстрый старт

### 1. Установка

```bash
git clone https://github.com/VladMineModDev/qwen-idea-mcp.git
cd qwen-idea-mcp
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Запуск демона

```bash
python server.py sse
```

Сервер запустится на `http://127.0.0.1:8765`. **Не закрывайте это окно** — это серверная комната.

### 3. Подключение к MCP-клиенту

#### Вариант A: SSE (рекомендуется)

В настройках клиента добавьте SSE-сервер:
- **URL:** `http://127.0.0.1:8765/sse`

Пример JSON-конфига (Cherry Studio, Qwen Desktop):

```json
{
  "mcpServers": {
    "qwen-idea": {
      "type": "sse",
      "url": "http://127.0.0.1:8765/sse"
    }
  }
}
```

#### Вариант B: stdio через uvx (если клиент не умеет SSE)

```json
{
  "mcpServers": {
    "qwen-idea": {
      "command": "uvx",
      "args": [
        "--from", "mcp[cli]<2",
        "mcp", "run",
        "C:\\path\\to\\qwen-idea-mcp\\server.py"
      ]
    }
  }
}
```

---

## 🎯 Quickstart для мододела (3 минуты)

1. Запустите демон (`python server.py sse`) и подключите MCP-клиент (URL: `http://127.0.0.1:8765/sse`)
2. В первом сообщении скажите ИИ:

   ```
   Настрой MCP, путь к проекту мода: C:\path\to\your\mod
   ```

3. ИИ вызовет `configure()`, затем `project_brief()` и начнёт работать:
   - Читать код и ресурсы мода
   - Делать точечные правки через `patch_file`
   - Запускать сборку и Minecraft
   - Анализировать логи и краши
   - Делать скриншоты окна игры

**Примеры запросов:**
- «Прочитай главный класс мода и расскажи, что он делает»
- «Запусти runClient и проверь логи на ошибки»
- «Сделай скриншот окна Minecraft»
- «Найди все файлы, где упоминается MyItem»
- «Почини ошибку компиляции, которую показывает run_gradle compileJava»

ИИ работает автономно, вы наблюдаете через IDEA (файлы синхронизируются с диском автоматически) или через `show_in_idea` (ИИ открывает правленные файлы прямо в редакторе).

---

## ⚙️ Конфигурация

### `mod_config.json`

Скопируйте `mod_config.example.json` в `mod_config.json` и отредактируйте:

```json
{
  "loader": "neoforge",
  "project_root": "C:\\path\\to\\your\\mod",
  "java_home": "",
  "idea_path": "",
  "host": "127.0.0.1",
  "port": 8765,
  "logs": {
    "client_latest": "run/client/logs/latest.log",
    "client_debug": "run/client/logs/debug.log",
    "crash_dirs": ["run/client/crash-reports", "run/crash-reports"]
  }
}
```

**Поля:**

| Поле | Обязательное | Описание |
|------|:------------:|----------|
| `loader` | ✅ | `neoforge` / `fabric` / `forge` / `quilt` |
| `project_root` | ✅ | Абсолютный путь к корню проекта мода |
| `java_home` | ❌ | Путь к JDK 21. Пусто = автодетект (`~/.gradle/jdks`) |
| `idea_path` | ❌ | Путь к `idea64.exe`. Пусто = автодетект |
| `host` / `port` | ❌ | Адрес SSE-демона (по умолчанию `127.0.0.1:8765`) |
| `logs.*` | ❌ | Пути к логам клиента (зависят от загрузчика) |

**Автодетект:** если `java_home` или `idea_path` пустые, сервер сам найдёт их в стандартных местах (`~/.gradle/jdks`, `C:\Program Files\JetBrains`, JetBrains Toolbox).

---

## 🛠️ Каталог инструментов (26)

<details>
<summary>📁 Файлы (6)</summary>

| Инструмент | Описание |
|------------|----------|
| `read_file(rel_path, max_bytes)` | Прочитать файл |
| `write_file(rel_path, content)` | Создать/перезаписать (с бэкапом) |
| `patch_file(rel_path, old_text, new_text, replace_all)` | Точечная правка |
| `delete_file(rel_path)` | Удалить (с бэкапом) |
| `list_files(rel_dir, pattern)` | Список файлов |
| `grep(pattern, rel_dir, file_glob, case_sensitive, max_results)` | Поиск по коду |

</details>

<details>
<summary>🔨 Сборка и запуск (4)</summary>

| Инструмент | Описание |
|------------|----------|
| `run_gradle(task, background, timeout, java_home)` | Запустить задачу Gradle |
| `client_status()` | Статус фонового клиента |
| `stop_client()` | Остановить фоновый клиент |
| `open_idea(project)` | Открыть проект в IDEA |

</details>

<details>
<summary>📊 Логи (1)</summary>

| Инструмент | Описание |
|------------|----------|
| `get_logs(source, lines, mode, filter_regex)` | Читать логи (`latest` / `debug` / `crash` / `run`) |

</details>

<details>
<summary>🖥️ GUI-автоматизация (9)</summary>

| Инструмент | Описание |
|------------|----------|
| `screenshot(target, save_path)` | Скриншот окна (`minecraft` / `idea` / `screen` / заголовок) |
| `focus_window(title)` | Вывести окно на передний план |
| `maximize_window(title)` | Развернуть окно |
| `list_windows(filter)` | Список окон |
| `press_key(keys, interval)` | Нажать клавишу (`f3`, `ctrl+s`) |
| `type_text(text, interval)` | Набрать ASCII-текст |
| `click_at(x, y, button, clicks)` | Клик по координатам |
| `get_mouse_position()` | Позиция мыши |
| `wait(seconds)` | Пауза (до 120 сек) |

</details>

<details>
<summary>👀 Наблюдение и интеграция (3)</summary>

| Инструмент | Описание |
|------------|----------|
| `show_in_idea(rel_path, line)` | Открыть файл в запущенной IDEA |
| `recent_activity(lines)` | Журнал вызовов сервера |
| `project_brief()` | Досье проекта (loader, modId, пакеты) |

</details>

<details>
<summary>🧪 Анализ и настройка (3)</summary>

| Инструмент | Описание |
|------------|----------|
| `probe_mod(target)` | Детект формата мода (.jar или папка) |
| `configure(project_root, java_home, idea_path, loader)` | Первичная настройка через чат |
| `ping()` | Проверка связи + состояние конфигурации |

</details>

---

## 🔄 Типичные циклы

### Цикл правки кода

```
grep / read_file → patch_file (фрагмент ТОЧНО из read_file) →
run_gradle("compileJava") до exit=0 → show_in_idea(правленный файл) →
stop_client() → run_gradle("runClient", background=True) →
wait(45) → get_logs(source="run", filter_regex="ERROR|Exception")
```

### Разбор краша

```
get_logs(source="crash", mode="head", lines=120) → стектрейс →
grep / read_file → цикл правки кода
```

### Визуальная проверка

```
client_status → focus_window("Minecraft") →
screenshot(save_path=...) → press_key / type_text / click_at →
stop_client()
```

---

## ⚠️ Жёсткие правила

- `runClient` **только** с `background=True` (иначе блокировка до таймаута)
- Перед новым `runClient` **всегда** вызывайте `stop_client()`
- Перед `patch_file` **всегда** делайте `read_file` — фрагмент должен совпадать с исходником посимвольно (включая отступы)
- Краш-репорты читайте с `mode="head"` (стектрейс в начале файла)
- Изменения Java-кода требуют `compileJava` **до** `runClient`
- Изменения ресурсов (текстуры / JSON / lang) требуют только перезапуска клиента
- `mod_config.json` нельзя править через `write_file` — только через `configure()`
- Перед крупным рефакторингом просите человека сделать `git commit` (бэкапы есть в `backups/`, но git надёжнее)

---

## 🐛 Troubleshooting

| Проблема | Решение |
|----------|---------|
| `ModuleNotFoundError: No module named 'mcp'` | `pip install "mcp[cli]<2"` (v2 сломал обратную совместимость) |
| Клиент не видит инструменты (HTTP) | Используйте SSE-транспорт (URL `/sse`), не `streamable-http` (`/mcp`) |
| `JAVA_HOME not set` | Задайте `java_home` в `mod_config.json` или переменную окружения `JAVA_HOME` |
| `gradlew.bat не найден` | Проверьте `project_root` в `mod_config.json` — это должен быть корень проекта мода |
| Висняки второго вызова в чате (stdio) | Перейдите на SSE-демон |
| Gradle «висит» до таймаута | Это норма: вывод идёт в файл (`logs/`), ждите завершения. Первый `compileJava` греется минутами |
| Чёрный скриншот | Добавьте `time.sleep(0.1)` перед `sct.grab()` в `screenshot()` |
| `list_windows` возвращает пустой список | Запущенные окна с пустыми заголовками фильтруются; это норма |
| `type_text` не печатает кириллицу | Ограничение `pyautogui`; для команд в игре обычно достаточно ASCII |
| ИИ говорит «инструменты зависли» | Сервер скорее всего жив. Проверьте `recent_activity` из другого чата или откройте новый чат |

---

## 📂 Структура проекта

```
qwen-idea-mcp/
├── server.py                       # Основной сервер (26 инструментов)
├── requirements.txt                # Зависимости
├── README.md                       # Эта документация
├── INSTRUCTIONS_FOR_AI.md          # Инструкции для ИИ (v2)
├── mod_config.example.json         # Шаблон конфигурации (публичный)
├── mod_config.json                 # Локальная конфигурация (git-ignored)
├── test_all_tools.py               # Автотест всех 26 инструментов
├── backups/                        # Бэкапы файлов до правок (git-ignored)
├── logs/                           # Выводы gradle/runClient (git-ignored)
├── state.json                      # PID фонового клиента (git-ignored)
└── server_debug.log                # Чёрный ящик вызовов (git-ignored)
```

---

## 🧪 Автотест

```bash
# В одном окне — демон
python server.py sse

# В другом — автотест
python test_all_tools.py
```

Тест обходит Qwen-клиент и подключается к SSE-демону напрямую через библиотеку `mcp`. Проверяет все 26 инструментов, пишет результат в консоль и `server_debug.log`.

**Ожидаемый результат v1.5:** все 26 ✅, ни одного EXC в логе.

---

## 🗺️ Дорожная карта

Актуальные задачи — в [Issues](https://github.com/VladMineModDev/qwen-idea-mcp/issues):

- [ ] **Fabric loader support** — отдельный `mod_config.fabric.example.json`, правки `run_gradle` и `get_logs` по полю `loader`
- [ ] **Forge (legacy) support** — поддержка Forge 1.20.1 и ниже
- [ ] **Linux / macOS** — заменить `tasklist`/`taskkill` на `psutil`, кроссплатформенный автодетект
- [ ] **ModRun кирпич 2: `resolve_environment`** — автоматическое скачивание нужной версии клиента и загрузчика через Mojang piston-meta и Fabric meta API
- [ ] **ModRun кирпич 3: `provision_instance`** — чистый тестовый инстанс для любого jar-мода
- [ ] **ModRun кирпич 4: `launch_mod`** — единый запуск мода независимо от его загрузчика
- [ ] **IntelliJ plugin bridge** — плагин IntelliJ Platform с REST/API-мостом (подсветка правок, инспекции, run-конфигурации из MCP)
- [ ] **Research: true universal loader** — обёртка над Sinytra Connector / Patchwork для запуска Fabric-модов внутри NeoForge и наоборот

---

## 🤝 Contributing

Pull requests приветствуются! Перед крупным PR:

1. Убедитесь, что `python test_all_tools.py` проходит полностью (26 ✅)
2. В `server_debug.log` нет `EXC`
3. Новые инструменты добавляйте с декоратором `@traced` и `@mcp.tool()`
4. Обновите этот README и `INSTRUCTIONS_FOR_AI.md`

### Архитектурные принципы

- **Никаких личных путей в коде** — всё через `mod_config.json` и автодетект
- **Бэкапы автоматические** — каждая правка сохраняется в `backups/`
- **Чёрный ящик** — каждый вызов логируется в `server_debug.log` (START / END / EXC)
- **Динамическое досье** — специфика проекта получается через `project_brief()`, не хардкодится в инструкциях

---

## 📄 License

MIT License — используйте как хотите. Подробности в файле `LICENSE`.

---

## 🙏 Acknowledgments

- [Model Context Protocol](https://modelcontextprotocol.io/) — протокол, на котором всё работает
- [FastMCP](https://github.com/jlowin/fastmcp) — удобный Python-SDK
- [pyautogui](https://pyautogui.readthedocs.io/) / [mss](https://python-mss.readthedocs.io/) / [pygetwindow](https://github.com/asweigart/pygetwindow) — GUI-автоматизация
- [NeoForge](https://neoforged.net/) / [Fabric](https://fabricmc.net/) — загрузчики модов
- Qwen AI — за совместную разработку в процессе вайбкодинга мода Sculk Echo

---

**Made with ❤️ for Minecraft modders**

> Если вам понравился проект — поставьте ⭐ на [GitHub](https://github.com/VladMineModDev/qwen-idea-mcp). Это помогает другим мододелам найти инструмент.