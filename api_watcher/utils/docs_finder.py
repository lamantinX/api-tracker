"""
API Documentation Finder Integration
Интеграция с api_docs_finder для автоматического поиска документации
"""

import logging
import asyncio
from typing import Optional, Dict
from urllib.parse import urlparse
import aiohttp

from api_watcher.config import Config

logger = logging.getLogger(__name__)


class APIDocsFinder:
    """
    Адаптер для поиска документации API через различные источники
    """
    
    def __init__(self, serpapi_key: Optional[str] = None):
        """
        Инициализация поисковика документации
        
        Args:
            serpapi_key: Ключ SerpAPI для поисковых запросов
        """
        self.serpapi_key = serpapi_key
        self.session: Optional[aiohttp.ClientSession] = None
        self._semaphore: Optional[asyncio.Semaphore] = None

    async def _read_text_probe(self, response: aiohttp.ClientResponse) -> str:
        """
        Читает только ограниченный объём текста для эвристик (openapi/swagger),
        чтобы не триггерить излишний парсинг больших страниц.
        """
        max_bytes = max(1, int(getattr(Config, "MAX_PROBE_BYTES", 256 * 1024)))
        collected = bytearray()
        async for chunk in response.content.iter_chunked(32 * 1024):
            if not chunk:
                continue
            collected.extend(chunk)
            if len(collected) >= max_bytes:
                break

        charset = response.charset or "utf-8"
        return collected.decode(charset, errors="replace")
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        )
        self._semaphore = asyncio.Semaphore(
            max(1, int(getattr(Config, "DOCS_FINDER_MAX_CONCURRENT", 4)))
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
        self._semaphore = None
    
    @staticmethod
    def _extract_base_url(url: str) -> Optional[str]:
        """
        Извлекает базовый URL из полного URL
        
        Args:
            url: Полный URL
            
        Returns:
            Базовый URL (scheme + netloc) или None
        """
        try:
            parsed = urlparse(url)
            if parsed.scheme and parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}"
            return None
        except Exception as e:
            logger.error(f"Ошибка парсинга URL {url}: {e}")
            return None
    
    async def _check_openapi_path(self, base_url: str, path: str) -> Optional[str]:
        """
        Проверяет наличие OpenAPI документации по указанному пути
        
        Args:
            base_url: Базовый URL API
            path: Путь к документации
            
        Returns:
            Полный URL документации или None
        """
        if not self.session:
            return None
        
        full_url = f"{base_url}{path}"
        
        try:
            # Внутренние проверки лимитируем семафором, иначе это пробивает общий max_concurrent watcher'а
            if self._semaphore:
                async with self._semaphore:
                    async with self.session.get(full_url, allow_redirects=True) as response:
                        if response.status == 200:
                            content_type = response.headers.get('Content-Type', '')
                            
                            # Проверяем, что это JSON или YAML
                            if 'json' in content_type or 'yaml' in content_type or 'yml' in content_type:
                                logger.info(f"✅ Найдена OpenAPI документация: {full_url}")
                                return full_url
                            
                            # Проверяем содержимое на наличие OpenAPI/Swagger (только preview)
                            try:
                                text = await self._read_text_probe(response)
                                text_lower = text.lower()
                                if any(keyword in text_lower for keyword in ['openapi', 'swagger', '"paths":', '"info":']):
                                    logger.info(f"✅ Найдена OpenAPI документация: {full_url}")
                                    return full_url
                            except Exception:
                                pass
            else:
                async with self.session.get(full_url, allow_redirects=True) as response:
                    if response.status == 200:
                        content_type = response.headers.get('Content-Type', '')
                        if 'json' in content_type or 'yaml' in content_type or 'yml' in content_type:
                            logger.info(f"✅ Найдена OpenAPI документация: {full_url}")
                            return full_url
                        try:
                            text = await self._read_text_probe(response)
                            text_lower = text.lower()
                            if any(keyword in text_lower for keyword in ['openapi', 'swagger', '"paths":', '"info":']):
                                logger.info(f"✅ Найдена OpenAPI документация: {full_url}")
                                return full_url
                        except Exception:
                            pass
        
        except Exception as e:
            logger.debug(f"Не удалось проверить {full_url}: {e}")
        
        return None
    
    async def find_openapi_direct(self, url: str) -> Optional[str]:
        """
        Прямой поиск OpenAPI документации по стандартным путям
        
        Args:
            url: URL API метода
            
        Returns:
            URL найденной документации или None
        """
        base_url = self._extract_base_url(url)
        if not base_url:
            logger.warning(f"Не удалось извлечь базовый URL из {url}")
            return None
        
        logger.info(f"🔍 Поиск OpenAPI документации для {base_url}")
        
        # Стандартные пути для OpenAPI/Swagger документации
        standard_paths = [
            '/openapi.json',
            '/openapi.yaml',
            '/swagger.json',
            '/swagger.yaml',
            '/api-docs',
            '/api-docs.json',
            '/v1/openapi.json',
            '/v2/openapi.json',
            '/v3/openapi.json',
            '/docs/openapi.json',
            '/api/openapi.json',
            '/redoc',
            '/swagger',
            '/swagger-ui',
            '/api/swagger.json',
            '/api/swagger.yaml'
        ]
        
        # Проверяем все пути параллельно
        tasks = [
            self._check_openapi_path(base_url, path)
            for path in standard_paths
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Возвращаем первый найденный результат
        for result in results:
            if result and not isinstance(result, Exception):
                return result
        
        logger.info(f"❌ OpenAPI документация не найдена для {base_url}")
        return None
    
    async def search_via_serpapi(
        self,
        api_name: str,
        method_name: Optional[str] = None
    ) -> Optional[Dict[str, str]]:
        """
        Поиск документации через SerpAPI
        
        Args:
            api_name: Название API
            method_name: Название метода (опционально)
            
        Returns:
            Словарь с результатами поиска или None
        """
        if not self.serpapi_key:
            logger.warning("SerpAPI ключ не настроен, пропускаем поиск")
            return None
        
        if not self.session:
            return None
        
        # Формируем поисковый запрос
        query = f"{api_name} API documentation"
        if method_name:
            query += f" {method_name}"
        
        logger.info(f"🔍 Поиск через SerpAPI: {query}")
        
        try:
            params = {
                'q': query,
                'api_key': self.serpapi_key,
                'engine': 'google',
                'num': 3
            }
            
            async with self.session.get(
                'https://serpapi.com/search',
                params=params
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Извлекаем первый органический результат
                    organic_results = data.get('organic_results', [])
                    if organic_results:
                        first_result = organic_results[0]
                        return {
                            'title': first_result.get('title', ''),
                            'link': first_result.get('link', ''),
                            'snippet': first_result.get('snippet', '')
                        }
        
        except Exception as e:
            logger.error(f"Ошибка поиска через SerpAPI: {e}")
        
        return None
    
    async def find_documentation(
        self,
        url: str,
        api_name: Optional[str] = None,
        method_name: Optional[str] = None
    ) -> Optional[Dict[str, str]]:
        """
        Комплексный поиск документации API
        
        Стратегия:
        1. Прямой поиск OpenAPI документации
        2. Если не найдено - поиск через SerpAPI
        
        Args:
            url: URL API метода
            api_name: Название API
            method_name: Название метода
            
        Returns:
            Словарь с найденной документацией:
            {
                'type': 'openapi' | 'search',
                'url': str,
                'title': str (опционально),
                'snippet': str (опционально)
            }
        """
        # Шаг 1: Прямой поиск OpenAPI
        openapi_url = await self.find_openapi_direct(url)
        if openapi_url:
            return {
                'type': 'openapi',
                'url': openapi_url
            }
        
        # Шаг 2: Поиск через SerpAPI
        if api_name:
            search_result = await self.search_via_serpapi(api_name, method_name)
            if search_result and search_result.get('link'):
                return {
                    'type': 'search',
                    'url': search_result['link'],
                    'title': search_result.get('title', ''),
                    'snippet': search_result.get('snippet', '')
                }
        
        logger.warning(f"Документация не найдена для {url}")
        return None


async def find_api_documentation(
    url: str,
    api_name: Optional[str] = None,
    method_name: Optional[str] = None,
    serpapi_key: Optional[str] = None
) -> Optional[Dict[str, str]]:
    """
    Удобная функция для поиска документации API
    
    Args:
        url: URL API метода
        api_name: Название API
        method_name: Название метода
        serpapi_key: Ключ SerpAPI
        
    Returns:
        Словарь с найденной документацией или None
    """
    async with APIDocsFinder(serpapi_key) as finder:
        return await finder.find_documentation(url, api_name, method_name)
