#!/usr/bin/env python3
"""
Тестовый скрипт для проверки работоспособности API Watcher
"""

import sys
import os
import traceback

# Добавляем путь к проекту
sys.path.insert(0, '/opt/api-tracker')

def test_imports():
    """Тестирует импорт основных модулей"""
    print("=== Тест импорта модулей ===")
    
    try:
        import asyncio
        print("✅ asyncio")
    except ImportError as e:
        print(f"❌ asyncio: {e}")
        return False
    
    try:
        from api_watcher.config import Config
        print("✅ Config")
        print(f"   URLs файл: {Config.URLS_FILE}")
        print(f"   Database: {Config.DATABASE_URL}")
    except ImportError as e:
        print(f"❌ Config: {e}")
        return False
    
    try:
        from api_watcher.watcher import APIWatcher
        print("✅ APIWatcher")
    except ImportError as e:
        print(f"❌ APIWatcher: {e}")
        return False
    
    try:
        from api_watcher.storage.repository import SQLAlchemySnapshotRepository
        print("✅ Repository")
    except ImportError as e:
        print(f"❌ Repository: {e}")
        return False
    
    return True

def test_config():
    """Тестирует конфигурацию"""
    print("\n=== Тест конфигурации ===")
    
    try:
        from api_watcher.config import Config
        
        # Проверяем основные файлы
        if os.path.exists(Config.URLS_FILE):
            print(f"✅ URLs файл найден: {Config.URLS_FILE}")
        else:
            print(f"❌ URLs файл не найден: {Config.URLS_FILE}")
            return False
        
        # Проверяем .env
        env_file = '/opt/api-tracker/.env'
        if os.path.exists(env_file):
            print(f"✅ .env файл найден: {env_file}")
        else:
            print(f"❌ .env файл не найден: {env_file}")
        
        # Проверяем настройки
        print(f"   ZenRows: {'✅' if Config.is_zenrows_configured() else '❌'}")
        print(f"   OpenRouter: {'✅' if Config.is_openrouter_configured() else '❌'}")
        print(f"   Webhook: {'✅' if Config.is_webhook_configured() else '❌'}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка конфигурации: {e}")
        return False

def test_database():
    """Тестирует подключение к базе данных"""
    print("\n=== Тест базы данных ===")
    
    try:
        from api_watcher.config import Config
        from api_watcher.storage.repository import SQLAlchemySnapshotRepository
        
        repo = SQLAlchemySnapshotRepository(Config.DATABASE_URL)
        print("✅ Подключение к БД успешно")
        repo.close()
        return True
        
    except Exception as e:
        print(f"❌ Ошибка БД: {e}")
        return False

def test_watcher_creation():
    """Тестирует создание экземпляра APIWatcher"""
    print("\n=== Тест создания APIWatcher ===")
    
    try:
        from api_watcher.watcher import APIWatcher
        
        watcher = APIWatcher()
        print("✅ APIWatcher создан успешно")
        
        # Проверяем компоненты
        if hasattr(watcher, 'repository'):
            print("✅ Repository инициализирован")
        if hasattr(watcher, 'fetcher'):
            print("✅ Fetcher инициализирован")
        if hasattr(watcher, 'notifiers'):
            print("✅ Notifiers инициализированы")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка создания APIWatcher: {e}")
        traceback.print_exc()
        return False

def main():
    """Основная функция тестирования"""
    print("=== API Watcher Diagnostic Test ===")
    print(f"Python версия: {sys.version}")
    print(f"Рабочая директория: {os.getcwd()}")
    print(f"Python path: {sys.path[:3]}...")
    
    tests = [
        test_imports,
        test_config,
        test_database,
        test_watcher_creation
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Неожиданная ошибка в тесте {test.__name__}: {e}")
            traceback.print_exc()
    
    print(f"\n=== Результат: {passed}/{total} тестов пройдено ===")
    
    if passed == total:
        print("✅ Все тесты пройдены! API Watcher готов к работе.")
        return 0
    else:
        print("❌ Есть проблемы, которые нужно исправить.")
        return 1

if __name__ == '__main__':
    sys.exit(main())