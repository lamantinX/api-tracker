"""
Async content fetcher using aiohttp
Асинхронное получение контента с retry логикой
"""

import asyncio
import re
from datetime import date
from typing import Optional, List, Dict
from dataclasses import dataclass
from urllib.parse import urlparse

import aiohttp

from api_watcher.config import Config
from api_watcher.logging_config import get_logger

logger = get_logger(__name__)

# URL patterns that don't need ZenRows (static content)
STATIC_URL_PATTERNS = [
    r'raw\.githubusercontent\.com',
    r'\.json$',
    r'\.yaml$',
    r'\.yml$',
    r'\.xml$',
    r'/openapi\.',
    r'/swagger\.',
]
STATIC_URL_REGEX = re.compile('|'.join(STATIC_URL_PATTERNS), re.IGNORECASE)


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
    """Асинхронный клиент ZenRows с retry логикой и circuit breaker"""
    
    BASE_URL = "https://api.zenrows.com/v1/"
    DEFAULT_MAX_RETRIES = 1
    DEFAULT_RETRY_DELAY = 2.0
    
    # Per-domain failure tracking
    MAX_DOMAIN_FAILURES = 3  # После 3 фейлов домен блокируется на день
    MAX_CONSECUTIVE_ERRORS = 10  # После 10 ошибок подряд - глобальный circuit breaker
    
    def __init__(
        self, 
        api_key: str, 
        timeout: int = 60,
        max_retries: int = DEFAULT_MAX_RETRIES,
        daily_limit: int = 500,
        js_render: bool = True,
        antibot: bool = False
    ):
        self.api_key = api_key
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self.daily_limit = daily_limit
        self.js_render = js_render
        self.antibot = antibot
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Circuit breaker state
        self._disabled = False
        self._disabled_reason: Optional[str] = None
        
        # Daily request counter
        self._request_count = 0
        self._request_date = date.today()
        
        # Per-domain failure tracking (domain -> failure_count)
        self._domain_failures: Dict[str, int] = {}
        self._blocked_domains: set = set()
        
        # Consecutive error tracking for global circuit breaker
        self._consecutive_errors = 0
    
    def _reset_daily_counter_if_needed(self) -> None:
        """Сбрасывает счётчик если наступил новый день"""
        today = date.today()
        if self._request_date != today:
            logger.info("zenrows_daily_counter_reset", 
                       old_count=self._request_count, 
                       old_date=str(self._request_date),
                       blocked_domains=len(self._blocked_domains))
            self._request_count = 0
            self._request_date = today
            self._domain_failures.clear()
            self._blocked_domains.clear()
            self._consecutive_errors = 0
            # Также сбрасываем circuit breaker при новом дне
            if self._disabled_reason in ("daily_limit_exceeded", "consecutive_errors"):
                self._disabled = False
                self._disabled_reason = None
    
    def _extract_domain(self, url: str) -> str:
        """Извлекает домен из URL"""
        try:
            parsed = urlparse(url)
            return parsed.netloc or url
        except:
            return url
    
    def _is_domain_blocked(self, url: str) -> bool:
        """Проверяет, заблокирован ли домен"""
        domain = self._extract_domain(url)
        return domain in self._blocked_domains
    
    def _record_domain_failure(self, url: str) -> None:
        """Записывает ошибку для домена"""
        domain = self._extract_domain(url)
        self._domain_failures[domain] = self._domain_failures.get(domain, 0) + 1
        
        if self._domain_failures[domain] >= self.MAX_DOMAIN_FAILURES:
            self._blocked_domains.add(domain)
            logger.warning("zenrows_domain_blocked", 
                          domain=domain, 
                          failures=self._domain_failures[domain])
    
    def _record_domain_success(self, url: str) -> None:
        """Сбрасывает счётчик ошибок для домена при успехе"""
        domain = self._extract_domain(url)
        if domain in self._domain_failures:
            del self._domain_failures[domain]
    
    def _check_consecutive_errors(self) -> Optional[FetchResult]:
        """Проверяет количество последовательных ошибок"""
        if self._consecutive_errors >= self.MAX_CONSECUTIVE_ERRORS:
            self._disabled = True
            self._disabled_reason = "consecutive_errors"
            logger.critical("zenrows_consecutive_errors_circuit_breaker",
                           errors=self._consecutive_errors)
            return FetchResult(
                content=None,
                status_code=0,
                success=False,
                error=f"Too many consecutive errors ({self._consecutive_errors})",
                url="",
                attempts=0
            )
        return None
    
    def _check_circuit_breaker(self) -> Optional[FetchResult]:
        """Проверяет circuit breaker, возвращает FetchResult если отключен"""
        if self._disabled:
            logger.warning("zenrows_circuit_breaker_open", reason=self._disabled_reason)
            return FetchResult(
                content=None,
                status_code=0,
                success=False,
                error=f"ZenRows disabled: {self._disabled_reason}",
                url="",
                attempts=0
            )
        return None
    
    def _check_daily_limit(self) -> Optional[FetchResult]:
        """Проверяет дневной лимит"""
        self._reset_daily_counter_if_needed()
        
        if self._request_count >= self.daily_limit:
            self._disabled = True
            self._disabled_reason = "daily_limit_exceeded"
            logger.error("zenrows_daily_limit_exceeded", 
                        limit=self.daily_limit, 
                        count=self._request_count)
            return FetchResult(
                content=None,
                status_code=0,
                success=False,
                error=f"Daily limit exceeded ({self.daily_limit})",
                url="",
                attempts=0
            )
        return None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session
    
    async def fetch(
        self,
        url: str,
        js_render: Optional[bool] = None,
        premium_proxy: bool = False,
        antibot: Optional[bool] = None
    ) -> FetchResult:
        """Асинхронно получает контент через ZenRows с retry и circuit breaker"""
        
        # Check circuit breaker first
        breaker_result = self._check_circuit_breaker()
        if breaker_result:
            breaker_result.url = url
            return breaker_result
        
        # Check consecutive errors
        errors_result = self._check_consecutive_errors()
        if errors_result:
            errors_result.url = url
            return errors_result
        
        # Check daily limit
        limit_result = self._check_daily_limit()
        if limit_result:
            limit_result.url = url
            return limit_result
        
        # Check if domain is blocked
        if self._is_domain_blocked(url):
            logger.warning("zenrows_domain_blocked_skip", url=url, domain=self._extract_domain(url))
            return FetchResult(
                content=None,
                status_code=0,
                success=False,
                error=f"Domain blocked due to repeated failures",
                url=url,
                attempts=0
            )
        
        # Use instance defaults if not specified
        use_js_render = js_render if js_render is not None else self.js_render
        use_antibot = antibot if antibot is not None else self.antibot
        
        params = {
            'apikey': self.api_key,
            'url': url,
        }
        
        if use_js_render:
            params['js_render'] = 'true'
        if premium_proxy:
            params['premium_proxy'] = 'true'
        if use_antibot:
            params['antibot'] = 'true'
        
        last_error: Optional[str] = None
        delay = self.DEFAULT_RETRY_DELAY
        
        for attempt in range(self.max_retries):
            # Increment counter for each actual request
            self._request_count += 1
            
            try:
                session = await self._get_session()
                async with session.get(self.BASE_URL, params=params) as response:
                    content = await response.text()
                    success = response.status == 200
                    
                    # Circuit Breaker: 402 Payment Required - STOP immediately
                    if response.status == 402:
                        self._disabled = True
                        self._disabled_reason = "payment_required_402"
                        logger.critical("zenrows_payment_required_circuit_breaker_triggered", 
                                       url=url, 
                                       daily_count=self._request_count)
                        return FetchResult(
                            content=None,
                            status_code=402,
                            success=False,
                            error="ZenRows Payment Required (402) - Circuit breaker triggered",
                            url=url,
                            attempts=attempt + 1
                        )
                    
                    # Circuit Breaker: 429 Rate Limit - don't retry
                    if response.status == 429:
                        logger.error("zenrows_rate_limit", url=url, daily_count=self._request_count)
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
                        logger.info("zenrows_success", url=url, attempts=attempt + 1, daily_count=self._request_count)
                        # Reset consecutive errors and domain failures on success
                        self._consecutive_errors = 0
                        self._record_domain_success(url)
                    else:
                        logger.warning("zenrows_bad_status", url=url, status_code=response.status)
                        # Track failures
                        self._consecutive_errors += 1
                        self._record_domain_failure(url)
                    
                    return FetchResult(
                        content=content if success else None,
                        status_code=response.status,
                        success=success,
                        url=url,
                        attempts=attempt + 1
                    )
                    
            except RETRYABLE_EXCEPTIONS as e:
                last_error = str(e)
                self._consecutive_errors += 1
                self._record_domain_failure(url)
                
                if attempt < self.max_retries - 1:
                    logger.warning("zenrows_retry_error", url=url, error=str(e), attempt=attempt + 1)
                    await asyncio.sleep(delay)
                    delay *= 2
                else:
                    logger.error("zenrows_failed", url=url, error=str(e), attempts=attempt + 1)
                    
            except Exception as e:
                logger.error("zenrows_error", url=url, error=str(e), exc_info=True)
                self._consecutive_errors += 1
                self._record_domain_failure(url)
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
    Поддерживает стратегии: direct_first (сначала прямой запрос), zenrows_only
    Автоматически пропускает ZenRows для статических URL
    """
    
    def __init__(
        self,
        zenrows_api_key: Optional[str] = None,
        timeout: int = 30,
        user_agent: str = Config.USER_AGENT,
        max_retries: int = 3,
        strategy: str = "direct_first",
        skip_static: bool = True,
        zenrows_daily_limit: int = 500,
        zenrows_js_render: bool = True,
        zenrows_antibot: bool = False
    ):
        self._direct = AsyncFetcher(
            timeout=timeout, 
            user_agent=user_agent,
            max_retries=max_retries
        )
        self._zenrows: Optional[AsyncZenRowsFetcher] = None
        self._strategy = strategy
        self._skip_static = skip_static
        
        if zenrows_api_key:
            self._zenrows = AsyncZenRowsFetcher(
                zenrows_api_key, 
                timeout=60,
                max_retries=1,  # Минимум retry для ZenRows - экономим
                daily_limit=zenrows_daily_limit,
                js_render=zenrows_js_render,
                antibot=zenrows_antibot
            )
            logger.info("zenrows_client_initialized", 
                       strategy=strategy, 
                       skip_static=skip_static,
                       daily_limit=zenrows_daily_limit,
                       js_render=zenrows_js_render,
                       antibot=zenrows_antibot)
    
    def _is_static_url(self, url: str) -> bool:
        """Проверяет, является ли URL статическим (не требует ZenRows)"""
        return bool(STATIC_URL_REGEX.search(url))
    
    def _should_use_zenrows(self, url: str) -> bool:
        """Определяет, нужно ли использовать ZenRows для URL"""
        if not self._zenrows:
            return False
        
        if self._skip_static and self._is_static_url(url):
            logger.debug("skipping_zenrows_static_url", url=url)
            return False
        
        return True
    
    async def fetch(self, url: str) -> Optional[str]:
        """
        Получает контент URL с учётом стратегии
        
        Стратегии:
        - direct_first: сначала прямой запрос, ZenRows как fallback
        - zenrows_only: только ZenRows (если настроен)
        
        Args:
            url: URL для получения
            
        Returns:
            Контент или None
        """
        use_zenrows = self._should_use_zenrows(url)
        
        # Strategy: direct_first - try direct request first
        if self._strategy == "direct_first":
            logger.debug("fetching_direct_first", url=url)
            result = await self._direct.fetch(url)
            
            if result.success:
                logger.info("direct_fetch_success", url=url)
                return result.content
            
            # Direct failed, try ZenRows as fallback
            if use_zenrows:
                logger.info("direct_failed_trying_zenrows", 
                           url=url, 
                           direct_status=result.status_code,
                           direct_error=result.error)
                zenrows_result = await self._zenrows.fetch(url)
                if zenrows_result.success:
                    return zenrows_result.content
                logger.warning("zenrows_fallback_failed", url=url, error=zenrows_result.error)
            
            return None
        
        # Strategy: zenrows_only
        if use_zenrows:
            logger.info("fetching_via_zenrows", url=url)
            result = await self._zenrows.fetch(url)
            return result.content if result.success else None
        else:
            # ZenRows not available or skipped, use direct
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
    
    def get_zenrows_stats(self) -> dict:
        """Возвращает статистику использования ZenRows"""
        if not self._zenrows:
            return {"enabled": False}
        
        return {
            "enabled": True,
            "disabled": self._zenrows._disabled,
            "disabled_reason": self._zenrows._disabled_reason,
            "daily_count": self._zenrows._request_count,
            "daily_limit": self._zenrows.daily_limit,
            "date": str(self._zenrows._request_date),
            "consecutive_errors": self._zenrows._consecutive_errors,
            "blocked_domains": list(self._zenrows._blocked_domains),
            "domain_failures": dict(self._zenrows._domain_failures)
        }
    
    async def close(self) -> None:
        """Закрывает все соединения"""
        await self._direct.close()
        if self._zenrows:
            await self._zenrows.close()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
