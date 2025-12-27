"""
API Watcher - Refactored version
Refactoring: Repository pattern, Notifier adapters, Async fetch, SRP compliance
"""

import json
import asyncio
import os
from typing import Dict, List, Optional
from datetime import datetime

from api_watcher.config import Config
from api_watcher.storage.repository import SQLAlchemySnapshotRepository, SnapshotRepository
from api_watcher.utils.async_fetcher import ContentFetcher
from api_watcher.utils.gemini_analyzer import GeminiAnalyzer
from api_watcher.utils.openrouter_analyzer import OpenRouterAnalyzer
from api_watcher.utils.smart_comparator import SmartComparator
from api_watcher.notifier.base import NotifierManager
from api_watcher.notifier.adapters import (
    SlackAdapter, 
    WebhookAdapter, 
    TelegramAdapter,
    ConsoleAdapter
)
from api_watcher.services.content_processor import ContentProcessor
from api_watcher.services.change_detector import ChangeDetector
from api_watcher.logging_config import setup_from_config, get_logger

# Initialize structured logging
setup_from_config(Config)
logger = get_logger(__name__)

def _acquire_lockfile(lock_path: str) -> int:
    """
    Простой lockfile, чтобы не запускать несколько инстансов watcher одновременно.
    Возвращает fd (держим открытым до конца процесса).
    """
    flags = os.O_CREAT | os.O_EXCL | os.O_RDWR
    fd = os.open(lock_path, flags)
    try:
        os.write(fd, str(os.getpid()).encode("utf-8"))
    except Exception:
        pass
    return fd

def _release_lockfile(fd: Optional[int], lock_path: str) -> None:
    try:
        if fd is not None:
            os.close(fd)
    finally:
        try:
            os.remove(lock_path)
        except Exception:
            pass


