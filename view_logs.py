#!/usr/bin/env python3
"""
Скрипт для удобного просмотра логов API Watcher
"""

import os
import sys
import json
import subprocess
from datetime import datetime, timedelta
from typing import List, Dict, Optional

def get_log_files() -> Dict[str, str]:
    """Получает пути к файлам логов"""
    log_files = {}
    
    # Основные логи приложения
    app_logs = [
        '/opt/api-tracker/api_watcher.log',
        '/opt/api-tracker/api_watcher/api_watcher.log',
        'api_watcher.log'
    ]
    
    for log_path in app_logs:
        if os.path.exists(log_path):
            log_files['app'] = log_path
            break
    
    # Логи systemd
    systemd_logs = [
        '/var/log/api-watcher/watcher.log',
        '/var/log/api-watcher/watcher.error.log'
    ]
    
    for log_path in systemd_logs:
        if os.path.exists(log_path):
            if 'error' in log_path:
                log_files['systemd_error'] = log_path
            else:
                log_files['systemd'] = log_path
    
    return log_files

def view_systemd_journal(lines: int = 50, follow: bool = False):
    """Просмотр логов systemd через journalctl"""
    print("=== Логи systemd (journalctl) ===")
    
    try:
        cmd = ['journalctl', '-u', 'api-watcher.service', '-n', str(lines), '--no-pager']
        if follow:
            cmd.append('-f')
        
        result = subprocess.run(cmd, capture_output=not follow, text=True)
        
        if follow:
            # Для режима follow просто запускаем команду
            return
        
        if result.returncode == 0:
            print(result.stdout)
        else:
            print(f"❌ Ошибка получения логов: {result.stderr}")
            
    except FileNotFoundError:
        print("❌ journalctl не найден. Возможно, systemd не используется.")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

def view_file_logs(log_files: Dict[str, str], lines: int = 50, follow: bool = False):
    """Просмотр логов из файлов"""
    for log_type, log_path in log_files.items():
        print(f"\n=== {log_type.upper()} LOG: {log_path} ===")
        
        try:
            if follow:
                # Для режима follow используем tail -f
                subprocess.run(['tail', '-f', log_path])
            else:
                # Читаем последние N строк
                with open(log_path, 'r', encoding='utf-8') as f:
                    all_lines = f.readlines()
                    recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
                    
                    for line in recent_lines:
                        print(line.rstrip())
                        
        except FileNotFoundError:
            print(f"❌ Файл не найден: {log_path}")
        except Exception as e:
            print(f"❌ Ошибка чтения файла: {e}")

def parse_structured_logs(log_files: Dict[str, str], filter_level: Optional[str] = None):
    """Парсинг структурированных JSON логов"""
    print("=== Структурированные логи ===")
    
    for log_type, log_path in log_files.items():
        if not os.path.exists(log_path):
            continue
            
        print(f"\n--- {log_type.upper()} ---")
        
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()[-100:]  # Последние 100 строк
                
            parsed_logs = []
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                try:
                    # Пытаемся парсить как JSON
                    log_entry = json.loads(line)
                    
                    # Фильтруем по уровню если нужно
                    if filter_level:
                        entry_level = log_entry.get('level', '').upper()
                        if entry_level != filter_level.upper():
                            continue
                    
                    parsed_logs.append(log_entry)
                    
                except json.JSONDecodeError:
                    # Если не JSON, показываем как есть
                    if not filter_level:  # Показываем только если нет фильтра
                        print(f"[TEXT] {line}")
            
            # Показываем структурированные логи
            for entry in parsed_logs[-20:]:  # Последние 20
                timestamp = entry.get('timestamp', entry.get('time', 'Unknown'))
                level = entry.get('level', 'INFO').upper()
                message = entry.get('message', entry.get('msg', ''))
                logger = entry.get('logger', entry.get('name', ''))
                
                # Цветовая схема для уровней
                level_colors = {
                    'DEBUG': '🔍',
                    'INFO': '✅',
                    'WARNING': '⚠️',
                    'ERROR': '❌',
                    'CRITICAL': '🚨'
                }
                
                icon = level_colors.get(level, '📝')
                
                print(f"{icon} [{timestamp}] {level} {logger}")
                print(f"   {message}")
                
                # Дополнительные поля
                for key, value in entry.items():
                    if key not in ['timestamp', 'time', 'level', 'message', 'msg', 'logger', 'name']:
                        print(f"   {key}: {value}")
                
                print()
                
        except Exception as e:
            print(f"❌ Ошибка парсинга {log_path}: {e}")

