#!/bin/bash

echo "=== Установка недостающих зависимостей API Watcher ==="

# Проверяем, что мы в правильной директории
if [ ! -f "api_watcher/requirements.txt" ]; then
    echo "❌ Файл api_watcher/requirements.txt не найден"
    echo "Запустите скрипт из директории /opt/api-tracker"
    exit 1
fi

# Проверяем виртуальное окружение
if [ ! -f "venv/bin/python" ]; then
    echo "❌ Виртуальное окружение не найдено"
    echo "Создаем виртуальное окружение..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "❌ Не удалось создать виртуальное окружение"
        exit 1
    fi
    echo "✅ Виртуальное окружение создано"
fi

echo "Активируем виртуальное окружение и устанавливаем зависимости..."

# Обновляем pip
./venv/bin/python -m pip install --upgrade pip

# Устанавливаем зависимости
./venv/bin/pip install -r api_watcher/requirements.txt

if [ $? -eq 0 ]; then
    echo "✅ Зависимости установлены успешно"
    
    # Проверяем ключевые модули
    echo -e "\nПроверяем установку ключевых модулей:"
    
    modules=("structlog" "aiohttp" "sqlalchemy" "beautifulsoup4" "requests")
    
    for module in "${modules[@]}"; do
        if ./venv/bin/python -c "import $module" 2>/dev/null; then
            echo "✅ $module"
        else
            echo "❌ $module не установлен"
        fi
    done
    
    echo -e "\n✅ Установка завершена!"
    echo "Теперь можно запустить: sudo bash fix_service.sh"
    
else
    echo "❌ Ошибка при установке зависимостей"
    exit 1
fi