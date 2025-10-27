#!/usr/bin/env python3
"""
Скрипт для настройки Telegram бота для API Watcher
"""

import os
import sys
import requests
from typing import Optional

def get_bot_info(token: str) -> Optional[dict]:
    """Получает информацию о боте"""
    try:
        response = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"❌ Ошибка получения информации о боте: {e}")
        return None

def get_updates(token: str) -> Optional[list]:
    """Получает последние обновления (сообщения) бота"""
    try:
        response = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=10)
        response.raise_for_status()
        return response.json().get('result', [])
    except Exception as e:
        print(f"❌ Ошибка получения обновлений: {e}")
        return None

def send_test_message(token: str, chat_id: str) -> bool:
    """Отправляет тестовое сообщение"""
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': '🤖 API Watcher настроен и готов к работе!\n\nТеперь вы будете получать уведомления об изменениях в API документации.',
            'parse_mode': 'Markdown'
        }
        
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        return result.get('ok', False)
        
    except Exception as e:
        print(f"❌ Ошибка отправки сообщения: {e}")
        return False

def main():
    print("🤖 Настройка Telegram бота для API Watcher")
    print("=" * 50)
    
    # Шаг 1: Получение токена
    print("\n📋 Шаг 1: Создание бота")
    print("1. Откройте Telegram и найдите @BotFather")
    print("2. Отправьте команду /newbot")
    print("3. Следуйте инструкциям для создания бота")
    print("4. Скопируйте полученный токен")
    
    token = input("\n🔑 Введите токен бота: ").strip()
    
    if not token or token == "your_bot_token_here":
        print("❌ Токен не введен или используется пример")
        return
    
    # Проверяем токен
    print("\n🔍 Проверяем токен...")
    bot_info = get_bot_info(token)
    
    if not bot_info or not bot_info.get('ok'):
        print("❌ Неверный токен бота")
        return
    
    bot_data = bot_info['result']
    print(f"✅ Бот найден: @{bot_data['username']} ({bot_data['first_name']})")
    
    # Шаг 2: Получение chat_id
    print("\n📋 Шаг 2: Получение Chat ID")
    print("1. Найдите вашего бота в Telegram")
    print("2. Отправьте боту любое сообщение (например: 'Привет')")
    print("3. Нажмите Enter для продолжения")
    
    input("Нажмите Enter после отправки сообщения боту...")
    
    print("\n🔍 Ищем ваш chat_id...")
    updates = get_updates(token)
    
    if not updates:
        print("❌ Не удалось получить сообщения. Убедитесь, что отправили сообщение боту.")
        return
    
    # Ищем последнее сообщение
    chat_ids = set()
    for update in updates:
        if 'message' in update:
            chat_id = update['message']['chat']['id']
            chat_ids.add(str(chat_id))
    
    if not chat_ids:
        print("❌ Сообщения не найдены. Отправьте сообщение боту и попробуйте снова.")
        return
    
    if len(chat_ids) == 1:
        chat_id = list(chat_ids)[0]
        print(f"✅ Chat ID найден: {chat_id}")
    else:
        print("📋 Найдено несколько chat_id:")
        for i, cid in enumerate(chat_ids, 1):
            print(f"  {i}. {cid}")
        
        try:
            choice = int(input("Выберите номер вашего chat_id: ")) - 1
            chat_id = list(chat_ids)[choice]
        except (ValueError, IndexError):
            print("❌ Неверный выбор")
            return
    
    # Шаг 3: Тестирование
    print(f"\n🧪 Тестируем отправку сообщения в chat {chat_id}...")
    
    if send_test_message(token, chat_id):
        print("✅ Тестовое сообщение отправлено успешно!")
    else:
        print("❌ Ошибка отправки тестового сообщения")
        return
    
    # Шаг 4: Сохранение конфигурации
    print("\n💾 Сохраняем конфигурацию...")
    
    env_content = f"""# API Watcher Configuration
# Автоматически сгенерировано setup_telegram.py

# Основные настройки
API_WATCHER_SNAPSHOTS_DIR=snapshots
API_WATCHER_URLS_FILE=urls.json
API_WATCHER_TIMEOUT=30
API_WATCHER_LOG_LEVEL=INFO

# User Agent для HTTP запросов
API_WATCHER_USER_AGENT=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36

# Telegram уведомления
TELEGRAM_BOT_TOKEN={token}
TELEGRAM_CHAT_ID={chat_id}
"""
    
    try:
        with open('../.env', 'w', encoding='utf-8') as f:
            f.write(env_content)
        print("✅ Конфигурация сохранена в .env файл")
    except Exception as e:
        print(f"❌ Ошибка сохранения конфигурации: {e}")
        print("\n📋 Добавьте эти строки в .env файл вручную:")
        print(f"TELEGRAM_BOT_TOKEN={token}")
        print(f"TELEGRAM_CHAT_ID={chat_id}")
    
    print("\n🎉 Настройка завершена!")
    print("Теперь API Watcher будет отправлять уведомления в Telegram при обнаружении изменений.")
    
    # Показываем как запустить тест
    print("\n🚀 Для тестирования запустите:")
    print("python api_watcher/main.py")

if __name__ == "__main__":
    main()