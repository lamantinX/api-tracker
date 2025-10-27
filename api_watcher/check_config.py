#!/usr/bin/env python3
"""
Проверка конфигурации API Watcher
"""

import os
import sys

# Загружаем переменные окружения
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ python-dotenv загружен")
except ImportError:
    print("⚠️ python-dotenv не установлен, используем системные переменные")

from config import Config

def check_config():
    print("🔍 Проверка конфигурации API Watcher")
    print("=" * 50)
    
    # Основные настройки
    print("\n📁 Основные настройки:")
    print(f"  Директория снимков: {Config.SNAPSHOTS_DIR}")
    print(f"  Файл URL: {Config.URLS_FILE}")
    print(f"  Таймаут: {Config.REQUEST_TIMEOUT}с")
    print(f"  Уровень логов: {Config.LOG_LEVEL}")
    
    # Проверяем файлы
    print("\n📄 Проверка файлов:")
    
    # urls.json
    urls_path = Config.URLS_FILE
    if os.path.exists(urls_path):
        print(f"  ✅ {urls_path} найден")
        try:
            import json
            with open(urls_path, 'r', encoding='utf-8') as f:
                urls = json.load(f)
            print(f"     📊 Источников: {len(urls)}")
        except Exception as e:
            print(f"     ❌ Ошибка чтения: {e}")
    else:
        print(f"  ❌ {urls_path} не найден")
    
    # snapshots директория
    if os.path.exists(Config.SNAPSHOTS_DIR):
        snapshots = [f for f in os.listdir(Config.SNAPSHOTS_DIR) if f.endswith('.json')]
        print(f"  ✅ {Config.SNAPSHOTS_DIR}/ найдена ({len(snapshots)} снимков)")
    else:
        print(f"  ⚠️ {Config.SNAPSHOTS_DIR}/ не найдена (будет создана)")
    
    # .env файл
    env_path = ".env"
    if os.path.exists(env_path):
        print(f"  ✅ {env_path} найден")
    else:
        print(f"  ⚠️ {env_path} не найден")
    
    # Telegram настройки
    print("\n📱 Telegram настройки:")
    print(f"  Токен бота: {'✅ Настроен' if Config.TELEGRAM_BOT_TOKEN and Config.TELEGRAM_BOT_TOKEN != 'your_bot_token_here' else '❌ Не настроен'}")
    print(f"  Chat ID: {'✅ Настроен' if Config.TELEGRAM_CHAT_ID and Config.TELEGRAM_CHAT_ID != 'your_chat_id_here' else '❌ Не настроен'}")
    print(f"  Статус: {'✅ Готов к работе' if Config.is_telegram_configured() else '❌ Требует настройки'}")
    
    if Config.TELEGRAM_BOT_TOKEN and Config.TELEGRAM_BOT_TOKEN != 'your_bot_token_here':
        print(f"  Токен: {Config.TELEGRAM_BOT_TOKEN[:10]}...{Config.TELEGRAM_BOT_TOKEN[-5:] if len(Config.TELEGRAM_BOT_TOKEN) > 15 else Config.TELEGRAM_BOT_TOKEN}")
    
    if Config.TELEGRAM_CHAT_ID and Config.TELEGRAM_CHAT_ID != 'your_chat_id_here':
        print(f"  Chat ID: {Config.TELEGRAM_CHAT_ID}")
    
    # Тест Telegram
    if Config.is_telegram_configured():
        print("\n🧪 Тестирование Telegram...")
        try:
            from notifier.telegram_notifier import TelegramNotifier
            
            notifier = TelegramNotifier(Config.TELEGRAM_BOT_TOKEN, Config.TELEGRAM_CHAT_ID)
            
            if notifier.test_connection():
                print("  ✅ Telegram работает корректно!")
            else:
                print("  ❌ Ошибка подключения к Telegram")
                
        except Exception as e:
            print(f"  ❌ Ошибка тестирования: {e}")
    else:
        print("\n⚠️ Telegram не настроен")
        print("  Для настройки запустите: python quick_telegram_setup.py")
    
    # Проверка зависимостей
    print("\n📦 Проверка зависимостей:")
    required_packages = [
        'requests', 'beautifulsoup4', 'deepdiff', 'yaml', 'dotenv'
    ]
    
    for package in required_packages:
        try:
            if package == 'yaml':
                import yaml
            elif package == 'dotenv':
                import dotenv
            else:
                __import__(package.replace('-', '_'))
            print(f"  ✅ {package}")
        except ImportError:
            print(f"  ❌ {package} не установлен")
    
    print("\n" + "=" * 50)
    
    # Итоговый статус
    if Config.is_telegram_configured():
        print("🎉 Конфигурация готова! Можно запускать API Watcher.")
    else:
        print("⚠️ Telegram не настроен. Уведомления будут только в консоли.")
    
    print("\n🚀 Для запуска: python main.py")

if __name__ == "__main__":
    check_config()