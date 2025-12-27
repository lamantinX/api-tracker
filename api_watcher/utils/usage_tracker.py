import json
import os
from datetime import datetime
from typing import Dict, Any

from api_watcher.config import Config
from api_watcher.logging_config import get_logger

logger = get_logger(__name__)

class UsageTracker:
    """
    Отслеживает использование API лимитов по дням.
    Сохраняет состояние в JSON файл.
    """
    
    def __init__(self, stats_file: str = "usage_stats.json"):
        self.stats_file = os.path.join(os.path.dirname(Config.SNAPSHOTS_DIR), stats_file)
        self._stats: Dict[str, Any] = self._load_stats()
        
    def _get_today_key(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")
        
    def _load_stats(self) -> Dict[str, Any]:
        if not os.path.exists(self.stats_file):
            return {}
        try:
            with open(self.stats_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"failed_load_usage_stats: {e}")
            return {}
            
    def _save_stats(self):
        try:
            with open(self.stats_file, 'w') as f:
                json.dump(self._stats, f, indent=2)
        except Exception as e:
            logger.error(f"failed_save_usage_stats: {e}")
            
    def get_usage(self, service_name: str) -> int:
        """Возвращает количество запросов за сегодня для сервиса"""
        today = self._get_today_key()
        if today not in self._stats:
            self._stats = {today: {}} # Сброс старых дней или инициализация
            
        return self._stats.get(today, {}).get(service_name, 0)
        
    def increment(self, service_name: str, count: int = 1):
        """Увеличивает счетчик использования"""
        today = self._get_today_key()
        
        # Если наступил новый день, очищаем старую статистику (опционально, сейчас просто добавляем новый ключ)
        if today not in self._stats:
            # Можно хранить историю, но чтобы файл не пух, можно удалять старое?
            # Пока оставим простую логику - ключ по дате.
            # Если файл станет большим, можно сделать cleanup.
            pass
            
        day_stats = self._stats.setdefault(today, {})
        current = day_stats.get(service_name, 0)
        day_stats[service_name] = current + count
        
        self._save_stats()
        
    def can_use(self, service_name: str, limit: int) -> bool:
        """Проверяет, можно ли использовать сервис"""
        # -1 = безлимит, 0 = отключено, >0 = лимит
        if limit < 0:
            return True
        if limit == 0:
            return False
        
        usage = self.get_usage(service_name)
        if usage >= limit:
            logger.warning(
                "api_limit_exceeded", 
                service=service_name, 
                current_usage=usage, 
                limit=limit
            )
            return False
        return True
