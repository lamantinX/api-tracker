#!/bin/bash

echo "=== Быстрая диагностика API Watcher ==="

# Проверяем основные компоненты
echo "1. Проверка Python в venv:"
/opt/api-tracker/venv/bin/python --version

echo -e "\n2. Проверка импорта модулей:"
cd /opt/api-tracker
export PYTHONPATH=/opt/api-tracker
/opt/api-tracker/venv/bin/python -c "
import sys
print(f'Python path: {sys.path}')
try:
    from api_watcher.config import Config
    print('✅ Config OK')
except ImportError as e:
    print(f'❌ Config error: {e}')
    
try:
    from api_watcher.watcher import APIWatcher
    print('✅ APIWatcher OK')
except ImportError as e:
    print(f'❌ APIWatcher error: {e}')
"

echo -e "\n3. Проверка зависимостей:"
/opt/api-tracker/venv/bin/python -c "
packages = ['asyncio', 'aiohttp', 'sqlalchemy', 'dotenv']
for pkg in packages:
    try:
        __import__(pkg)
        print(f'✅ {pkg}')
    except ImportError:
        print(f'❌ {pkg} не установлен')
"

echo -e "\n4. Тест запуска с перехватом ошибок:"
/opt/api-tracker/venv/bin/python -c "
import sys
sys.path.insert(0, '/opt/api-tracker')
try:
    from api_watcher.watcher import main
    print('✅ Модуль main импортирован')
except Exception as e:
    print(f'❌ Ошибка импорта main: {e}')
    import traceback
    traceback.print_exc()
"