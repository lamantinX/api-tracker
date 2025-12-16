"""
Async content fetcher using aiohttp
Асинхронное получение контента с retry логикой
"""

import asyncio
from typing import Optional, List
from dataclasses import dataclass

import aiohttp

from api_watcher.logging_config import get_logger

logger = get_logger(__name__)


@dataclass


@dataclass
class FetchResult:
    """Результат получения контента"""
    content: Optional[str]
    status_code: int
    success: bool
    error: Optional[str] = None
    url: str = ""
    attempts: int = 1


# Retryable HTTP status codes
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}

# Retryable exceptions
RETRYABLE_EXCEPTIONS = (
    asyncio.TimeoutError,
    aiohttp.ServerTimeoutError,
    aiohttp.ServerDisconnectedError,
    aiohttp.ClientConnectorError,
    ConnectionResetError,
)


class AsyncFetcher:
    """Асинхронный клиент для получения контента с retry"""
    
    DEFAULT_TIMEOUT = 30
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_RETRY_DELAY = 1.0
    DEFAULT_RETRY_MULTIPLIER = 2.0
    
    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        user_agent: str = Config.USER_AGENT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY,
        retry_multiplier: float = DEFAULT_RETRY_MULTIPLIER
    ):
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.headers = {'User-Agent': user_agent}
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.retry_multiplier = retry_multiplier
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Получает или создает сессию"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=self.timeout,
                headers=self.headers
            )
        return self._session
    
    def _is_retryable_status(self, status_code: int) -> bool:
        """Проверяет, можно ли повторить запрос для данного статуса"""
        return status_code in RETRYABLE_STATUS_CODES
    
    async def fetch(self, url: str, retry: bool = True) -> FetchResult:
        """
        Асинхронно получает контент URL с retry логикой
        
        Args:
            url: URL для получения
            retry: Включить retry при ошибках (default: True)
            
        Returns:
            FetchResult с контентом или ошибкой
        """
        last_error: Optional[str] = None
        last_status: int = 0
        attempts = 0
        delay = self.retry_delay
        
        max_attempts = self.max_retries if retry else 1
        
        for attempt in range(max_attempts):
            attempts = attempt + 1
            try:
                session = await self._get_session()
                async with session.get(url) as response:
                    content = await response.text()
                    
                    # Check if we should retry based on status code
                    if self._is_retryable_status(response.status) and attempt < max_attempts - 1:
                        logger.warning(
                            "retryable_status",
                            url=url,
                            status_code=response.status,
                            attempt=attempt + 1,
                            max_attempts=max_attempts
                        )
                        last_status = response.status
                        last_error = f"HTTP {response.status}"
                        await asyncio.sleep(delay)
                        delay *= self.retry_multiplier
                        continue
                    
                    return FetchResult(
                        content=content,
                        status_code=response.status,
                        success=response.status == 200,
                        url=url,
                        attempts=attempts
                    )
                    
            except RETRYABLE_EXCEPTIONS as e:
                last_error = str(e)
                last_status = 0
                
                if attempt < max_attempts - 1:
                    logger.warning(
                        "retryable_error",
                        url=url,
                        error=str(e),
                        attempt=attempt + 1,
                        max_attempts=max_attempts,
                        retry_delay=delay
                    )
                    await asyncio.sleep(delay)
                    delay *= self.retry_multiplier
                else:
                    logger.error("fetch_failed_after_retries", url=url, error=str(e), attempts=attempts)
                    
            except aiohttp.ClientError as e:
                # Non-retryable client errors
                logger.error("client_error", url=url, error=str(e))
                return FetchResult(
                    content=None,
                    status_code=0,
                    success=False,
                    error=str(e),
                    url=url,
                    attempts=attempts
                )
            except Exception as e:
                logger.error("unexpected_error", url=url, error=str(e), exc_info=True)
                return FetchResult(
                    content=None,
                    status_code=0,
                    success=False,
                    error=str(e),
                    url=url,
                    attempts=attempts
                )
        
        # All retries exhausted
        return FetchResult(
            content=None,
            status_code=last_status,
            success=False,
            error=last_error or "Max retries exceeded",
            url=url,
            attempts=attempts
        )
    
    async def fetch_many(self, urls: List[str]) -> List[FetchResult]:
        """
        Асинхронно получает контент нескольких URL
        
        Args:
            urls: Список URL
            
        Returns:
            Список FetchResult
        """
        tasks = [self.fetch(url) for url in urls]
        return await asyncio.gather(*tasks)
    
    async def close(self) -> None:
        """Закрывает сессию"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


class AsyncZenRowsFetcher:
    """Асинхронный клиент ZenRows с retry логикой"""
    
    BASE_URL = "https://api.zenrows.com/v1/"
    DEFAULT_MAX_RETRIES = 1
    DEFAULT_RETRY_DELAY = 2.0
    
    def __init__(
        self, 
        api_key: str, 
        timeout: int = 60,
        max_retries: int = DEFAULT_MAX_RETRIES
    ):
        self.api_key = api_key
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session
    
    async def fetch(
        self,
        url: str,
        js_render: bool = True,
        premium_proxy: bool = False,
        antibot: bool = True
    ) -> FetchResult:
        """Асинхронно получает контент через ZenRows с retry"""
        params = {
            'apikey': self.api_key,
            'url': url,
        }
        
        if js_render:
            params['js_render'] = 'true'
        if premium_proxy:
            params['premium_proxy'] = 'true'
        if antibot:
            params['antibot'] = 'true'
        
        last_error: Optional[str] = None
        delay = self.DEFAULT_RETRY_DELAY
        
        for attempt in range(self.max_retries):
            try:
                session = await self._get_session()
                async with session.get(self.BASE_URL, params=params) as response:
                    content = await response.text()
                    success = response.status == 200
                    
                    # Circuit Breaker for Critical Errors
                    if response.status == 402:
                        logger.critical("zenrows_payment_required_aborting", url=url)
                        raise Exception("ZenRows Payment Required (402) - Aborting to save funds")
                    
                    if response.status == 429:
                        logger.error("zenrows_rate_limit_aborting", url=url)
                        # Don't retry aggressively on 429, just fail this request
                        return FetchResult(
                            content=None,
                            status_code=429,
                            success=False,
                            error="Rate Limit Exceeded",
                            url=url,
                            attempts=attempt + 1
                        )

                    # Retry on 5xx errors
                    if response.status in {500, 502, 503, 504} and attempt < self.max_retries - 1:
                        logger.warning(
                            "zenrows_retry_status",
                            url=url,
                            status_code=response.status,
                            attempt=attempt + 1
                        )
                        await asyncio.sleep(delay)
                        delay *= 2
                        continue
                    
                    if success:
                        logger.info("zenrows_success", url=url, attempts=attempt + 1)
                    else:
                        logger.warning("zenrows_bad_status", url=url, status_code=response.status)
                    
                    return FetchResult(
                        content=content if success else None,
                        status_code=response.status,
                        success=success,
                        url=url,
                        attempts=attempt + 1
                    )
                    
            except RETRYABLE_EXCEPTIONS as e:
                last_error = str(e)
                if attempt < self.max_retries - 1:
                    logger.warning("zenrows_retry_error", url=url, error=str(e), attempt=attempt + 1)
                    await asyncio.sleep(delay)
                    delay *= 2
                else:
                    logger.error("zenrows_failed", url=url, error=str(e), attempts=attempt + 1)
                    
            except Exception as e:
                logger.error("zenrows_error", url=url, error=str(e), exc_info=True)
                return FetchResult(
                    content=None,
                    status_code=0,
                    success=False,
                    error=str(e),
                    url=url,
                    attempts=attempt + 1
                )
        
        return FetchResult(
            content=None,
            status_code=0,
            success=False,
            error=last_error or "Max retries exceeded",
            url=url,
            attempts=self.max_retries
        )
    
    async def fetch_with_fallback(self, url: str) -> Optional[str]:
        """Получает контент с fallback стратегией"""
        # Попытка 1: базовые настройки
        result = await self.fetch(url, js_render=True, premium_proxy=False)
        if result.success:
            return result.content
        
        logger.warning("zenrows_retry_no_js", url=url)
        
        # Попытка 2: без JS
        result = await self.fetch(url, js_render=False, premium_proxy=False)
        return result.content if result.success else None
    
    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


class ContentFetcher:
    """
    Фасад для получения контента
    Использует ZenRows если настроен, иначе прямой запрос
    """
    
    def __init__(
        self,
        zenrows_api_key: Optional[str] = None,
        timeout: int = 30,
        user_agent: str = Config.USER_AGENT,
        max_retries: int = 3
    ):
        self._direct = AsyncFetcher(
            timeout=timeout, 
            user_agent=user_agent,
            max_retries=max_retries
        )
        self._zenrows: Optional[AsyncZenRowsFetcher] = None
        
        if zenrows_api_key:
            self._zenrows = AsyncZenRowsFetcher(
                zenrows_api_key, 
                timeout=60,
                max_retries=max_retries
            )
            logger.info("zenrows_client_initialized")
    
    async def fetch(self, url: str) -> Optional[str]:
        """
        Получает контент URL
        
        Args:
            url: URL для получения
            
        Returns:
            Контент или None
        """
        if self._zenrows:
            logger.info("fetching_via_zenrows", url=url)
            return await self._zenrows.fetch_with_fallback(url)
        else:
            logger.debug("fetching_direct", url=url)
            result = await self._direct.fetch(url)
            return result.content if result.success else None
    
    async def fetch_many(self, urls: List[str]) -> dict[str, Optional[str]]:
        """
        Получает контент нескольких URL параллельно
        
        Args:
            urls: Список URL
            
        Returns:
            Словарь {url: content}
        """
        tasks = [self.fetch(url) for url in urls]
        results = await asyncio.gather(*tasks)
        return dict(zip(urls, results))
    
    async def close(self) -> None:
        """Закрывает все соединения"""
        await self._direct.close()
        if self._zenrows:
            await self._zenrows.close()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
