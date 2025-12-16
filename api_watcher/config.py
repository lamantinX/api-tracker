"""
Конфигурационный файл для API Watcher
"""

import os
from typing import Optional
from dotenv import load_dotenv

# Load .env file from project root
load_dotenv()

class Config:
    """Класс конфигурации приложения"""
    
    # Основные настройки
    SNAPSHOTS_DIR = os.getenv('API_WATCHER_SNAPSHOTS_DIR', 'snapshots')
    URLS_FILE = os.getenv('API_WATCHER_URLS_FILE', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'urls.json'))
    
    # Настройки HTTP запросов
    REQUEST_TIMEOUT = int(os.getenv('API_WATCHER_TIMEOUT', '30'))
    USER_AGENT = os.getenv('API_WATCHER_USER_AGENT', 
                          'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    
    # Настройки Telegram (опционально)
    TELEGRAM_BOT_TOKEN: Optional[str] = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID: Optional[str] = os.getenv('TELEGRAM_CHAT_ID')
    
    # Настройки ZenRows
    ZENROWS_API_KEY: Optional[str] = os.getenv('ZENROWS_API_KEY')

    
    # Настройки Gemini AI (deprecated, используйте OpenRouter)
    GEMINI_API_KEY: Optional[str] = os.getenv('GEMINI_API_KEY')
    GEMINI_MODEL: str = os.getenv('GEMINI_MODEL', 'gemini-pro')
    
    # Настройки OpenRouter AI
    OPENROUTER_API_KEY: Optional[str] = os.getenv('OPENROUTER_API_KEY')
    OPENROUTER_MODEL: str = os.getenv('OPENROUTER_MODEL', 'anthropic/claude-3.5-sonnet')
    OPENROUTER_SITE_URL: Optional[str] = os.getenv('OPENROUTER_SITE_URL')
    OPENROUTER_APP_NAME: str = os.getenv('OPENROUTER_APP_NAME', 'API Watcher')
    
    # Настройки Slack
    SLACK_BOT_TOKEN: Optional[str] = os.getenv('SLACK_BOT_TOKEN')
    SLACK_CHANNEL: Optional[str] = os.getenv('SLACK_CHANNEL')
    
    # Настройки SerpAPI (для поиска документации)
    SERPAPI_KEY: Optional[str] = os.getenv('SERPAPI_KEY')
    
    # Настройки Webhook
    WEBHOOK_URL: Optional[str] = os.getenv('WEBHOOK_URL')
    
    # Настройки БД
    DATABASE_URL: str = os.getenv('DATABASE_URL', 'sqlite:///api_watcher.db')
    
    # Настройки сравнения
    IGNORE_ORDER = True
    VERBOSE_LEVEL = 2
    CHECK_INTERVAL_DAYS = int(os.getenv('CHECK_INTERVAL_DAYS', '7'))
    
    # Настройки логирования
    LOG_LEVEL = os.getenv('API_WATCHER_LOG_LEVEL', 'INFO')

    # Настройки режима работы
    DAEMON_MODE = os.getenv('API_WATCHER_DAEMON', 'false').lower() == 'true'
    CHECK_INTERVAL_SECONDS = int(os.getenv('API_WATCHER_CHECK_INTERVAL', '3600'))  # 1 hour default
    
    @classmethod
    def is_telegram_configured(cls) -> bool:
        """Проверяет, настроен ли Telegram"""
        return bool(cls.TELEGRAM_BOT_TOKEN and cls.TELEGRAM_CHAT_ID)
    
    @classmethod
    def is_zenrows_configured(cls) -> bool:
        """Проверяет, настроен ли ZenRows"""
        return bool(cls.ZENROWS_API_KEY)
    
    @classmethod
    def is_gemini_configured(cls) -> bool:
        """Проверяет, настроен ли Gemini AI"""
        return bool(cls.GEMINI_API_KEY)
    
    @classmethod
    def is_slack_configured(cls) -> bool:
        """Проверяет, настроен ли Slack"""
        return bool(cls.SLACK_BOT_TOKEN and cls.SLACK_CHANNEL)
    
    @classmethod
    def is_serpapi_configured(cls) -> bool:
        """Проверяет, настроен ли SerpAPI"""
        return bool(cls.SERPAPI_KEY)
    
    @classmethod
    def is_openrouter_configured(cls) -> bool:
        """Проверяет, настроен ли OpenRouter"""
        return bool(cls.OPENROUTER_API_KEY)
    
    @classmethod
    def is_webhook_configured(cls) -> bool:
        """Проверяет, настроен ли Webhook"""
        return bool(cls.WEBHOOK_URL)
    
    @classmethod
    def get_exclude_paths(cls) -> list:
        """Возвращает пути для исключения из сравнения"""
        return [
            "root['url']",
            "root['timestamp']",
        ]