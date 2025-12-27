#!/bin/bash

echo "=== API Watcher Service Debug Script ==="
echo "Дата: $(date)"
echo

echo "1. Проверка структуры каталогов:"
echo "Рабочий каталог: /opt/api-tracker"
ls -la /opt/api-tracker/ 2>/dev/null || echo "❌ Каталог /opt/api-tracker не найден"
echo

echo "2. Проверка виртуального окружения:"
ls -la /opt/api-tracker/venv/bin/ 2>/dev/null || echo "❌ Виртуальное окружение не найдено"
echo

echo "3. Проверка Python и зависимостей:"
/opt/api-tracker/venv/bin/python --version 2>/dev/null || echo "❌ Python не найден в venv"
echo

echo "4. Проверка основных файлов:"
echo "watcher.py: $(test -f /opt/api-tracker/api_watcher/watcher.py && echo '✅ Найден' || echo '❌ Не найден')"
echo "config.py: $(test -f /opt/api-tracker/api_watcher/config.py && echo '✅ Найден' || echo '❌ Не найден')"
echo ".env: $(test -f /opt/api-tracker/.env && echo '✅ Найден' || echo '❌ Не найден')"
echo "urls.json: $(test -f /opt/api-tracker/urls.json && echo '✅ Найден' || echo '❌ Не найден')"
echo

echo "5. Проверка прав доступа:"
echo "Владелец /opt/api-tracker: $(ls -ld /opt/api-tracker 2>/dev/null | awk '{print $3":"$4}')"
echo "Права на watcher.py: $(ls -l /opt/api-tracker/api_watcher/watcher.py 2>/dev/null | awk '{print $1}')"
echo

echo "6. Проверка пользователя apiwatcher:"
id apiwatcher 2>/dev/null || echo "❌ Пользователь apiwatcher не найден"
echo

echo "7. Проверка логов systemd:"
echo "Последние 20 строк из journalctl:"
journalctl -u api-watcher.service -n 20 --no-pager 2>/dev/null || echo "❌ Не удалось получить логи"
echo

echo "8. Тест запуска Python модулей:"
echo "Тестируем импорт основных модулей..."
/opt/api-tracker/venv/bin/python -c "
import sys
sys.path.insert(0, '/opt/api-tracker')
try:
    from api_watcher.config import Config
    print('✅ Config импортирован успешно')
    print(f'URLs файл: {Config.URLS_FILE}')
    print(f'Database URL: {Config.DATABASE_URL}')
except Exception as e:
    print(f'❌ Ошибка импорта Config: {e}')

try:
    import asyncio
    print('✅ asyncio доступен')
except Exception as e:
    print(f'❌ Ошибка asyncio: {e}')
" 2>/dev/null || echo "❌ Не удалось выполнить тест Python"

echo
echo "9. Проверка переменных окружения из .env:"
if [ -f /opt/api-tracker/.env ]; then
    echo "Содержимое .env (без секретов):"
    grep -v "API_KEY\|TOKEN\|SECRET" /opt/api-tracker/.env 2>/dev/null || echo "Файл .env пуст или недоступен"
else
    echo "❌ Файл .env не найден"
fi

echo
echo "10. Попытка запуска с подробным выводом ошибок:"
echo "Запускаем watcher.py с максимальной детализацией..."
cd /opt/api-tracker
export PYTHONPATH=/opt/api-tracker
export API_WATCHER_URLS_FILE=/opt/api-tracker/urls.json
/opt/api-tracker/venv/bin/python -u -v /opt/api-tracker/api_watcher/watcher.py 2>&1 | head -50

echo
echo "=== Конец диагностики ==="