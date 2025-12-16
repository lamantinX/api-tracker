import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from api_watcher.watcher import APIWatcher
from api_watcher.utils.async_fetcher import ContentFetcher

@pytest.mark.asyncio
async def test_fetch_deduplication():
    # Setup
    mock_fetcher = Mock(spec=ContentFetcher)
    # Simulate a slow fetch to ensure concurrent requests hit the cache
    async def delayed_fetch(url):
        await asyncio.sleep(0.1)
        return f"content for {url}"
    
    mock_fetcher.fetch = AsyncMock(side_effect=delayed_fetch)
    
    with patch('api_watcher.watcher.Config') as mock_config:
        mock_config.DATABASE_URL = 'sqlite:///:memory:'
        mock_config.is_openrouter_configured.return_value = False
        mock_config.is_gemini_configured.return_value = False
        
        watcher = APIWatcher(fetcher=mock_fetcher)
        
        # Test URLs - same base, different anchors
        url_base = "http://example.com/api"
        urls = [
            f"{url_base}#section1",
            f"{url_base}#section2",
            f"{url_base}#section3",
            f"{url_base}"
        ]
        
        # Execute fetches concurrently
        tasks = [watcher.fetch_content(url) for url in urls]
        results = await asyncio.gather(*tasks)
        
        # Verify results
        assert len(results) == 4
        assert all(r == f"content for {url_base}" for r in results)
        
        # Verify fetcher was called ONLY ONCE with the base URL
        mock_fetcher.fetch.assert_called_once_with(url_base)

@pytest.mark.asyncio
async def test_fetch_deduplication_different_urls():
    # Setup
    mock_fetcher = Mock(spec=ContentFetcher)
    mock_fetcher.fetch = AsyncMock(return_value="content")
    
    with patch('api_watcher.watcher.Config') as mock_config:
        watcher = APIWatcher(fetcher=mock_fetcher)
        
        # Different URLs
        url1 = "http://example.com/page1"
        url2 = "http://example.com/page2"
        
        await asyncio.gather(
            watcher.fetch_content(url1),
            watcher.fetch_content(url2)
        )
        
        # Should be called twice
        assert mock_fetcher.fetch.call_count == 2
        mock_fetcher.fetch.assert_any_call(url1)
        mock_fetcher.fetch.assert_any_call(url2)