def search_logs(log_files: Dict[str, str], search_term: str, lines_context: int = 3):
    """Поиск в логах"""
    print(f"=== Поиск '{search_term}' в логах ===")
    
    for log_type, log_path in log_files.items():
        if not os.path.exists(log_path):
            continue
            
        print(f"\n--- {log_type.upper()}: {log_path} ---")
        
        try:
            # Используем grep для поиска
            cmd = ['grep', '-n', '-i', '-C', str(lines_context), search_term, log_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                print(result.stdout)
            else:
                print("Совпадений не найдено")
                
        except Exception as e:
            print(f"❌ Ошибка поиска: {e}")

def show_log_stats(log_files: Dict[str, str]):
    """Показывает статистику логов"""
    print("=== Статистика логов ===")
    
    for log_type, log_path in log_files.items():
        if not os.path.exists(log_path):
            continue
            
        try:
            # Размер файла
            size = os.path.getsize(log_path)
            
            # Время последнего изменения
            mtime = datetime.fromtimestamp(os.path.getmtime(log_path))
            
            # Количество строк
            with open(log_path, 'r', encoding='utf-8') as f:
                line_count = sum(1 for _ in f)
            
            print(f"\n{log_type.upper()}: {log_path}")
            print(f"  Размер: {size:,} байт ({size/1024/1024:.1f} MB)")
            print(f"  Строк: {line_count:,}")
            print(f"  Изменен: {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Анализ последних записей для определения активности
            with open(log_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if lines:
                    last_line = lines[-1].strip()
                    print(f"  Последняя запись: {last_line[:100]}...")
            
        except Exception as e:
            print(f"❌ Ошибка анализа {log_path}: {e}")

def main():
    """Основная функция"""
    print("=== API Watcher - Просмотр логов ===")
    
    # Получаем доступные лог файлы
    log_files = get_log_files()
    
    if not log_files:
        print("❌ Лог файлы не найдены")
        print("Проверьте:")
        print("- /opt/api-tracker/api_watcher.log")
        print("- /var/log/api-watcher/")
        print("- journalctl -u api-watcher.service")
        return
    
    print(f"Найдено лог файлов: {len(log_files)}")
    for log_type, path in log_files.items():
        print(f"  {log_type}: {path}")
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "follow" or command == "-f":
            print("\n=== Режим отслеживания (Ctrl+C для выхода) ===")
            try:
                view_systemd_journal(follow=True)
            except KeyboardInterrupt:
                print("\nОтслеживание остановлено")
                
        elif command == "systemd":
            lines = int(sys.argv[2]) if len(sys.argv) > 2 else 50
            view_systemd_journal(lines=lines)
            
        elif command == "files":
            lines = int(sys.argv[2]) if len(sys.argv) > 2 else 50
            view_file_logs(log_files, lines=lines)
            
        elif command == "json":
            filter_level = sys.argv[2] if len(sys.argv) > 2 else None
            parse_structured_logs(log_files, filter_level)
            
        elif command == "search":
            if len(sys.argv) < 3:
                print("❌ Укажите поисковый запрос: python view_logs.py search 'error'")
                return
            search_term = sys.argv[2]
            search_logs(log_files, search_term)
            
        elif command == "stats":
            show_log_stats(log_files)
            
        elif command == "errors":
            parse_structured_logs(log_files, filter_level="ERROR")
            
        else:
            print(f"❌ Неизвестная команда: {command}")
            
    else:
        # По умолчанию показываем статистику и последние записи
        show_log_stats(log_files)
        
        print(f"\n=== Последние записи ===")
        view_systemd_journal(lines=20)
        view_file_logs(log_files, lines=10)
    
    print(f"\n=== Использование ===")
    print("python view_logs.py                    # Статистика и последние записи")
    print("python view_logs.py follow             # Отслеживание в реальном времени")
    print("python view_logs.py systemd [N]        # N последних записей systemd")
    print("python view_logs.py files [N]          # N последних записей из файлов")
    print("python view_logs.py json [LEVEL]       # Структурированные логи")
    print("python view_logs.py search 'текст'     # Поиск в логах")
    print("python view_logs.py stats              # Статистика файлов")
    print("python view_logs.py errors             # Только ошибки")

if __name__ == '__main__':
    main()