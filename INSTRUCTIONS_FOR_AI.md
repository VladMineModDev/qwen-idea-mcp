# Инструкции для ИИ: работа с qwen-idea-mcp

## Контекст
- Проект: мод SculkEcho (NeoForge, Minecraft 1.21.1), путь C:\Users\Home\Desktop\skulkevo-template-1.21.1
- Код: src/main/java/com/example/sculkecho/ (пакеты client, crafting, entity, infection, init, item, loot, network, service)
- Ресурсы: src/main/resources/assets/sculkecho/ и data/
- Сборка: gradlew.bat, JDK 21 (JAVA_HOME настроен на сервере)
- MCP-сервер — отдельный демон (SSE). Если инструменты не отвечают — попроси человека проверить окно PowerShell с демоном.

## Каталог инструментов
Файлы: read_file(rel_path), write_file(rel_path, content), patch_file(rel_path, old_text, new_text, replace_all), delete_file(rel_path), list_files(rel_dir, pattern), grep(pattern, rel_dir, file_glob, case_sensitive, max_results) -> "файл:строка: текст"
Сборка/запуск: run_gradle(task, background, timeout), client_status(), stop_client()
Логи: get_logs(source: latest|debug|crash|run, lines, mode: tail|head, filter_regex)
GUI: screenshot(target: minecraft|idea|screen|заголовок, save_path), focus_window(title), maximize_window(title), list_windows(filter), press_key("f3"/"ctrl+s"), type_text(ascii), click_at(x, y), get_mouse_position(), wait(seconds)
Служебные: ping(), open_idea()

## Стандартные циклы
### Правка кода (основной)
1. grep / read_file — найти место. 2. patch_file — минимальная правка (фрагмент копировать ТОЧНО из read_file, включая отступы). 3. run_gradle("compileJava") — ждать exit=0; при ошибке читать хвост вывода и чинить. 4. Если правка видна в игре: stop_client() -> run_gradle("runClient", background=True) -> wait(45) -> get_logs(source="run", filter_regex="ERROR|Exception|Missing").
### Разбор краша
1. get_logs(source="crash", mode="head", lines=120). 2. Найти классы мода в стектрейсе -> grep/read_file. 3. Цикл правки кода.
### Проверка в игре
1. client_status(); если не запущен — поднять по циклу правки. 2. focus_window("Minecraft") -> screenshot(save_path=...) и проанализировать/показать человеку. 3. При необходимости press_key / type_text + press_key("enter") / click_at. 4. По завершении stop_client().

## Жёсткие правила
- runClient ТОЛЬКО с background=True (иначе блокировка до таймаута).
- Никогда не запускать второй runClient без stop_client().
- Перед крупным рефакторингом просить человека сделать git commit (бэкапы есть в qwen-idea-mcp/backups, но git надёжнее).
- Запрещено редактировать: gradlew, gradlew.bat, gradle/, .gradle/, .idea/, build/, run/ (сервер и так откажет).
- Изменения Java-кода требуют compileJava ПЕРЕД runClient; изменения ресурсов (текстуры/json/lang) — только перезапуска клиента.
- По одному вызову инструмента за раз, ждать результата перед следующим шагом.

## Подводные камни
- Первый compileJava греется минутами (демон Gradle) — это норма.
- runClient загружается 40–90 сек; get_logs(source="run") раньше может быть пустым.
- type_text не печатает кириллицу.
- Краш-репорты читать с mode="head" (стектрейс в начале файла).
- Если вызов «виснет»: сервер жив, проверить окно демона и повторить вызов следующим сообщением.