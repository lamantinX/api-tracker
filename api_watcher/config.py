"""
Конфигурационный файл для API Watcher
"""

import os
from typing import Optional

class Config:
    """Класс конфигурации приложения"""
    
    # Основные настройки
    SNAPSHOTS_DIR = os.getenv('API_WATCHER_SNAPSHOTS_DIR', 'snapshots')
    URLS_FILE = os.getenv('API_WATCHER_URLS_FILE', 'urls.json')
    
    # Настройки HTTP запросов
    REQUEST_TIMEOUT = int(os.getenv('API_WATCHER_TIMEOUT', '30'))
    USER_AGENT = os.getenv('API_WATCHER_USER_AGENT', 
                          'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    
    # Настройки Telegram (опционально)
    TELEGRAM_BOT_TOKEN: Optional[str] = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID: Optional[str] = os.getenv('TELEGRAM_CHAT_ID')
    
    # Настройки сравнения
    IGNORE_ORDER = True
    VERBOSE_LEVEL = 2
    
    # Настройки логирования
    LOG_LEVEL = os.getenv('API_WATCHER_LOG_LEVEL', 'INFO')
    
    @classmethod
    def is_telegram_configured(cls) -> bool:
        """Проверяет, настроен ли Telegram"""
        return bool(cls.TELEGRAM_BOT_TOKEN and cls.TELEGRAM_CHAT_ID)
    
    @classmethod
    def get_exclude_paths(cls) -> list:
        """Возвращает пути для исключения из сравнения"""
        return [
            "root['url']",
            "root['timestamp']",
        ]