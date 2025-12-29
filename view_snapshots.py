#!/usr/bin/env python3
"""
Скрипт для просмотра снэпшотов API Watcher
"""

import sys
import os
import json
from datetime import datetime, timedelta
from typing import Optional

# Добавляем путь к проекту
sys.path.insert(0, '/opt/api-tracker')

def view_database_snapshots():
    """Просмотр снэпшотов из базы данных"""
    try:
        from api_watcher.config import Config
        from api_watcher.storage.database import DatabaseManager
        
        print("=== Снэпшоты из базы данных ===")
        print(f"База данных: {Config.DATABASE_URL}")
        
        db = DatabaseManager(Config.DATABASE_URL)
        
        # Получаем все URL
        urls = db.get_all_urls()
        print(f"\nОтслеживается URL: {len(urls)}")
        
        for i, url in enumerate(urls, 1):
            print(f"\n{i}. {url}")
            
            # Последний снэпшот
            latest = db.get_latest_snapshot(url)
            if latest:
                print(f"   Последний снэпшот: {latest.created_at}")
                print(f"   API: {latest.api_name or 'Не указано'}")
                print(f"   Метод: {latest.method_name or 'Не указано'}")
                print(f"   Тип: {latest.content_type}")
                print(f"   Есть изменения: {'Да' if latest.has_changes else 'Нет'}")
                if latest.ai_summary:
                    print(f"   AI сводка: {latest.ai_summary[:100]}...")
            
            # История
            history = db.get_snapshot_history(url, limit=5)
            if len(history) > 1:
                print(f"   История ({len(history)} записей):")
                for snap in history[:3]:
                    status = "🔄 Изменения" if snap.has_changes else "✅ Без изменений"
                    print(f"     - {snap.created_at.strftime('%Y-%m-%d %H:%M')} {status}")
        
        # Недавние изменения
        print(f"\n=== Изменения за последние 7 дней ===")
        changes = db.get_snapshots_with_changes(days=7)
        
        if changes:
            for change in changes[:10]:
                print(f"\n🔄 {change.created_at.strftime('%Y-%m-%d %H:%M')}")
                print(f"   URL: {change.url}")
                print(f"   API: {change.api_name or 'Не указано'}")
                if change.ai_summary:
                    print(f"   Изменения: {change.ai_summary}")
        else:
            print("Изменений не найдено")
        
        db.close()
        
    except Exception as e:
        print(f"❌ Ошибка при работе с БД: {e}")
        return False
    
    return True

def view_file_snapshots():
    """Просмотр снэпшотов из файлов"""
    try:
        from api_watcher.config import Config
        
        snapshots_dir = Config.SNAPSHOTS_DIR
        if not os.path.exists(snapshots_dir):
            print(f"❌ Директория снэпшотов не найдена: {snapshots_dir}")
            return False
        
        print(f"=== Файловые снэпшоты ===")
        print(f"Директория: {os.path.abspath(snapshots_dir)}")
        
        # Получаем все JSON файлы
        json_files = []
        for root, dirs, files in os.walk(snapshots_dir):
            for file in files:
                if file.endswith('.json'):
                    json_files.append(os.path.join(root, file))
        
        if not json_files:
            print("Файловых снэпшотов не найдено")
            return True
        
        print(f"\nНайдено файлов: {len(json_files)}")
        
        # Сортируем по времени изменения
        json_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        
        for i, file_path in enumerate(json_files[:10], 1):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                print(f"\n{i}. {os.path.basename(file_path)}")
                
                # Метаданные
                if 'metadata' in data:
                    meta = data['metadata']
                    print(f"   API: {meta.get('api_name', 'Не указано')}")
                    print(f"   Метод: {meta.get('method_name', 'Не указано')}")
                    print(f"   Дата: {meta.get('snapshot_date', 'Не указано')}")
                    print(f"   Время: {meta.get('snapshot_time', 'Не указано')}")
                
                # URL
                if 'url' in data:
                    print(f"   URL: {data['url']}")
                
                # Размер файла
                size = os.path.getsize(file_path)
                print(f"   Размер: {size:,} байт")
                
                # Время изменения файла
                mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                print(f"   Изменен: {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
                
            except Exception as e:
                print(f"   ❌ Ошибка чтения файла: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при просмотре файлов: {e}")
        return False

def export_snapshot_details(url_filter: Optional[str] = None):
    """Экспорт детальной информации о снэпшотах"""
    try:
        from api_watcher.config import Config
        from api_watcher.storage.database import DatabaseManager
        
        db = DatabaseManager(Config.DATABASE_URL)
        
        if url_filter:
            print(f"=== Детали для URL: {url_filter} ===")
            snapshots = db.get_snapshot_history(url_filter, limit=20)
        else:
            print("=== Все снэпшоты с изменениями ===")
            snapshots = db.get_snapshots_with_changes(days=30)
        
        if not snapshots:
            print("Снэпшоты не найдены")
            return
        
        for i, snap in enumerate(snapshots, 1):
            print(f"\n--- Снэпшот {i} ---")
            print(f"ID: {snap.id}")
            print(f"URL: {snap.url}")
            print(f"API: {snap.api_name or 'Не указано'}")
            print(f"Метод: {snap.method_name or 'Не указано'}")
            print(f"Тип: {snap.content_type}")
            print(f"Дата: {snap.created_at}")
            print(f"Изменения: {'Да' if snap.has_changes else 'Нет'}")
            print(f"Хеш: {snap.content_hash}")
            
            if snap.ai_summary:
                print(f"AI сводка: {snap.ai_summary}")
            
            if snap.text_content:
                print(f"Размер текста: {len(snap.text_content):,} символов")
            
            if snap.raw_html:
                print(f"Размер HTML: {len(snap.raw_html):,} символов")
        
        db.close()
        
    except Exception as e:
        print(f"❌ Ошибка экспорта: {e}")

def main():
    """Основная функция"""
    print("=== API Watcher - Просмотр снэпшотов ===")
    print(f"Рабочая директория: {os.getcwd()}")
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "db":
            view_database_snapshots()
        elif command == "files":
            view_file_snapshots()
        elif command == "details":
            url_filter = sys.argv[2] if len(sys.argv) > 2 else None
            export_snapshot_details(url_filter)
        else:
            print(f"Неизвестная команда: {command}")
            print("Доступные команды: db, files, details [url]")
    else:
        # По умолчанию показываем и БД и файлы
        print("Проверяем базу данных...")
        view_database_snapshots()
        
        print("\n" + "="*60)
        print("Проверяем файловые снэпшоты...")
        view_file_snapshots()
        
        print(f"\n=== Использование ===")
        print("python view_snapshots.py db          # Только база данных")
        print("python view_snapshots.py files       # Только файлы")
        print("python view_snapshots.py details     # Детали всех изменений")
        print("python view_snapshots.py details URL # Детали для конкретного URL")

if __name__ == '__main__':
    main()