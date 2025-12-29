#!/usr/bin/env python3
"""
Простой просмотрщик базы данных SQLite для API Watcher
"""

import sqlite3
import sys
from datetime import datetime

def view_db_structure():
    """Показывает структуру базы данных"""
    conn = sqlite3.connect('api_watcher.db')
    cursor = conn.cursor()
    
    # Получаем список таблиц
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    
    print("=== Структура базы данных ===")
    print(f"Файл: api_watcher.db")
    print(f"Таблицы: {len(tables)}")
    
    for table in tables:
        table_name = table[0]
        print(f"\n--- Таблица: {table_name} ---")
        
        # Получаем структуру таблицы
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        
        print("Колонки:")
        for col in columns:
            print(f"  {col[1]} ({col[2]}) {'NOT NULL' if col[3] else 'NULL'} {'PK' if col[5] else ''}")
        
        # Получаем количество записей
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        print(f"Записей: {count}")
    
    conn.close()

def view_snapshots_summary():
    """Показывает сводку по снепшотам"""
    conn = sqlite3.connect('api_watcher.db')
    cursor = conn.cursor()
    
    print("\n=== Сводка по снепшотам ===")
    
    # Общая статистика
    cursor.execute("SELECT COUNT(*) FROM snapshots")
    total_snapshots = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT url) FROM snapshots")
    unique_urls = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM snapshots WHERE has_changes = 1")
    with_changes = cursor.fetchone()[0]
    
    print(f"Всего снепшотов: {total_snapshots}")
    print(f"Уникальных URL: {unique_urls}")
    print(f"С изменениями: {with_changes}")
    
    # Последние изменения
    print("\n--- Последние 10 изменений ---")
    cursor.execute("""
        SELECT url, api_name, method_name, created_at, ai_summary 
        FROM snapshots 
        WHERE has_changes = 1 
        ORDER BY created_at DESC 
        LIMIT 10
    """)
    
    changes = cursor.fetchall()
    for i, change in enumerate(changes, 1):
        url, api_name, method_name, created_at, ai_summary = change
        print(f"\n{i}. {created_at}")
        print(f"   API: {api_name or 'Не указано'}")
        print(f"   Метод: {method_name or 'Не указано'}")
        print(f"   URL: {url[:80]}...")
        if ai_summary:
            print(f"   Изменения: {ai_summary[:100]}...")
    
    # Статистика по типам контента
    print("\n--- Статистика по типам контента ---")
    cursor.execute("""
        SELECT content_type, COUNT(*) 
        FROM snapshots 
        GROUP BY content_type 
        ORDER BY COUNT(*) DESC
    """)
    
    content_types = cursor.fetchall()
    for content_type, count in content_types:
        print(f"  {content_type or 'Не указано'}: {count}")
    
    conn.close()

def view_recent_activity(days=7):
    """Показывает активность за последние дни"""
    conn = sqlite3.connect('api_watcher.db')
    cursor = conn.cursor()
    
    print(f"\n=== Активность за последние {days} дней ===")
    
    cursor.execute("""
        SELECT DATE(created_at) as date, 
               COUNT(*) as total,
               COUNT(CASE WHEN has_changes = 1 THEN 1 END) as changes
        FROM snapshots 
        WHERE created_at >= datetime('now', '-{} days')
        GROUP BY DATE(created_at)
        ORDER BY date DESC
    """.format(days))
    
    activity = cursor.fetchall()
    
    if not activity:
        print("Нет активности за указанный период")
        return
    
    for date, total, changes in activity:
        print(f"{date}: {total} снепшотов, {changes} изменений")
    
    conn.close()

def search_snapshots(query):
    """Поиск снепшотов по URL или API"""
    conn = sqlite3.connect('api_watcher.db')
    cursor = conn.cursor()
    
    print(f"\n=== Поиск: '{query}' ===")
    
    cursor.execute("""
        SELECT url, api_name, method_name, created_at, has_changes, ai_summary
        FROM snapshots 
        WHERE url LIKE ? OR api_name LIKE ? OR method_name LIKE ?
        ORDER BY created_at DESC
        LIMIT 20
    """, (f'%{query}%', f'%{query}%', f'%{query}%'))
    
    results = cursor.fetchall()
    
    if not results:
        print("Ничего не найдено")
        return
    
    for i, result in enumerate(results, 1):
        url, api_name, method_name, created_at, has_changes, ai_summary = result
        status = "🔄 Изменения" if has_changes else "✅ Без изменений"
        
        print(f"\n{i}. {created_at} {status}")
        print(f"   API: {api_name or 'Не указано'}")
        print(f"   Метод: {method_name or 'Не указано'}")
        print(f"   URL: {url}")
        if ai_summary:
            print(f"   Сводка: {ai_summary[:100]}...")
    
    conn.close()

def main():
    """Основная функция"""
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python db_viewer.py structure    # Структура БД")
        print("  python db_viewer.py summary      # Сводка по снепшотам")
        print("  python db_viewer.py activity [days] # Активность за N дней")
        print("  python db_viewer.py search <query>  # Поиск по URL/API")
        return
    
    command = sys.argv[1]
    
    try:
        if command == "structure":
            view_db_structure()
        elif command == "summary":
            view_snapshots_summary()
        elif command == "activity":
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
            view_recent_activity(days)
        elif command == "search":
            if len(sys.argv) < 3:
                print("Укажите поисковый запрос")
                return
            query = sys.argv[2]
            search_snapshots(query)
        else:
            print(f"Неизвестная команда: {command}")
    
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == '__main__':
    main()