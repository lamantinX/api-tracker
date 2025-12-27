import json
from typing import Optional, Dict, Tuple, Union, overload

from api_watcher.config import Config
from api_watcher.utils.docs_finder import find_api_documentation
from api_watcher.notifier.base import NotifierManager, DocumentationUpdate
from api_watcher.logging_config import get_logger

logger = get_logger(__name__)

class ContentProcessor:
    """
    Handles content validation, type detection, and documentation discovery.
    """
    
    def __init__(self, notifier_manager: NotifierManager):
        self.notifiers = notifier_manager
        self.config = Config

    def is_valid_response(
        self, 
        content: str, 
        url: str, 
        status_code: int = 200,
        return_details: bool = False
    ) -> Union[bool, Tuple[bool, Optional[str]]]:
        """
        Checks if the response content is valid.
        
        Args:
            content: Response content (HTML, JSON, etc.)
            url: URL that was fetched
            status_code: HTTP status code
            return_details: If True, returns Tuple[bool, error_reason], else just bool
            
        Returns:
            bool if return_details=False (default), else Tuple of (is_valid, error_reason)
        """
        def _result(is_valid: bool, reason: Optional[str] = None):
            """Helper to return correct type based on return_details flag"""
            if return_details:
                return is_valid, reason
            return is_valid
        
        if not content:
            logger.warning("empty_response", url=url, status_code=status_code)
            return _result(False, "Empty response")
        
        # Check HTTP status code
        if status_code < 200 or status_code >= 300:
            logger.warning(
                "invalid_status_code", 
                url=url, 
                status_code=status_code,
                content_length=len(content)
            )
            return _result(False, f"HTTP {status_code}")
        
        # Try to parse as JSON and check for error fields FIRST.
        # Важно: не пытаемся json.loads() на любой HTML-странице — это дорого на больших ответах.
        stripped = content.lstrip()
        looks_like_json = bool(stripped) and stripped[0] in ['{', '[']
        max_json_chars = max(1, int(getattr(Config, "MAX_JSON_PARSE_CHARS", 2 * 1024 * 1024)))

        try:
            if not looks_like_json or len(content) > max_json_chars:
                raise json.JSONDecodeError("Skip JSON parse (heuristics)", content, 0)

            data = json.loads(content)
            
            # Check for explicit error indicators
            if isinstance(data, dict):
                # Check for {"error": "..."}
                if 'error' in data and data['error']:
                    error_msg = str(data['error'])
                    logger.warning(
                        "json_error_field",
                        url=url,
                        error=error_msg,
                        status_code=status_code
                    )
                    return _result(False, f"JSON error: {error_msg}")
                
                # Check for {"success": false}
                if 'success' in data and data['success'] is False:
                    error_msg = data.get('message', 'Unknown error')
                    logger.warning(
                        "json_success_false",
                        url=url,
                        message=error_msg,
                        status_code=status_code
                    )
                    return _result(False, f"API error: {error_msg}")
                
                # Check for {"status": "error"}
                if 'status' in data and str(data['status']).lower() in ['error', 'fail', 'failed']:
                    error_msg = data.get('message', 'Unknown error')
                    logger.warning(
                        "json_status_error",
                        url=url,
                        status=data['status'],
                        message=error_msg,
                        status_code=status_code
                    )
                    return _result(False, f"Status error: {error_msg}")
            
            # JSON is valid and has no error indicators
            # For JSON, we don't enforce the 100 char minimum
            return _result(True, None)
            
        except json.JSONDecodeError:
            # Not JSON, continue with HTML/text validation
            pass
        
        # Check content length for non-JSON content
        if len(content) < 100:
            logger.warning(
                "short_response", 
                url=url, 
                content_length=len(content),
                status_code=status_code
            )
            return _result(False, f"Short response ({len(content)} chars)")
        
        # HTML/Text validation - check for common error indicators
        # Only check the beginning of the content to avoid false positives (и не делать lower() на весь ответ)
        content_start = content[:1000].lower()  # Check only first 1000 chars
        
        # Check for error page patterns (usually in title or at the start)
        error_page_indicators = [
            '<title>404',
            '<title>not found',
            '<title>error',
            '<title>forbidden',
            '<h1>404',
            '<h1>not found',
            '<h1>error',
            '<h1>forbidden',
            '<h1>500',
            '<h1>internal server error',
        ]
        
        for indicator in error_page_indicators:
            if indicator in content_start:
                error_type = indicator.split('>')[1] if '>' in indicator else indicator
                logger.warning(
                    "error_page_detected",
                    url=url,
                    indicator=error_type,
                    status_code=status_code
                )
                return _result(False, f"Error page: {error_type}")
        
        # Check for very obvious error patterns at the start
        if content_start.startswith('<!doctype html>') or content_start.startswith('<html'):
            # It's HTML, check if it looks like an error page
            if any(pattern in content_start for pattern in ['404 not found', 'page not found', '403 forbidden', '500 internal server error', 'service unavailable']):
                logger.warning(
                    "html_error_page",
                    url=url,
                    status_code=status_code
                )
                return _result(False, "HTML error page detected")
        
        # All checks passed
        return _result(True, None)

    def detect_content_type(self, url: str, content: str) -> str:
        """Detects the content type (openapi, json, html)."""
        if 'openapi' in url.lower() or 'swagger' in url.lower():
            return 'openapi'
        
        try:
            stripped = content.lstrip()
            looks_like_json = bool(stripped) and stripped[0] in ['{', '[']
            max_json_chars = max(1, int(getattr(Config, "MAX_JSON_PARSE_CHARS", 2 * 1024 * 1024)))
            if not looks_like_json or len(content) > max_json_chars:
                raise json.JSONDecodeError("Skip JSON parse (heuristics)", content, 0)

            data = json.loads(content)
            if 'openapi' in data or 'swagger' in data:
                return 'openapi'
            return 'json'
        except:
            return 'html'

    async def try_find_new_documentation(
        self,
        url: str,
        api_name: Optional[str],
        method_name: Optional[str]
    ) -> Optional[str]:
        """Attempts to find new documentation URL if the current one is invalid."""
        logger.info("searching_new_documentation", url=url, api_name=api_name, method_name=method_name)
        
        try:
            docs_info = await find_api_documentation(
                url=url,
                api_name=api_name,
                method_name=method_name,
                serpapi_key=self.config.SERPAPI_KEY
            )
            
            if docs_info and docs_info.get('url'):
                new_url = docs_info['url']
                doc_type = docs_info.get('type', 'unknown')
                
                logger.info(
                    "found_new_documentation",
                    url=url,
                    new_url=new_url,
                    doc_type=doc_type
                )
                
                # Notify via adapters
                update = DocumentationUpdate(
                    api_name=api_name or 'Unknown',
                    method_name=method_name,
                    old_url=url,
                    new_url=new_url,
                    doc_type=doc_type,
                    title=docs_info.get('title')
                )
                self.notifiers.send_doc_update(update)
                
                return new_url
        except Exception as e:
            logger.error("documentation_search_failed", url=url, error=str(e), exc_info=True)
        
        return None
