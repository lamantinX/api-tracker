import pytest
from unittest.mock import Mock, AsyncMock, patch
import aiohttp
from api_watcher.utils.async_fetcher import AsyncZenRowsFetcher

@pytest.mark.asyncio
class TestZenRowsOptimization:
    
    async def test_circuit_breaker_payment_required(self):
        """Test that 402 Payment Required triggers circuit breaker"""
        fetcher = AsyncZenRowsFetcher("test_key")
        
        # Mock session and response
        mock_response = AsyncMock()
        mock_response.status = 402
        mock_response.text.return_value = "Payment Required"
        
        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__.return_value = mock_response
        
        with patch.object(fetcher, '_get_session', new_callable=AsyncMock) as mock_get_session:
            mock_get_session.return_value = mock_session
            
            result = await fetcher.fetch("http://example.com")
            
            # Should return error result, not raise
            assert result.success is False
            assert result.status_code == 402
            assert "Payment Required" in result.error
            
            # Circuit breaker should be triggered
            assert fetcher._disabled is True
            assert fetcher._disabled_reason == "payment_required_402"
            
            # Should only call once
            assert mock_session.get.call_count == 1
            
            # Subsequent calls should be blocked by circuit breaker
            result2 = await fetcher.fetch("http://example2.com")
            assert result2.success is False
            assert "disabled" in result2.error.lower()
            # No additional API calls
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
            # max_retries is 1, so it runs the loop once
            assert mock_session.get.call_count == 1

    async def test_daily_limit(self):
        """Test that daily limit blocks requests"""
        fetcher = AsyncZenRowsFetcher("test_key", daily_limit=2)
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text.return_value = "OK"
        
        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__.return_value = mock_response
        
        with patch.object(fetcher, '_get_session', new_callable=AsyncMock) as mock_get_session:
            mock_get_session.return_value = mock_session
            
            # First 2 requests should succeed
            result1 = await fetcher.fetch("http://example1.com")
            result2 = await fetcher.fetch("http://example2.com")
            
            assert result1.success is True
            assert result2.success is True
            assert mock_session.get.call_count == 2
            
            # Third request should be blocked
            result3 = await fetcher.fetch("http://example3.com")
            assert result3.success is False
            assert "Daily limit exceeded" in result3.error
            # No additional API call
            assert mock_session.get.call_count == 2

    async def test_domain_blocking(self):
        """Test that domains are blocked after repeated failures"""
        fetcher = AsyncZenRowsFetcher("test_key", daily_limit=100)
        
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text.return_value = "Server Error"
        
        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__.return_value = mock_response
        
        with patch.object(fetcher, '_get_session', new_callable=AsyncMock) as mock_get_session:
            mock_get_session.return_value = mock_session
            
            # Make MAX_DOMAIN_FAILURES requests to same domain
            for i in range(AsyncZenRowsFetcher.MAX_DOMAIN_FAILURES):
                await fetcher.fetch("http://failing-domain.com/page")
            
            # Domain should now be blocked
            assert "failing-domain.com" in fetcher._blocked_domains
            
            # Next request to same domain should be blocked without API call
            call_count_before = mock_session.get.call_count
            result = await fetcher.fetch("http://failing-domain.com/other-page")
            
            assert result.success is False
            assert "blocked" in result.error.lower()
            assert mock_session.get.call_count == call_count_before  # No new calls

    async def test_consecutive_errors_circuit_breaker(self):
        """Test that too many consecutive errors triggers global circuit breaker"""
        fetcher = AsyncZenRowsFetcher("test_key", daily_limit=100)
        
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text.return_value = "Server Error"
        
        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__.return_value = mock_response
        
        with patch.object(fetcher, '_get_session', new_callable=AsyncMock) as mock_get_session:
            mock_get_session.return_value = mock_session
            
            # Make MAX_CONSECUTIVE_ERRORS requests (different domains to avoid domain blocking)
            for i in range(AsyncZenRowsFetcher.MAX_CONSECUTIVE_ERRORS):
                await fetcher.fetch(f"http://domain{i}.com/page")
            
            # Circuit breaker should be triggered
            assert fetcher._disabled is True
            assert fetcher._disabled_reason == "consecutive_errors"
            
            # Next request should be blocked
            call_count_before = mock_session.get.call_count
            result = await fetcher.fetch("http://new-domain.com/page")
            
            assert result.success is False
            assert "consecutive errors" in result.error.lower()
            assert mock_session.get.call_count == call_count_before  # No new calls
