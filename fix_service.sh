#!/bin/bash

echo "=== Исправление проблем API Watcher Service ==="

# Проверяем, что мы запущены от root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Запустите скрипт от root: sudo bash fix_service.sh"
    exit 1
fi

echo "1. Создание пользователя apiwatcher (если не существует)..."
if ! id apiwatcher &>/dev/null; then
    useradd -r -s /bin/false apiwatcher
    echo "✅ Пользователь apiwatcher создан"
else
    echo "✅ Пользователь apiwatcher уже существует"
fi

echo -e "\n2. Проверка и создание директорий..."
mkdir -p /opt/api-tracker
mkdir -p /var/log/api-watcher
chown -R apiwatcher:apiwatcher /opt/api-tracker
chown -R apiwatcher:apiwatcher /var/log/api-watcher
echo "✅ Директории созданы и права установлены"

echo -e "\n3. Проверка и установка зависимостей Python..."
if [ ! -f /opt/api-tracker/venv/bin/python ]; then
    echo "❌ Виртуальное окружение не найдено в /opt/api-tracker/venv/"
    echo "Создайте его командой:"
    echo "cd /opt/api-tracker && python3 -m venv venv && source venv/bin/activate && pip install -r api_watcher/requirements.txt"
    exit 1
else
    echo "✅ Виртуальное окружение найдено"
    
    # Проверяем и устанавливаем недостающие зависимости
    echo "Проверяем зависимости..."
    cd /opt/api-tracker
    
    # Проверяем structlog
    if ! /opt/api-tracker/venv/bin/python -c "import structlog" 2>/dev/null; then
        echo "⚠️ structlog не найден, устанавливаем зависимости..."
        /opt/api-tracker/venv/bin/pip install -r api_watcher/requirements.txt
        echo "✅ Зависимости установлены"
    else
        echo "✅ Основные зависимости найдены"
    fi
fi

echo -e "\n4. Проверка основных файлов..."
required_files=(
    "/opt/api-tracker/api_watcher/watcher.py"
    "/opt/api-tracker/api_watcher/config.py"
    "/opt/api-tracker/.env"
    "/opt/api-tracker/urls.json"
)

for file in "${required_files[@]}"; do
    if [ -f "$file" ]; then
        echo "✅ $file найден"
    else
        echo "❌ $file не найден"
        missing_files=true
    fi
done

if [ "$missing_files" = true ]; then
    echo "❌ Отсутствуют необходимые файлы. Убедитесь, что проект правильно развернут."
    exit 1
fi

echo -e "\n5. Тестирование Python модулей..."
cd /opt/api-tracker
export PYTHONPATH=/opt/api-tracker

# Тест импорта
sudo -u apiwatcher /opt/api-tracker/venv/bin/python -c "
import sys
sys.path.insert(0, '/opt/api-tracker')
try:
    from api_watcher.config import Config
    print('✅ Config импортирован успешно')
except Exception as e:
    print(f'❌ Ошибка импорта Config: {e}')
    exit(1)

try:
    from api_watcher.watcher import APIWatcher
    print('✅ APIWatcher импортирован успешно')
except Exception as e:
    print(f'❌ Ошибка импорта APIWatcher: {e}')
    exit(1)
"

if [ $? -ne 0 ]; then
    echo "❌ Ошибка импорта Python модулей"
    exit 1
fi

echo -e "\n6. Установка исправленного systemd сервиса..."
if [ -f "/opt/api-tracker/deployment/api-watcher-fixed.service" ]; then
    cp /opt/api-tracker/deployment/api-watcher-fixed.service /etc/systemd/system/api-watcher.service
    systemctl daemon-reload
    echo "✅ Сервис обновлен"
else
    echo "❌ Файл api-watcher-fixed.service не найден"
    exit 1
fi

echo -e "\n7. Тестовый запуск..."
echo "Тестируем запуск от пользователя apiwatcher..."
sudo -u apiwatcher bash -c "
cd /opt/api-tracker
export PYTHONPATH=/opt/api-tracker
export API_WATCHER_URLS_FILE=/opt/api-tracker/urls.json
timeout 10s /opt/api-tracker/venv/bin/python -u /opt/api-tracker/api_watcher/watcher.py
"

echo -e "\n8. Проверка статуса сервиса..."
systemctl status api-watcher.service --no-pager

echo -e "\n=== Исправление завершено ==="
echo "Для запуска сервиса используйте:"
echo "sudo systemctl start api-watcher.service"
echo ""
echo "Для просмотра логов:"
echo "sudo journalctl -u api-watcher.service -f"
echo "sudo tail -f /var/log/api-watcher/watcher.error.log"