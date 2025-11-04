#!/usr/bin/env python3
"""
Health Check скрипт для API Watcher
Может использоваться для мониторинга состояния приложения
"""

import json
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path


def check_health(health_file: str = "health.json", max_age_minutes: int = 60) -> dict:
    """
    Проверяет состояние здоровья приложения
    
    Args:
        health_file: Путь к файлу здоровья
        max_age_minutes: Максимальный возраст последнего обновления в минутах
    
    Returns:
        Словарь с результатами проверки
    """
    health_path = Path(health_file)
    
    if not health_path.exists():
        return {
            "status": "unknown",
            "message": "Health file not found",
            "healthy": False
        }
    
    try:
        with open(health_path, 'r', encoding='utf-8') as f:
            health_data = json.load(f)
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error reading health file: {e}",
            "healthy": False
        }
    
    # Проверяем возраст последнего обновления
    try:
        last_update = datetime.fromisoformat(health_data.get('timestamp', ''))
        age = datetime.now() - last_update
        
        if age > timedelta(minutes=max_age_minutes):
            return {
                "status": "stale",
                "message": f"Health data is too old ({age.total_seconds():.0f} seconds)",
                "healthy": False,
                "data": health_data
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Invalid timestamp in health file: {e}",
            "healthy": False,
            "data": health_data
        }
    
    # Проверяем статус
    status = health_data.get('status', 'unknown')
    healthy = status in ['healthy', 'degraded']
    
    return {
        "status": status,
        "message": "Health check passed" if healthy else f"Application status: {status}",
        "healthy": healthy,
        "data": health_data
    }


def main():
    parser = argparse.ArgumentParser(description='Health Check для API Watcher')
    parser.add_argument('--health-file', default='health.json', help='Путь к файлу здоровья')
    parser.add_argument('--max-age', type=int, default=60, help='Максимальный возраст данных в минутах')
    parser.add_argument('--json', action='store_true', help='Вывод в формате JSON')
    parser.add_argument('--quiet', action='store_true', help='Тихий режим (только код выхода)')
    
    args = parser.parse_args()
    
    result = check_health(args.health_file, args.max_age)
    
    if not args.quiet:
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Status: {result['status']}")
            print(f"Message: {result['message']}")
            if 'data' in result and result['data']:
                details = result['data'].get('details', {})
                if details:
                    print(f"Last run: {details.get('last_run', 'Unknown')}")
                    print(f"Total URLs: {details.get('total_urls', 'Unknown')}")
                    print(f"Successful: {details.get('successful', 'Unknown')}")
                    print(f"Failed: {details.get('failed', 'Unknown')}")
                    print(f"Changes detected: {details.get('changes_detected', 'Unknown')}")
    
    # Возвращаем соответствующий код выхода
    sys.exit(0 if result['healthy'] else 1)


if __name__ == "__main__":
    main()