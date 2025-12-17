"""
Async content fetcher using aiohttp
Асинхронное получение контента с retry логикой
"""

import asyncio
from typing import Optional, List
from dataclasses import dataclass

import aiohttp

from api_watcher.config import Config
from api_watcher.logging_config import get_logger
from api_watcher.utils.usage_tracker import UsageTracker

logger = get_logger(__name__)

async def _read_text_limited(response: aiohttp.ClientResponse, max_bytes: int) -> str:
    """
    Читает тело ответа с ограничением по размеру, чтобы не тащить огромные страницы в память.
    Декодирует с учётом charset, заменяя ошибки.
    """
    # Быстрый отказ по Content-Length, если сервер его честно прислал
    content_length = response.headers.get("Content-Length")
    if content_length:
        # Ловим только ошибки парсинга int(), а превышение лимита должно прерывать чтение.
        try:
            content_length_int = int(content_length)
        except ValueError:
            # если Content-Length нечисловой — игнорируем и читаем потоково
            content_length_int = None

        if content_length_int is not None and content_length_int > max_bytes:
            raise ValueError(f"Response too large: {content_length_int} bytes > {max_bytes}")

    collected = bytearray()
    async for chunk in response.content.iter_chunked(64 * 1024):
        if not chunk:
            continue
        collected.extend(chunk)
        if len(collected) > max_bytes:
            raise ValueError(f"Response too large: read>{max_bytes} bytes")

    charset = response.charset or "utf-8"
    return collected.decode(charset, errors="replace")


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
                    try:
                        max_bytes = max(1, int(getattr(Config, "MAX_RESPONSE_BYTES", 2 * 1024 * 1024)))
                        content = await _read_text_limited(response, max_bytes=max_bytes)
                    except ValueError as e:
                        # Не ретраим: это "логическая" ошибка/защита от чрезмерных ответов
                        logger.warning("response_too_large", url=url, error=str(e))
                        return FetchResult(
                            content=None,
                            status_code=response.status,
                            success=False,
                            error=str(e),
                            url=url,
                            attempts=attempts
                        )
                    
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
        max_retries: int = DEFAULT_MAX_RETRIES,
        usage_tracker: Optional[UsageTracker] = None,
        daily_request_limit: Optional[int] = None
    ):
        self.api_key = api_key
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self._session: Optional[aiohttp.ClientSession] = None
        self.usage_tracker = usage_tracker or UsageTracker()
        self.daily_request_limit = (
            int(daily_request_limit)
            if daily_request_limit is not None
            else int(getattr(Config, "ZENROWS_DAILY_REQUEST_LIMIT", 2000))
        )
        self._disabled: bool = False
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session
    
    async def fetch(
        self,
        url: str,
        js_render: bool = True,
        premium_proxy: bool = False,
        antibot: bool = False,
        skip_counter: bool = False
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
                if self._disabled:
                    return FetchResult(
                        content=None,
                        status_code=0,
                        success=False,
                        error="ZenRows disabled (circuit breaker)",
                        url=url,
                        attempts=attempt + 1
                    )
                
                # Атомарная проверка лимита и резервирование слота
                # Это предотвращает race condition при параллельных запросах
                if skip_counter:
                    # Для fallback попытки только проверяем лимит (не инкрементируем)
                    # Счетчик уже был увеличен в первой попытке
                    if not await self.usage_tracker.can_use("zenrows", self.daily_request_limit):
                        usage = await self.usage_tracker.get_usage("zenrows")
                        logger.error(
                            "zenrows_daily_limit_exceeded_fallback",
                            url=url,
                            limit=self.daily_request_limit,
                            usage=usage
                        )
                        return FetchResult(
                            content=None,
                            status_code=0,
                            success=False,
                            error="ZenRows daily limit exceeded",
                            url=url,
                            attempts=attempt + 1
                        )
                else:
                    # Для обычной попытки атомарно проверяем и резервируем слот
                    # ИСПРАВЛЕНИЕ УЯЗВИМОСТИ #6: Инкремент происходит ТОЛЬКО один раз 
                    # в начале цикла retry (attempt == 0), а не на каждой итерации.
                    # Это предотвращает множественный инкремент при retry.
                    if attempt == 0:
                        if not await self.usage_tracker.try_increment("zenrows", self.daily_request_limit, 1):
                            usage = await self.usage_tracker.get_usage("zenrows")
                            logger.error(
                                "zenrows_daily_limit_exceeded",
                                url=url,
                                limit=self.daily_request_limit,
                                usage=usage
                            )
                            return FetchResult(
                                content=None,
                                status_code=0,
                                success=False,
                                error="ZenRows daily limit exceeded",
                                url=url,
                                attempts=attempt + 1
                            )
                    # При retry (attempt > 0) слот уже зарезервирован в первой попытке,
                    # поэтому мы НЕ инкрементируем счетчик повторно.
                    # Это исправляет проблему множественного инкремента при retry.

                # Выполняем запрос (счетчик уже увеличен в try_increment() если skip_counter=False и attempt == 0)
                # Примечание: Если запрос падает с сетевой ошибкой ДО выполнения HTTP запроса,
                # счетчик уже увеличен, но это правильное поведение - мы резервируем слот для попытки.
                async with session.get(self.BASE_URL, params=params) as response:
                    try:
                        max_bytes = max(1, int(getattr(Config, "MAX_RESPONSE_BYTES", 2 * 1024 * 1024)))
                        content = await _read_text_limited(response, max_bytes=max_bytes)
                    except ValueError as e:
                        logger.warning("zenrows_response_too_large", url=url, error=str(e))
                        return FetchResult(
                            content=None,
                            status_code=response.status,
                            success=False,
                            error=str(e),
                            url=url,
                            attempts=attempt + 1
                        )
                    success = response.status == 200
                    
                    # Circuit Breaker for Critical Errors
                    if response.status == 402:
                        # На практике 402 может означать "кончился баланс" — не спамим дальше платными запросами
                        logger.critical("zenrows_payment_required_disabling", url=url)
                        self._disabled = True
                        return FetchResult(
                            content=None,
                            status_code=402,
                            success=False,
                            error="ZenRows Payment Required (402) - disabled",
                            url=url,
                            attempts=attempt + 1
                        )
                    
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
                    # ИСПРАВЛЕНИЕ УЯЗВИМОСТИ #6: При retry мы НЕ инкрементируем счетчик повторно,
                    # так как слот уже зарезервирован в начале цикла (attempt == 0) через try_increment().
                    # Это предотвращает множественный инкремент при retry - счетчик увеличивается только один раз
                    # для всех попыток retry в рамках одного запроса.
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
                # ИСПРАВЛЕНИЕ УЯЗВИМОСТИ #6: При сетевых ошибках (RETRYABLE_EXCEPTIONS) 
                # счетчик уже был увеличен при attempt == 0, но мы НЕ инкрементируем его повторно при retry.
                # Это правильное поведение - мы резервируем один слот для всех попыток retry.
                last_error = str(e)
                if attempt < self.max_retries - 1:
                    logger.warning("zenrows_retry_error", url=url, error=str(e), attempt=attempt + 1)
                    await asyncio.sleep(delay)
                    delay *= 2
                    # Продолжаем цикл - счетчик НЕ инкрементируется повторно
                else:
                    logger.error("zenrows_failed", url=url, error=str(e), attempts=attempt + 1)
                    # Все попытки исчерпаны - счетчик был увеличен только один раз при attempt == 0
                    
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
        """
        Получает контент с fallback стратегией.
        Вторая попытка НЕ инкрементирует счетчик, чтобы избежать двойного подсчета.
        """
        # Попытка 1: базовые настройки (инкрементирует счетчик)
        result = await self.fetch(
            url,
            js_render=bool(getattr(Config, "ZENROWS_JS_RENDER", True)),
            premium_proxy=False,
            antibot=bool(getattr(Config, "ZENROWS_ANTIBOT", False)),
            skip_counter=False
        )
        if result.success:
            return result.content
        
        logger.warning("zenrows_retry_no_js", url=url)
        
        # Попытка 2: без JS (НЕ инкрементирует счетчик - это fallback в рамках одного запроса)
        result = await self.fetch(
            url,
            js_render=False,
            premium_proxy=False,
            antibot=bool(getattr(Config, "ZENROWS_ANTIBOT", False)),
            skip_counter=True  # Пропускаем инкремент для fallback попытки
        )
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
        self._usage_tracker = UsageTracker()
        
        if zenrows_api_key:
            self._zenrows = AsyncZenRowsFetcher(
                zenrows_api_key, 
                timeout=60,
                max_retries=max_retries,
                usage_tracker=self._usage_tracker,
                daily_request_limit=getattr(Config, "ZENROWS_DAILY_REQUEST_LIMIT", 2000)
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
        # Стратегия по умолчанию: direct_first, чтобы не жечь ZenRows на JSON/YAML/простых доменах.
        strategy = getattr(Config, "ZENROWS_STRATEGY", "direct_first")

        def _looks_static(u: str) -> bool:
            ul = u.lower()
            if any(ul.endswith(ext) for ext in (".json", ".yaml", ".yml")):
                return True
            # raw github и прочие статики
            if "raw.githubusercontent.com" in ul:
                return True
            return False

        skip_static = bool(getattr(Config, "ZENROWS_SKIP_STATIC", True))
        should_skip_zenrows = skip_static and _looks_static(url)

        # 1) direct_first: пробуем прямой запрос
        if strategy != "zenrows_first" or should_skip_zenrows or not self._zenrows:
            logger.debug("fetching_direct", url=url)
            direct_result = await self._direct.fetch(url)
            if direct_result.success and direct_result.content:
                return direct_result.content
            # если ZenRows не настроен или нельзя — сдаёмся
            if not self._zenrows or should_skip_zenrows:
                return None
            # иначе пробуем ZenRows как fallback

        # 2) ZenRows (если доступен и не запрещён)
        if self._zenrows:
            # Используем атомарную операцию для проверки лимита
            limit = int(getattr(Config, "ZENROWS_DAILY_REQUEST_LIMIT", 2000))
            if not await self._usage_tracker.can_use("zenrows", limit):
                usage = await self._usage_tracker.get_usage("zenrows")
                logger.error(
                    "zenrows_disabled_due_to_daily_limit",
                    url=url,
                    limit=limit,
                    usage=usage
                )
                return None

            logger.info("fetching_via_zenrows", url=url)
            return await self._zenrows.fetch_with_fallback(url)

        return None
    
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
