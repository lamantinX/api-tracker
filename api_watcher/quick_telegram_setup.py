#!/usr/bin/env python3
"""
Быстрая настройка Telegram для API Watcher
"""

import os

def quick_setup():
    print("🚀 Быстрая настройка Telegram для API Watcher")
    print("=" * 50)
    
    print("\n📋 Для настройки Telegram уведомлений вам нужно:")
    print("1. 🤖 Токен бота (получить от @BotFather)")
    print("2. 💬 Chat ID (ваш ID в Telegram)")
    
    print("\n🔧 Способы получения:")
    print("1. Автоматическая настройка: python setup_telegram.py")
    print("2. Ручная настройка: отредактируйте .env файл")
    
    choice = input("\nВыберите способ (1 - авто, 2 - ручной, Enter - пропустить): ").strip()
    
    if choice == "1":
        print("\n🤖 Запускаем автоматическую настройку...")
        os.system("python setup_telegram.py")
    elif choice == "2":
        print("\n📝 Ручная настройка:")
        print("1. Создайте бота у @BotFather в Telegram")
        print("2. Получите токен бота")
        print("3. Узнайте свой chat_id (можно у @userinfobot)")
        print("4. Отредактируйте файл .env:")
        print("   TELEGRAM_BOT_TOKEN=ваш_токен")
        print("   TELEGRAM_CHAT_ID=ваш_chat_id")
        
        token = input("\n🔑 Введите токен бота (или Enter для пропуска): ").strip()
        chat_id = input("💬 Введите chat_id (или Enter для пропуска): ").strip()
        
        if token and chat_id:
            # Обновляем .env файл
            env_path = "../.env"
            try:
                # Читаем существующий .env
                env_content = ""
                if os.path.exists(env_path):
                    with open(env_path, 'r', encoding='utf-8') as f:
                        env_content = f.read()
                
                # Обновляем или добавляем токен и chat_id
                lines = env_content.split('\n')
                updated_lines = []
                token_updated = False
                chat_id_updated = False
                
                for line in lines:
                    if line.startswith('TELEGRAM_BOT_TOKEN='):
                        updated_lines.append(f'TELEGRAM_BOT_TOKEN={token}')
                        token_updated = True
                    elif line.startswith('TELEGRAM_CHAT_ID='):
                        updated_lines.append(f'TELEGRAM_CHAT_ID={chat_id}')
                        chat_id_updated = True
                    else:
                        updated_lines.append(line)
                
                # Добавляем, если не было
                if not token_updated:
                    updated_lines.append(f'TELEGRAM_BOT_TOKEN={token}')
                if not chat_id_updated:
                    updated_lines.append(f'TELEGRAM_CHAT_ID={chat_id}')
                
                # Сохраняем
                with open(env_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(updated_lines))
                
                print("✅ Настройки сохранены в .env файл")
                
                # Тестируем
                print("\n🧪 Тестируем соединение...")
                from notifier.telegram_notifier import TelegramNotifier
                
                notifier = TelegramNotifier(token, chat_id)
                if notifier.test_connection():
                    print("✅ Telegram настроен успешно!")
                else:
                    print("❌ Ошибка подключения к Telegram")
                    
            except Exception as e:
                print(f"❌ Ошибка сохранения: {e}")
    else:
        print("\n⏭️ Пропускаем настройку Telegram")
        print("Вы можете настроить позже, отредактировав .env файл")
    
    print("\n🎉 Настройка завершена!")
    print("Для тестирования запустите: python main.py")

if __name__ == "__main__":
    quick_setup()