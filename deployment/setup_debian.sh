#!/bin/bash

# Остановка при ошибке
set -e

APP_DIR="/opt/api-tracker"
USER="apiwatcher"
LOG_DIR="/var/log/api-watcher"

# Проверка запуска от root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root"
  exit 1
fi

echo "🚀 Starting API Watcher deployment..."

# 1. Создание пользователя
if id "$USER" &>/dev/null; then
    echo "✅ User $USER already exists"
else
    echo "👤 Creating user $USER..."
    useradd -r -s /bin/false $USER
fi

# 2. Установка системных зависимостей
echo "📦 Installing system dependencies..."
apt-get update
apt-get install -y python3 python3-venv python3-pip git

# 3. Создание директорий
echo "📂 Creating directories..."
mkdir -p $APP_DIR
mkdir -p $LOG_DIR
chown -R $USER:$USER $LOG_DIR

# 4. Копирование файлов (предполагается запуск из корня репозитория)
echo "Copying files..."
cp -r . $APP_DIR/
chown -R $USER:$USER $APP_DIR

# 5. Настройка Python Venv
echo "🐍 Setting up Python environment..."
cd $APP_DIR
if [ ! -d "venv" ]; then
    sudo -u $USER python3 -m venv venv
fi

# Установка зависимостей
sudo -u $USER ./venv/bin/pip install -r api_watcher/requirements.txt

# 6. Настройка .env
if [ ! -f ".env" ]; then
    echo "⚠️ .env file not found! Creating from example..."
    if [ -f "api_watcher/.env.example" ]; then
        cp api_watcher/.env.example .env
        chown $USER:$USER .env
        echo "❗ Please edit $APP_DIR/.env with your actual keys!"
    else
        echo "❌ .env.example not found. You must create .env manually."
    fi
fi

# 7. Установка Systemd сервисов
echo "⚙️ Installing systemd services..."
cp deployment/api-watcher.service /etc/systemd/system/
cp deployment/api-watcher.timer /etc/systemd/system/

# Обновление systemd
systemctl daemon-reload

# Включение таймера
systemctl enable api-watcher.timer
systemctl start api-watcher.timer

echo "✅ Deployment complete!"
echo "📝 Logs: $LOG_DIR/watcher.log"
echo "Check status: systemctl status api-watcher.timer"

