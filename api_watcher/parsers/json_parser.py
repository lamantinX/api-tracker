"""
JSON Parser - парсер для произвольных JSON Schema
Сравнивает ключи и значения структуры
"""

import requests
import json
import os
import urllib.parse
from typing import Dict, Any, Optional
from requests.exceptions import Timeout, ConnectionError, HTTPError

from api_watcher.config import Config
from api_watcher.logging_config import get_logger

logger = get_logger(__name__)


class JSONParser:
    def __init__(self, user_agent: Optional[str] = None):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': user_agent or Config.USER_AGENT
        })

    def parse(self, url: str, **kwargs) -> Dict[str, Any]:
        """Парсит JSON документ"""
        if url.startswith('file://') or not url.startswith('http'):
            # Локальный файл
            if url.startswith('file://'):
                file_path = urllib.parse.unquote(url[7:])  # Убираем file://
            else:
                file_path = url
            
            # Если путь относительный, делаем его абсолютным
            if not os.path.isabs(file_path):
                file_path = os.path.abspath(file_path)
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except FileNotFoundError:
                raise Exception(f"Файл не найден: {file_path}")
            except json.JSONDecodeError as e:
                raise Exception(f"Ошибка парсинга JSON файла: {str(e)}")
            except Exception as e:
                raise Exception(f"Ошибка чтения файла {file_path}: {str(e)}")
        else:
            # Удаленный файл
            try:
                response = self.session.get(url, timeout=Config.REQUEST_TIMEOUT)
                response.raise_for_status()
            except Timeout:
                raise Exception(f"Timeout при подключении к {url}")
            except ConnectionError as e:
                raise Exception(f"Ошибка подключения к {url}: {str(e)}")
            except HTTPError as e:
                status_code = e.response.status_code if e.response else 'unknown'
                raise Exception(f"HTTP ошибка {status_code} для {url}")
            
            # Проверяем, что ответ не пустой
            if not response.text or not response.text.strip():
                raise Exception(f"Сервер вернул пустой ответ для {url}")
            
            # Проверяем, что это не HTML
            content_type = response.headers.get('content-type', '').lower()
            response_preview = response.text[:500].strip().lower()
            
            html_indicators = [
                'text/html',
                '<!doctype html',
                '<html',
                '<meta charset',
                '<title>',
                '<body>',
                '<head>',
                '\t<meta charset',  # Табуляция перед meta
                '    <meta charset'  # Пробелы перед meta
            ]
            
            if ('text/html' in content_type or 
                response.text.strip().startswith(('<html', '<!DOCTYPE', '<!doctype')) or
                any(indicator in response_preview for indicator in html_indicators)):
                raise Exception(f"Сервер вернул HTML вместо JSON для {url}. Content-Type: {content_type}")
            
            # Дополнительная проверка на HTML теги в начале контента
            first_line = response.text.strip().split('\n')[0].strip().lower()
            if first_line.startswith(('<', '\t<', '    <')) and any(tag in first_line for tag in ['html', 'meta', 'title', 'head', 'body']):
                raise Exception(f"Обнаружен HTML контент в ответе для {url}")
            
            try:
                data = response.json()
            except json.JSONDecodeError as e:
                preview = response.text[:200].strip()
                raise Exception(f"Ошибка парсинга JSON: {str(e)}. Начало ответа: {preview}")
            except Exception as e:
                raise Exception(f"Неожиданная ошибка при парсинге ответа: {str(e)}")
        
        return {
            'url': url,
            'structure': self._analyze_structure(data),
            'keys': self._extract_all_keys(data),
            'data': data  # Сохраняем полные данные для сравнения
        }

    def _analyze_structure(self, data: Any, path: str = '') -> Dict[str, Any]:
        """Анализирует структуру JSON"""
        if isinstance(data, dict):
            return {
                'type': 'object',
                'keys': list(data.keys()),
                'children': {
                    key: self._analyze_structure(value, f"{path}.{key}" if path else key)
                    for key, value in data.items()
                }
            }
        elif isinstance(data, list):
            return {
                'type': 'array',
                'length': len(data),
                'item_types': list(set(type(item).__name__ for item in data)) if data else []
            }
        else:
            return {
                'type': type(data).__name__,
                'value': str(data) if len(str(data)) < 100 else str(data)[:100] + '...'
            }

    def _extract_all_keys(self, data: Any, keys: set = None) -> list:
        """Извлекает все ключи из JSON структуры"""
        if keys is None:
            keys = set()
        
        if isinstance(data, dict):
            keys.update(data.keys())
            for value in data.values():
                self._extract_all_keys(value, keys)
        elif isinstance(data, list):
            for item in data:
                self._extract_all_keys(item, keys)
        
        return sorted(list(keys))