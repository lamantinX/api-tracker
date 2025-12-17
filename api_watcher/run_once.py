#!/usr/bin/env python3
"""
Скрипт для одноразового запуска API Watcher (без цикличности)
Запускает проверку всех URL один раз и завершает работу
"""

import asyncio
import os
import sys

# Добавляем родительскую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_watcher.watcher import APIWatcher
from api_watcher.config import Config
from api_watcher.logging_config import configure_logging, get_logger

# Инициализация логирования с читаемым форматом для консоли
# Используем 'console' формат вместо 'json' для удобного вывода
log_format = os.getenv('API_WATCHER_LOG_FORMAT', 'console')
log_level = os.getenv('API_WATCHER_LOG_LEVEL', 'INFO')
configure_logging(log_format=log_format, log_level=log_level)
logger = get_logger(__name__)


async def main():
    """Главная функция одноразового запуска"""
    logger.info("🚀 Запуск API Watcher (одна итерация)")
    
    # Принудительно отключаем daemon режим
    Config.DAEMON_MODE = False
    
    watcher = APIWatcher()
    
    try:
        # Обрабатываем все URLs параллельно
        results = await watcher.process_urls_parallel(
            Config.URLS_FILE,
            max_concurrent=10,
            delay_between_requests=0.2
        )
        
        # Статистика
        total = len(results)
        changed = sum(1 for r in results if r.get('has_changes'))
        errors = sum(1 for r in results if 'error' in r)
        
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 ИТОГОВАЯ СТАТИСТИКА")
        logger.info(f"{'='*60}")
        logger.info(f"Всего проверено: {total}")
        logger.info(f"Обнаружено изменений: {changed}")
        logger.info(f"Ошибок: {errors}")
        logger.info(f"{'='*60}\n")
        
        logger.info("✅ Проверка завершена успешно")
        return 0
        
    except Exception as e:
        logger.error(f"❌ Ошибка при выполнении проверки: {e}", exc_info=True)
        return 1
        
    finally:
        await watcher.cleanup()


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))

