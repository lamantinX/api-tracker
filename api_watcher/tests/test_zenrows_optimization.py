import pytest
from unittest.mock import Mock, AsyncMock, patch
import aiohttp
from api_watcher.utils.async_fetcher import AsyncZenRowsFetcher

@pytest.mark.asyncio
class TestZenRowsOptimization:
    
    async def test_circuit_breaker_payment_required(self):
        """Test that 402 Payment Required aborts immediately"""
        fetcher = AsyncZenRowsFetcher("test_key")
        
        # Mock session and response
        mock_response = AsyncMock()
        mock_response.status = 402
        mock_response.text.return_value = "Payment Required"
        
        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__.return_value = mock_response
        
        with patch.object(fetcher, '_get_session', new_callable=AsyncMock) as mock_get_session:
            mock_get_session.return_value = mock_session
            
            with pytest.raises(Exception) as excinfo:
                await fetcher.fetch("http://example.com")
            
            assert "Payment Required" in str(excinfo.value)
            # Should only call once
            assert mock_session.get.call_count == 1

    async def test_circuit_breaker_rate_limit(self):
        """Test that 429 Rate Limit stops retrying immediately"""
        fetcher = AsyncZenRowsFetcher("test_key")
        
        mock_response = AsyncMock()
        mock_response.status = 429
        mock_response.text.return_value = "Rate Limit Exceeded"
        
        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__.return_value = mock_response
        
        with patch.object(fetcher, '_get_session', new_callable=AsyncMock) as mock_get_session:
            mock_get_session.return_value = mock_session
            
            result = await fetcher.fetch("http://example.com")
            
            assert result.success is False
            assert result.status_code == 429
            # Should only call once, not retry aggressively
            assert mock_session.get.call_count == 1

    async def test_reduced_retries(self):
        """Test that 500 errors only retry once (max_retries=1)"""
        fetcher = AsyncZenRowsFetcher("test_key")
        
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text.return_value = "Server Error"
        
        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__.return_value = mock_response
        
        with patch.object(fetcher, '_get_session', new_callable=AsyncMock) as mock_get_session:
            mock_get_session.return_value = mock_session
            
            result = await fetcher.fetch("http://example.com")
            
            assert result.success is False
            assert result.status_code == 500
            # max_retries is 1, so it runs the loop once (0 to 0)
            # Wait, range(self.max_retries) where max_retries=1 is [0], so 1 iteration.
            assert mock_session.get.call_count == 1

    async def test_no_premium_proxy_fallback(self):
        """Test that fetch_with_fallback does NOT use premium proxy"""
        fetcher = AsyncZenRowsFetcher("test_key")
        
        # Mock fetch to always fail
        mock_result_fail = Mock(success=False, content=None)
        
        with patch.object(fetcher, 'fetch', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_result_fail
            
            await fetcher.fetch_with_fallback("http://example.com")
            
            # Should call twice: 
            # 1. Standard (js_render=True, premium_proxy=False)
            # 2. No-JS (js_render=False, premium_proxy=False)
            assert mock_fetch.call_count == 2
            
            # Verify arguments of calls
            calls = mock_fetch.call_args_list
            
            # Call 1
            args1, kwargs1 = calls[0]
            assert kwargs1.get('premium_proxy') is False
            assert kwargs1.get('js_render') is True
            
            # Call 2
            args2, kwargs2 = calls[1]
            assert kwargs2.get('premium_proxy') is False
            assert kwargs2.get('js_render') is False
            
            # Ensure NO call had premium_proxy=True
            for call in calls:
                assert call.kwargs.get('premium_proxy') is False

