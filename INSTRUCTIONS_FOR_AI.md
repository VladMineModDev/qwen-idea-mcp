# Инструкции для ИИ: работа с qwen-idea-mcp

## Первый выход на связь
1. ping — связь и конфигурация. Если WARNING: спроси у человека абсолютный путь
   к проекту мода и вызови configure(project_root=...).
2. project_brief — досье проекта (загрузчик, mod id, пакеты, ресурсы).
   Никогда не угадывай специфику проекта — бери её отсюда.
3. Уточняй детали через list_files / grep / read_file.

## Каталог инструментов
Файлы: read_file, write_file, patch_file, delete_file, list_files, grep
Сборка/запуск: run_gradle(task, background, timeout), client_status, stop_client
Логи: get_logs(source: latest|debug|crash|run, lines, mode: tail|head, filter_regex)
GUI: screenshot(target, save_path), focus_window, maximize_window, list_windows,
     press_key, type_text (ASCII), click_at, get_mouse_position, wait
Наблюдение и интеграция: show_in_idea(rel_path, line), recent_activity(lines), open_idea
Анализ модов: probe_mod(jar или папка)
Служебные: ping, configure, project_brief

## Циклы
Правка кода: grep/read_file -> patch_file (фрагмент ТОЧНО из read_file) ->
  run_gradle("compileJava") до exit=0 -> show_in_idea(правленный файл) ->
  stop_client() -> run_gradle("runClient", background=True) -> wait(45) ->
  get_logs(source="run", filter_regex="ERROR|Exception|Missing")
Разбор краша: get_logs(source="crash", mode="head", lines=120) -> стектрейс ->
  grep/read_file -> цикл правки
Проверка в игре: client_status -> focus_window("Minecraft") -> screenshot(save_path=...)
  -> при необходимости press_key/type_text/click_at -> stop_client() по завершении

## Жёсткие правила
- runClient ТОЛЬКО с background=True; перед новым runClient всегда stop_client().
- Перед patch_file всегда read_file; не угадывай отступы.
- Краш-репорты читай с mode="head".
- Java-правки требуют compileJava до runClient; ресурсы (текстуры/json/lang) — только перезапуск клиента.
- Перед крупным рефакторингом проси человека сделать git commit.
- Запрещено редактировать: gradlew*, gradle/, .gradle/, .idea/, build/, run/ (сервер откажет).
- mod_config.json не правь через write_file — только configure().
- По одному вызову за раз, жди результат.
- После важной правки вызывай show_in_idea — человек наблюдает за тобой в IDEA.

## Подводные камни
- Первый compileJava греется минутами — норма. runClient грузится 40–90 сек.
- type_text не печатает кириллицу.
- Если вызов «виснет»: сервер жив (проверь recent_activity из другого чата),
  повтори вызов следующим сообщением или в новом чате.