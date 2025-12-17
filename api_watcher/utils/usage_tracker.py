import json
import os
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

from api_watcher.config import Config
from api_watcher.logging_config import get_logger

logger = get_logger(__name__)

class UsageTracker:
    """
    Отслеживает использование API лимитов по дням.
    Сохраняет состояние в JSON файл.
    
    Потокобезопасный для параллельных асинхронных запросов.
    Использует asyncio.Lock для предотвращения race conditions.
    """
    
    def __init__(self, stats_file: str = "usage_stats.json"):
        self.stats_file = os.path.join(os.path.dirname(Config.SNAPSHOTS_DIR), stats_file)
        self._lock = asyncio.Lock()
        self._stats: Dict[str, Any] = self._load_stats()
        
    def _get_today_key(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")
        
    def _load_stats(self) -> Dict[str, Any]:
        """Загружает статистику из файла"""
        if not os.path.exists(self.stats_file):
            return {}
        try:
            with open(self.stats_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"failed_load_usage_stats: {e}")
            return {}
            
    def _save_stats(self):
        """Сохраняет статистику в файл"""
        try:
            # Создаем директорию если не существует
            os.makedirs(os.path.dirname(self.stats_file), exist_ok=True)
            with open(self.stats_file, 'w') as f:
                json.dump(self._stats, f, indent=2)
        except Exception as e:
            logger.error(f"failed_save_usage_stats: {e}")
    
    def _cleanup_old_days(self, today: str):
        """Удаляет статистику за старые дни (оставляет только сегодня)"""
        if today in self._stats:
            self._stats = {today: self._stats[today]}
        else:
            self._stats = {today: {}}
    
    async def get_usage(self, service_name: str) -> int:
        """
        Возвращает количество запросов за сегодня для сервиса.
        Потокобезопасный метод.
        """
        async with self._lock:
            # Перезагружаем статистику из файла для синхронизации между процессами
            self._stats = self._load_stats()
            today = self._get_today_key()
            if today not in self._stats:
                self._stats[today] = {}
            return self._stats.get(today, {}).get(service_name, 0)
        
    async def increment(self, service_name: str, count: int = 1):
        """
        Увеличивает счетчик использования.
        Потокобезопасный метод.
        """
        async with self._lock:
            # Перезагружаем статистику из файла для синхронизации между процессами
            self._stats = self._load_stats()
            today = self._get_today_key()
            
            # Если наступил новый день, очищаем старую статистику
            if today not in self._stats:
                self._cleanup_old_days(today)
            
            day_stats = self._stats.setdefault(today, {})
            current = day_stats.get(service_name, 0)
            day_stats[service_name] = current + count
            
            self._save_stats()
        
    async def can_use(self, service_name: str, limit: int) -> bool:
        """
        Проверяет, можно ли использовать сервис.
        Потокобезопасный метод.
        
        Args:
            service_name: Имя сервиса
            limit: Лимит запросов (-1 = безлимит, 0 = отключено, >0 = лимит)
            
        Returns:
            True если можно использовать, False если лимит превышен
        """
        # -1 = безлимит, 0 = отключено, >0 = лимит
        if limit < 0:
            return True
        if limit == 0:
            return False
        
        async with self._lock:
            # Перезагружаем статистику из файла для синхронизации между процессами
            self._stats = self._load_stats()
            today = self._get_today_key()
            if today not in self._stats:
                self._stats[today] = {}
            
            usage = self._stats.get(today, {}).get(service_name, 0)
            if usage >= limit:
                logger.warning(
                    "api_limit_exceeded", 
                    service=service_name, 
                    current_usage=usage, 
                    limit=limit
                )
                return False
            return True
    
    async def try_increment(self, service_name: str, limit: int, count: int = 1) -> bool:
        """
        Атомарная операция: проверяет лимит и инкрементирует счетчик в одной транзакции.
        Это предотвращает race condition между can_use() и increment().
        
        Args:
            service_name: Имя сервиса
            limit: Лимит запросов (-1 = безлимит, 0 = отключено, >0 = лимит)
            count: Количество для инкремента (по умолчанию 1)
            
        Returns:
            True если инкремент выполнен успешно, False если лимит превышен
        """
        # -1 = безлимит, 0 = отключено, >0 = лимит
        if limit < 0:
            # Безлимит - просто инкрементируем
            await self.increment(service_name, count)
            return True
        if limit == 0:
            return False
        
        async with self._lock:
            # Перезагружаем статистику из файла для синхронизации между процессами
            self._stats = self._load_stats()
            today = self._get_today_key()
            
            # Если наступил новый день, очищаем старую статистику
            if today not in self._stats:
                self._cleanup_old_days(today)
            
            day_stats = self._stats.setdefault(today, {})
            current = day_stats.get(service_name, 0)
            
            # Проверяем лимит ПЕРЕД инкрементом
            if current + count > limit:
                logger.warning(
                    "api_limit_exceeded_atomic", 
                    service=service_name, 
                    current_usage=current, 
                    requested=count,
                    limit=limit
                )
                return False
            
            # Атомарно инкрементируем
            day_stats[service_name] = current + count
            self._save_stats()
            return True
