"""
ZenRows client for fetching web content
Обходит защиту и получает чистый HTML
"""

import requests
from typing import Optional, Dict

from api_watcher.logging_config import get_logger

logger = get_logger(__name__)


class ZenRowsClient:
    """Клиент для работы с ZenRows API"""
    
    BASE_URL = "https://api.zenrows.com/v1/"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    def fetch_html(
        self,
        url: str,
        js_render: bool = True,
        premium_proxy: bool = False,
        antibot: bool = True
    ) -> Optional[str]:
        """
        Получает HTML контент через ZenRows
        
        Args:
            url: URL для получения
            js_render: Рендерить JavaScript
            premium_proxy: Использовать премиум прокси
            antibot: Обход антибот защиты
        
        Returns:
            HTML контент или None при ошибке
        """
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
        
        try:
            response = requests.get(self.BASE_URL, params=params, timeout=60)
            response.raise_for_status()
            
            logger.info("zenrows_fetch_success", url=url)
            return response.text
            
        except requests.exceptions.RequestException as e:
            logger.error("zenrows_request_error", url=url, error=str(e))
            return None
    
    def fetch_with_fallback(self, url: str) -> Optional[str]:
        """
        Получает контент с fallback стратегией:
        1. Попытка с базовыми настройками
        2. Попытка с премиум прокси
        3. Попытка без JS рендеринга
        """
        # Попытка 1: базовые настройки
        html = self.fetch_html(url, js_render=True, premium_proxy=False)
        if html:
            return html
        
        logger.warning("zenrows_retry_no_js", url=url)
        
        # Попытка 2: без JS рендеринга
        html = self.fetch_html(url, js_render=False, premium_proxy=False)
        return html
