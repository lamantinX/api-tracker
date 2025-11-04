# Используем официальный Python образ
FROM python:3.11-slim

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файлы зависимостей
COPY api_watcher/requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY api_watcher/ ./api_watcher/
COPY urls.json .

# Создаем директории для снимков и логов
RUN mkdir -p snapshots logs

# Создаем пользователя для безопасности
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app
USER app

# Устанавливаем переменные окружения
ENV PYTHONPATH=/app
ENV API_WATCHER_SNAPSHOTS_DIR=/app/snapshots
ENV API_WATCHER_URLS_FILE=/app/urls.json

# Команда по умолчанию
CMD ["python", "api_watcher/main.py"]