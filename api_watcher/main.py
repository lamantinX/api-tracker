#!/usr/bin/env python3
"""
API Watcher - микросервис для мониторинга изменений в API документации
Точка входа приложения
"""

import json
import os
import asyncio
import aiohttp
import logging
import time
import sys
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass

from config import Config
from parsers.html_parser import HTMLParser
from parsers.openapi_parser import OpenAPIParser
from parsers.json_parser import JSONParser
from parsers.postman_parser import PostmanParser
from parsers.md_parser import MarkdownParser
from storage.snapshot_manager import SnapshotManager
from notifier.console_notifier import ConsoleNotifier
from notifier.telegram_notifier import TelegramNotifier
from utils.comparator import Comparator


@dataclass
class ProcessingResult:
    """Результат обработки URL"""
    url: str
    name: str
    success: bool
    error: Optional[str] = None
    changes_detected: bool = False
    processing_time: float = 0.0


class HealthChecker:
    """Класс для проверки здоровья приложения"""
    
    def __init__(self, health_file: str = "health.json"):
        self.health_file = health_file
        
    def update_health(self, status: str, details: Dict[str, Any]):
        """Обновляет файл здоровья"""
        health_data = {
            "timestamp": datetime.now().isoformat(),
            "status": status,
            "details": details
        }
        
        try:
            with open(self.health_file, 'w', encoding='utf-8') as f:
                json.dump(health_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Не удалось обновить health файл: {e}")
    
    def get_health(self) -> Dict[str, Any]:
        """Получает текущее состояние здоровья"""
        try:
            with open(self.health_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {"status": "unknown", "message": "Health file not found"}
        except Exception as e:
            return {"status": "error", "message": f"Error reading health file: {e}"}


class APIWatcher:
    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0, max_concurrent: int = 5):
        # Настройка логирования
        self._setup_logging()
        
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.max_concurrent = max_concurrent
        
        self.parsers = {
            'html': HTMLParser(),
            'openapi': OpenAPIParser(),
            'json': JSONParser(),
            'postman': PostmanParser(),
            'md': MarkdownParser()
        }
        self.snapshot_manager = SnapshotManager(Config.SNAPSHOTS_DIR)
        self.notifier = ConsoleNotifier()
        self.comparator = Comparator()
        self.health_checker = HealthChecker()
        
        # Инициализируем Telegram уведомления, если настроены
        if Config.is_telegram_configured():
            self.telegram_notifier = TelegramNotifier(
                Config.TELEGRAM_BOT_TOKEN, 
                Config.TELEGRAM_CHAT_ID
            )
            logging.info("📱 Telegram уведомления включены")
        else:
            self.telegram_notifier = None
            
    def _setup_logging(self):
        """Настройка системы логирования"""
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        log_level = getattr(logging, os.getenv('LOG_LEVEL', 'INFO').upper())
        
        # Настройка основного логгера
        logging.basicConfig(
            level=log_level,
            format=log_format,
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler('api_watcher.log', encoding='utf-8')
            ]
        )
        
        self.logger = logging.getLogger(__name__)

    def load_urls(self) -> List[Dict[str, str]]:
        """Загружает список URL из urls.json"""
        try:
            with open(Config.URLS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            self.logger.error(f"Файл {Config.URLS_FILE} не найден!")
            return []
        except json.JSONDecodeError as e:
            self.logger.error(f"Ошибка парсинга {Config.URLS_FILE}: {e}")
            return []

    async def process_url_with_retry(self, session: aiohttp.ClientSession, url_config: Dict[str, str]) -> ProcessingResult:
        """Обрабатывает один URL с повторными попытками"""
        url = url_config['url']
        name = url_config.get('name', url)
        
        for attempt in range(self.max_retries):
            try:
                result = await self._process_single_url(session, url_config)
                if result.success:
                    return result
                    
                if attempt < self.max_retries - 1:
                    self.logger.warning(f"Попытка {attempt + 1} неудачна для {name}, повтор через {self.retry_delay}с")
                    await asyncio.sleep(self.retry_delay * (2 ** attempt))  # Экспоненциальная задержка
                    
            except Exception as e:
                if attempt < self.max_retries - 1:
                    self.logger.warning(f"Ошибка при обработке {name} (попытка {attempt + 1}): {e}")
                    await asyncio.sleep(self.retry_delay * (2 ** attempt))
                else:
                    self.logger.error(f"Все попытки исчерпаны для {name}: {e}")
                    
        return ProcessingResult(url=url, name=name, success=False, error="Превышено количество попыток")

    async def _process_single_url(self, session: aiohttp.ClientSession, url_config: Dict[str, str]) -> ProcessingResult:
        """Обрабатывает один URL (одна попытка)"""
        start_time = time.time()
        url = url_config['url']
        doc_type = url_config['type']
        name = url_config.get('name', url)
        description = url_config.get('description', '')
        
        self.logger.info(f"Обрабатываем: {name}")
        self.logger.debug(f"  URL: {url}")
        if description:
            self.logger.debug(f"  Описание: {description}")
        
        if doc_type not in self.parsers:
            error_msg = f"Неподдерживаемый тип документации: {doc_type}"
            self.logger.error(error_msg)
            return ProcessingResult(url=url, name=name, success=False, error=error_msg)
        
        try:
            # Парсим данные с дополнительными параметрами
            parser = self.parsers[doc_type]
            
            # Передаем дополнительные параметры в зависимости от типа парсера
            if doc_type == 'html':
                selector = url_config.get('selector')
                current_data = parser.parse(url, selector=selector)
            elif doc_type == 'openapi':
                method_filter = url_config.get('method_filter')
                current_data = parser.parse(url, method_filter=method_filter)
            else:
                current_data = parser.parse(url)
            
            # Получаем method_filter для OpenAPI
            method_filter = url_config.get('method_filter') if doc_type == 'openapi' else None
            
            # Получаем предыдущий snapshot
            previous_data = self.snapshot_manager.load_snapshot(url, method_filter)
            
            changes_detected = False
            
            # Сравниваем данные
            if previous_data is not None:
                diff = self.comparator.compare(previous_data, current_data)
                if diff:
                    changes_detected = True
                    self.notifier.notify_changes(url, diff)
                    
                    # Отправляем Telegram уведомление, если настроено
                    if self.telegram_notifier:
                        self.telegram_notifier.notify_changes(url, diff)
                    
                    self.snapshot_manager.save_snapshot(url, current_data, name, self._extract_method_name(current_data), method_filter)
                    self.logger.info(f"✅ Обнаружены изменения в {name}")
                else:
                    self.logger.info(f"📄 Изменений не обнаружено в {name}")
            else:
                # Первый запуск - сохраняем snapshot
                self.snapshot_manager.save_snapshot(url, current_data, name, self._extract_method_name(current_data), method_filter)
                self.logger.info(f"💾 Создан первый snapshot для {name}")
            
            processing_time = time.time() - start_time
            return ProcessingResult(
                url=url, 
                name=name, 
                success=True, 
                changes_detected=changes_detected,
                processing_time=processing_time
            )
                
        except Exception as e:
            processing_time = time.time() - start_time
            self.logger.error(f"❌ Ошибка при обработке {name}: {e}", exc_info=True)
            return ProcessingResult(
                url=url, 
                name=name, 
                success=False, 
                error=str(e),
                processing_time=processing_time
            )

    async def run_async(self) -> Dict[str, Any]:
        """Асинхронный основной цикл выполнения"""
        start_time = time.time()
        self.logger.info("🚀 Запуск API Watcher...")
        
        urls = self.load_urls()
        if not urls:
            error_msg = "Нет URL для обработки"
            self.logger.warning(error_msg)
            self.health_checker.update_health("warning", {"message": error_msg})
            return {"status": "warning", "message": error_msg}
        
        # Создаем семафор для ограничения количества одновременных запросов
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def process_with_semaphore(session, url_config):
            async with semaphore:
                return await self.process_url_with_retry(session, url_config)
        
        try:
            # Создаем HTTP сессию с таймаутами
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Запускаем обработку всех URL параллельно
                tasks = [process_with_semaphore(session, url_config) for url_config in urls]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Анализируем результаты
                successful = 0
                failed = 0
                changes_detected = 0
                total_processing_time = time.time() - start_time
                
                for result in results:
                    if isinstance(result, Exception):
                        failed += 1
                        self.logger.error(f"Необработанная ошибка: {result}")
                    elif isinstance(result, ProcessingResult):
                        if result.success:
                            successful += 1
                            if result.changes_detected:
                                changes_detected += 1
                        else:
                            failed += 1
                    else:
                        failed += 1
                        self.logger.error(f"Неожиданный тип результата: {type(result)}")
                
                # Обновляем health status
                health_details = {
                    "total_urls": len(urls),
                    "successful": successful,
                    "failed": failed,
                    "changes_detected": changes_detected,
                    "processing_time": round(total_processing_time, 2),
                    "last_run": datetime.now().isoformat()
                }
                
                if failed == 0:
                    status = "healthy"
                    self.logger.info("✨ Обработка завершена успешно")
                elif successful > 0:
                    status = "degraded"
                    self.logger.warning(f"⚠️ Обработка завершена с ошибками: {failed} из {len(urls)} неудачных")
                else:
                    status = "unhealthy"
                    self.logger.error("❌ Все URL обработаны с ошибками")
                
                self.health_checker.update_health(status, health_details)
                
                return {
                    "status": status,
                    "details": health_details,
                    "results": [r for r in results if isinstance(r, ProcessingResult)]
                }
                
        except Exception as e:
            error_msg = f"Критическая ошибка при выполнении: {e}"
            self.logger.error(error_msg, exc_info=True)
            self.health_checker.update_health("unhealthy", {
                "error": error_msg,
                "last_run": datetime.now().isoformat()
            })
            return {"status": "unhealthy", "error": error_msg}

    def run(self) -> Dict[str, Any]:
        """Синхронная обертка для асинхронного выполнения"""
        try:
            return asyncio.run(self.run_async())
        except KeyboardInterrupt:
            self.logger.info("Получен сигнал прерывания, завершение работы...")
            return {"status": "interrupted", "message": "Работа прервана пользователем"}
        except Exception as e:
            error_msg = f"Неожиданная ошибка: {e}"
            self.logger.error(error_msg, exc_info=True)
            return {"status": "error", "error": error_msg}

    def _extract_method_name(self, data: Dict[str, Any]) -> str:
        """Извлекает название метода из данных"""
        if isinstance(data, dict):
            # Для HTML парсера
            method_content = data.get('method_content', {})
            if isinstance(method_content, dict):
                method_name = method_content.get('method_name', '')
                if method_name:
                    # Очищаем название метода от лишних символов
                    clean_name = method_name.replace('\n', ' ').strip()
                    if len(clean_name) > 50:
                        clean_name = clean_name[:50] + '...'
                    return clean_name
            
            # Для OpenAPI парсера
            if 'paths' in data:
                paths = data.get('paths', {})
                if paths:
                    first_path = list(paths.keys())[0] if paths else 'Unknown'
                    return f"OpenAPI: {first_path}"
            
            # Для JSON парсера
            if 'structure' in data:
                return "JSON API"
            
            # Для Markdown парсера
            if 'sections' in data:
                return "Markdown Doc"
        
        return "Unknown Method"


def main():
    """Точка входа приложения"""
    import argparse
    
    parser = argparse.ArgumentParser(description='API Watcher - мониторинг изменений API документации')
    parser.add_argument('--max-retries', type=int, default=3, help='Максимальное количество повторных попыток')
    parser.add_argument('--retry-delay', type=float, default=1.0, help='Задержка между повторными попытками (сек)')
    parser.add_argument('--max-concurrent', type=int, default=5, help='Максимальное количество одновременных запросов')
    parser.add_argument('--health-check', action='store_true', help='Показать текущее состояние здоровья и выйти')
    
    args = parser.parse_args()
    
    if args.health_check:
        health_checker = HealthChecker()
        health = health_checker.get_health()
        print(json.dumps(health, indent=2, ensure_ascii=False))
        sys.exit(0 if health.get('status') == 'healthy' else 1)
    
    watcher = APIWatcher(
        max_retries=args.max_retries,
        retry_delay=args.retry_delay,
        max_concurrent=args.max_concurrent
    )
    
    result = watcher.run()
    
    # Возвращаем соответствующий код выхода
    if result['status'] == 'healthy':
        sys.exit(0)
    elif result['status'] in ['degraded', 'warning']:
        sys.exit(1)
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()