class APIWatcher:
    """
    Orchestrator for API monitoring.
    Delegates responsibilities to ContentProcessor and ChangeDetector.
    """
    
    def __init__(
        self,
        repository: Optional[SnapshotRepository] = None,
        fetcher: Optional[ContentFetcher] = None,
        notifier_manager: Optional[NotifierManager] = None
    ):
        self.config = Config
        
        # Repository (DI or default)
        self.repository = repository or SQLAlchemySnapshotRepository(
            self.config.DATABASE_URL
        )
        
        # Async Fetcher (DI or default)
        self.fetcher = fetcher or ContentFetcher(
            zenrows_api_key=self.config.ZENROWS_API_KEY,
            timeout=self.config.REQUEST_TIMEOUT,
            user_agent=self.config.USER_AGENT
        )
        
        # Notifier Manager (DI or default)
        self.notifiers = notifier_manager or self._create_notifier_manager()
        
        # AI Analyzer
        self.ai_analyzer = self._create_ai_analyzer()
        
        # Services
        self.content_processor = ContentProcessor(self.notifiers)
        self.change_detector = ChangeDetector(
            repository=self.repository,
            notifiers=self.notifiers,
            ai_analyzer=self.ai_analyzer
        )
        
        # Comparator (still needed for initial snapshot hash calculation in some cases, 
        # but mostly handled by ChangeDetector. Keeping it for now if needed by legacy methods or direct usage)
        self.comparator = SmartComparator()
        
        # Request cache for deduplication within a single cycle
        self._request_cache: Dict[str, asyncio.Task] = {}
    
    def _create_notifier_manager(self) -> NotifierManager:
        """Creates notifier manager based on config"""
        manager = NotifierManager()
        
        if self.config.is_slack_configured():
            manager.register(SlackAdapter(
                self.config.SLACK_BOT_TOKEN,
                self.config.SLACK_CHANNEL
            ))
            logger.info("✅ Slack adapter registered")
        
        if self.config.is_webhook_configured():
            adapter = WebhookAdapter(self.config.WEBHOOK_URL)
            if adapter.test_connection():
                manager.register(adapter)
                logger.info("✅ Webhook adapter registered")
            else:
                logger.warning("⚠️ Webhook unavailable")
        
        if self.config.is_telegram_configured():
            manager.register(TelegramAdapter(
                self.config.TELEGRAM_BOT_TOKEN,
                self.config.TELEGRAM_CHAT_ID
            ))
            logger.info("✅ Telegram adapter registered")
        
        # Console always on
        manager.register(ConsoleAdapter())
        
        return manager
    
    def _create_ai_analyzer(self):
        """Creates AI analyzer (OpenRouter priority, Gemini fallback)"""
        if self.config.is_openrouter_configured():
            logger.info(f"✅ OpenRouter AI (model: {self.config.OPENROUTER_MODEL})")
            return OpenRouterAnalyzer(
                self.config.OPENROUTER_API_KEY,
                self.config.OPENROUTER_MODEL,
                self.config.OPENROUTER_SITE_URL,
                self.config.OPENROUTER_APP_NAME
            )
        elif self.config.is_gemini_configured():
            logger.info("✅ Gemini AI (fallback)")
            return GeminiAnalyzer(
                self.config.GEMINI_API_KEY,
                self.config.GEMINI_MODEL
            )
        return None
    
    async def fetch_content(self, url: str) -> Optional[str]:
        """
        Async fetch content with deduplication.
        If multiple URLs point to the same page (e.g. different anchors),
        we only fetch it once per cycle.
        """
        # Strip anchor for deduplication (e.g. http://site.com#foo -> http://site.com)
        base_url = url.split('#')[0]
        
        # Check cache
        if base_url in self._request_cache:
            logger.info(f"🔄 Using cached request for {base_url}")
            try:
                return await self._request_cache[base_url]
            except Exception as e:
                logger.error(f"❌ Error awaiting cached task for {base_url}: {e}")
                return None
            
        # Create new fetch task
        # We use base_url to avoid sending anchors to the provider
        task = asyncio.create_task(self.fetcher.fetch(base_url))
        self._request_cache[base_url] = task
        
        try:
            return await task
        except Exception as e:
            logger.error(f"❌ Error fetching {base_url}: {e}")
            # Keep the failed task in cache so other requests for the same URL 
            # (e.g. different anchors) don't trigger a retry in this cycle.
            # They will receive the same exception/None result.
            return None
    
    async def process_url(
        self,
        url: str,
        api_name: Optional[str] = None,
        method_name: Optional[str] = None
    ) -> Dict:
        """Async process URL"""
        logger.info(f"\n{'='*60}")
        logger.info(f"🔍 Processing: {api_name or url}")
        logger.info(f"{'='*60}")
        
        # 1. Fetch content
        new_html = await self.fetch_content(url)
        if not new_html:
            logger.error(f"❌ Failed to fetch content for {url}")
            return {'url': url, 'has_changes': False, 'error': 'Failed to fetch'}
        
        # 2. Validate and fallback
        if not self.content_processor.is_valid_response(new_html, url):
            logger.warning(f"⚠️ Invalid response from {url}")
            
            new_url = await self.content_processor.try_find_new_documentation(url, api_name, method_name)
            
            if new_url:
                new_html_from_new_url = await self.fetch_content(new_url)
                
                if new_html_from_new_url and self.content_processor.is_valid_response(new_html_from_new_url, new_url):
                    logger.info(f"✅ Content from new URL: {new_url}")
                    url = new_url
                    new_html = new_html_from_new_url
                else:
                    return {'url': url, 'has_changes': False, 'error': 'New URL also failed'}
            else:
                return {'url': url, 'has_changes': False, 'error': 'No alternative found'}
        
        # 3. Detect content type
        content_type = self.content_processor.detect_content_type(url, new_html)
        logger.info(f"📄 Content type: {content_type}")
        
        # 4. Get latest snapshot
        old_snapshot = self.repository.get_latest(url)
        
        if not old_snapshot:
            logger.info(f"📝 First snapshot for {url}")
            text_content = self.comparator.html_to_text(new_html) if content_type == 'html' else new_html
            content_hash = self.comparator.calculate_hash(new_html)
            
            self.repository.save(
                url=url,
                raw_html=new_html,
                text_content=text_content,
                api_name=api_name,
                method_name=method_name,
                content_type=content_type,
                content_hash=content_hash,
                has_changes=False
            )
            
            return {'url': url, 'has_changes': False, 'is_first_snapshot': True}
        
        # 5. Detect changes
        return self.change_detector.detect_changes(
            old_snapshot, new_html, content_type, url, api_name, method_name
        )
    
    async def process_urls_file(self, urls_file: str) -> List[Dict]:
        """Async process URLs from file"""
        logger.info(f"📂 Loading URLs from {urls_file}")
        
        # Clear request cache for new cycle
        self._request_cache.clear()
        
        try:
            with open(urls_file, 'r', encoding='utf-8') as f:
                urls_data = json.load(f)
        except Exception as e:
            logger.error(f"❌ Error reading file {urls_file}: {e}")
            return []
        
        results = []
        for item in urls_data:
            url = item.get('url')
            api_name = item.get('api_name')
            method_name = item.get('method_name')
            
            if not url:
                continue
            
            result = await self.process_url(url, api_name, method_name)
            results.append(result)
        
        return results
    
    async def process_urls_parallel(
        self, 
        urls_file: str, 
        max_concurrent: int = 10,
        delay_between_requests: float = 0.2
    ) -> List[Dict]:
        """
        Parallel URL processing with rate limiting
        
        Args:
            urls_file: Path to JSON file with URLs
            max_concurrent: Maximum concurrent requests (default: 3 to avoid rate limiting)
            delay_between_requests: Delay in seconds between starting new requests
        """
        logger.info(f"📂 Loading URLs from {urls_file} (parallel, max={max_concurrent})")
        
        # Clear request cache for new cycle
        self._request_cache.clear()
        
        try:
            with open(urls_file, 'r', encoding='utf-8') as f:
                urls_data = json.load(f)
        except Exception as e:
            logger.error(f"❌ Error reading file {urls_file}: {e}")
            return []
        
        semaphore = asyncio.Semaphore(max_concurrent)
        results = []
        
        async def process_with_semaphore(item, index):
            # Add delay to avoid rate limiting
            if delay_between_requests > 0 and index > 0:
                await asyncio.sleep(delay_between_requests * (index % max_concurrent))
            
            async with semaphore:
                url = item.get('url')
                if not url:
                    return None
                try:
                    return await self.process_url(
                        url,
                        item.get('api_name'),
                        item.get('method_name')
                    )
                except Exception as e:
                    logger.error(f"❌ Error processing {url}: {e}")
                    return {'url': url, 'has_changes': False, 'error': str(e)}
        
        tasks = [process_with_semaphore(item, i) for i, item in enumerate(urls_data)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out None and exceptions
        return [r for r in results if r is not None and not isinstance(r, Exception)]
    
    def send_weekly_digest(self):
        """Sends weekly digest"""
        logger.info("📊 Generating weekly digest...")
        
        snapshots = self.repository.get_with_changes(days=self.config.CHECK_INTERVAL_DAYS)
        
        changes = []
        for snapshot in snapshots:
            changes.append({
                'api_name': snapshot.api_name,
                'method_name': snapshot.method_name,
                'url': snapshot.url,
                'summary': snapshot.ai_summary or 'Changes detected',
                'created_at': snapshot.created_at.isoformat() if snapshot.created_at else None
            })
        
        self.notifiers.send_digest(changes)
    
    async def cleanup(self):
        """Cleanup resources"""
        await self.fetcher.close()
        self.repository.close()


async def main():
    """Main async function"""
    watcher = APIWatcher()
    lock_fd: Optional[int] = None
    lock_path = os.getenv("API_WATCHER_LOCKFILE", os.path.join(watcher.config.SNAPSHOTS_DIR, ".api_watcher.lock"))
    
    try:
        if os.getenv("API_WATCHER_DISABLE_LOCK", "false").lower() != "true":
            os.makedirs(os.path.dirname(lock_path), exist_ok=True)
            try:
                lock_fd = _acquire_lockfile(lock_path)
                logger.info("lock_acquired", lockfile=lock_path)
            except FileExistsError:
                logger.critical("another_instance_running", lockfile=lock_path)
                return

        # Guard: слишком частый polling в daemon режиме может сжечь ZenRows
        sleep_seconds = watcher.config.CHECK_INTERVAL_SECONDS
        if (
            watcher.config.DAEMON_MODE
            and watcher.config.is_zenrows_configured()
            and not watcher.config.ALLOW_FAST_POLL
            and sleep_seconds < watcher.config.MIN_CHECK_INTERVAL_SECONDS
        ):
            logger.critical(
                "check_interval_too_low_clamped",
                configured=sleep_seconds,
                clamped_to=watcher.config.MIN_CHECK_INTERVAL_SECONDS
            )
            sleep_seconds = watcher.config.MIN_CHECK_INTERVAL_SECONDS

        while True:
            # Process URLs parallel with rate limiting
            results = await watcher.process_urls_parallel(
                Config.URLS_FILE,
                max_concurrent=10,
                delay_between_requests=0.2
            )
            
            # Stats
            total = len(results)
            changed = sum(1 for r in results if r.get('has_changes'))
            
            logger.info(f"\n{'='*60}")
            logger.info(f"📊 STATISTICS")
            logger.info(f"{'='*60}")
            logger.info(f"Total checked: {total}")
            logger.info(f"Changes detected: {changed}")
            logger.info(f"{'='*60}\n")
            
            if not Config.DAEMON_MODE:
                break
            
            logger.info(f"Sleeping for {sleep_seconds} seconds...")
            await asyncio.sleep(sleep_seconds)
            
    finally:
        await watcher.cleanup()
        _release_lockfile(lock_fd, lock_path)


if __name__ == '__main__':
    asyncio.run(main())
