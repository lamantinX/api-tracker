# 🚀 Быстрая настройка API Watcher

## 1. Установка

```bash
# Создайте виртуальное окружение
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Установите зависимости
pip install -r api_watcher/requirements.txt
```

## 2. Настройка

### Основные параметры (.env файл)
```bash
# Скопируйте пример
copy api_watcher\.env.example .env

# Отредактируйте .env:
API_WATCHER_SNAPSHOTS_DIR=snapshots
API_WATCHER_URLS_FILE=urls.json
API_WATCHER_TIMEOUT=30
API_WATCHER_LOG_LEVEL=INFO

# Telegram (опционально)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### URL для мониторинга (urls.json)
```json
[
  {
    "url": "https://api.example.com/docs",
    "type": "html",
    "name": "Example API",
    "selector": ".method",
    "description": "Описание API"
  }
]
```

## 3. Запуск

```bash
# Разовый запуск (из корневой папки проекта)
python api_watcher/main.py

# С дополнительными параметрами
python api_watcher/main.py --max-concurrent 5 --max-retries 3

# Автоматический запуск каждые 30 минут (Windows)
schtasks /create /tn "API Watcher" /tr "python api_watcher/main.py" /sc minute /mo 30 /st 09:00
```

**Важно:** Запускайте скрипт из корневой папки проекта, а не из папки `api_watcher`!

## 4. Типы документации

- **html** - HTML страницы (параметр: `selector`)
- **openapi** - OpenAPI/Swagger (параметр: `method_filter`)
- **json** - JSON API
- **postman** - Postman коллекции
- **md** - Markdown документы

## 5. Структура проекта

```
api_watcher/
├── main.py              # Точка входа
├── config.py            # Настройки
├── parsers/             # Парсеры документации
├── notifier/            # Уведомления
├── storage/             # Снимки состояний
└── utils/               # Утилиты
```