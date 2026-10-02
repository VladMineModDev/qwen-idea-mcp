# 🎮 qwen-idea-mcp

**MCP-сервер для AI-разработки Minecraft-модов через IntelliJ IDEA**

Позволяет ИИ-ассистенту (Qwen, Claude, GPT и др.) полноценно работать с проектом мода: читать и редактировать код, запускать сборку и клиент Minecraft, анализировать логи и краш-репорты, делать скриншоты игры и управлять окнами.

![Minecraft Modding](https://img.shields.io/badge/Minecraft-1.21.1-brightgreen)
![NeoForge](https://img.shields.io/badge/NeoForge-21.1.248-blue)
![Python](https://img.shields.io/badge/Python-3.11%2B-yellow)

## ✨ Возможности

### 📁 Файловая система
- Чтение, создание, удаление файлов с автоматическими бэкапами
- Точечное патчинг кода (search & replace с проверками)
- Поиск по коду (grep с regex)
- Защита от случайной правки служебных директорий (.gradle, .idea, build)

### 🔨 Сборка и запуск
- Запуск Gradle-задач (build, compileJava, runClient)
- Фоновый запуск Minecraft-клиента с логированием
- Мониторинг статуса запущенного клиента
- Корректная остановка процессов

### 📊 Логи и отладка
- Чтение latest.log, debug.log, crash-reports
- Фильтрация по regex (ERROR, Exception и т.д.)
- Анализ краш-репортов с рекомендациями

### 🖥️ GUI-автоматизация
- Скриншоты окон Minecraft и IDEA
- Управление окнами (фокус, разворачивание)
- Нажатие клавиш и клики по координатам
- Ввод текста (для команд в игре)

## 🚀 Быстрый старт

### 1. Установка

```bash
git clone https://github.com/YOUR_USERNAME/qwen-idea-mcp.git
cd qwen-idea-mcp
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac
pip install -r requirements.txt

## 🚀 Шаг 2: Создание репозитория на GitHub

1. Зайди на [github.com/new](https://github.com/new)
2. Repository name: `qwen-idea-mcp`
3. Description: `MCP server for AI-powered Minecraft mod development via IntelliJ IDEA`
4. Public (или Private — как хочешь)
5. **НЕ** ставь галочки на README/.gitignore/license (мы уже создали)
6. Нажми **Create repository**

## 📤 Шаг 3: Пуш на GitHub

В PowerShell (в папке `qwen-idea-mcp`):

```powershell
# Инициализация git
git init
git add .
git commit -m "Initial commit: MCP server for Minecraft mod development"

# Подключение к GitHub (замени YOUR_USERNAME на свой ник)
git remote add origin https://github.com/YOUR_USERNAME/qwen-idea-mcp.git
git branch -M main
git push -u origin main