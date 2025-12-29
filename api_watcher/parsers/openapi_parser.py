"""
OpenAPI Parser - парсер для OpenAPI спецификаций (JSON/YAML)
Извлекает информацию о путях, методах, параметрах
"""

import requests
import json
import yaml
from typing import Dict, Any, List, Optional
from requests.exceptions import Timeout, ConnectionError, HTTPError

from api_watcher.config import Config
from api_watcher.logging_config import get_logger

logger = get_logger(__name__)


class OpenAPIParser:
    def __init__(self, user_agent: Optional[str] = None):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': user_agent or Config.USER_AGENT
        })

    def parse(self, url: str, method_filter: str = None) -> Dict[str, Any]:
        """Парсит OpenAPI спецификацию"""
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
        
        # Определяем формат по Content-Type или расширению
        content_type = response.headers.get('content-type', '').lower()
        
        # Проверяем, что это не HTML
        response_preview = response.text[:500].strip().lower()
        html_indicators = [
            'text/html',
            '<!doctype html',
            '<html',
            '<meta charset',
            '<title>',
            '<body>',
            '<head>',
            '\t<meta charset'  # Добавляем проверку на табуляцию перед meta
        ]
        
        if ('text/html' in content_type or 
            response.text.strip().startswith(('<html', '<!DOCTYPE', '<!doctype')) or
            any(indicator in response_preview for indicator in html_indicators)):
            raise Exception(f"Сервер вернул HTML вместо JSON/YAML для {url}. Content-Type: {content_type}")
        
        # Дополнительная проверка на HTML теги в начале контента
        first_line = response.text.strip().split('\n')[0].strip().lower()
        if first_line.startswith(('<', '\t<')) and any(tag in first_line for tag in ['html', 'meta', 'title', 'head', 'body']):
            raise Exception(f"Обнаружен HTML контент в ответе для {url}")
        
        # Проверяем на пустой или почти пустой ответ
        if len(response.text.strip()) < 10:
            raise Exception(f"Сервер вернул слишком короткий ответ для {url}: '{response.text[:50]}'")
        
        try:
            if 'yaml' in content_type or url.endswith(('.yml', '.yaml')):
                spec = yaml.safe_load(response.text)
            else:
                spec = response.json()
        except json.JSONDecodeError as e:
            # Показываем начало ответа для диагностики
            preview = response.text[:200].strip()
            raise Exception(f"Ошибка парсинга JSON: {str(e)}. Начало ответа: {preview}")
        except yaml.YAMLError as e:
            preview = response.text[:200].strip()
            raise Exception(f"Ошибка парсинга YAML: {str(e)}. Начало ответа: {preview}")
        except Exception as e:
            preview = response.text[:200].strip()
            raise Exception(f"Неожиданная ошибка при парсинге ответа: {str(e)}. Начало ответа: {preview}")
        
        return self._extract_api_info(spec, url, method_filter)

    def _extract_api_info(self, spec: Dict[str, Any], url: str, method_filter: str = None) -> Dict[str, Any]:
        """Извлекает ключевую информацию из OpenAPI спецификации"""
        result = {
            'url': url,
            'info': spec.get('info', {}),
            'servers': spec.get('servers', []),
            'paths': {},
            'components': {},
            'method_filter': method_filter
        }
        
        # Извлекаем информацию о путях
        paths = spec.get('paths', {})
        for path, methods in paths.items():
            # Применяем фильтр по методам, если указан
            if method_filter and method_filter not in path:
                continue
                
            result['paths'][path] = {}
            for method, details in methods.items():
                if isinstance(details, dict):
                    result['paths'][path][method] = {
                        'summary': details.get('summary', ''),
                        'description': details.get('description', ''),
                        'parameters': self._extract_parameters(details.get('parameters', [])),
                        'responses': list(details.get('responses', {}).keys()),
                        'tags': details.get('tags', []),
                        'requestBody': self._extract_request_body(details.get('requestBody', {})),
                        'operationId': details.get('operationId', '')
                    }
        
        # Извлекаем компоненты (схемы) только для отфильтрованных путей
        components = spec.get('components', {})
        if 'schemas' in components:
            if method_filter:
                # Фильтруем схемы, связанные с отфильтрованными путями
                used_schemas = self._get_used_schemas(result['paths'], components['schemas'])
                result['components']['schemas'] = used_schemas
            else:
                result['components']['schemas'] = list(components['schemas'].keys())
        
        return result

    def _extract_parameters(self, parameters: list) -> list:
        """Извлекает информацию о параметрах"""
        result = []
        for param in parameters:
            if isinstance(param, dict):
                result.append({
                    'name': param.get('name', ''),
                    'in': param.get('in', ''),
                    'required': param.get('required', False),
                    'type': param.get('schema', {}).get('type', '') if 'schema' in param else param.get('type', '')
                })
        return result

    def _extract_request_body(self, request_body: Dict[str, Any]) -> Dict[str, Any]:
        """Извлекает информацию о теле запроса"""
        if not request_body:
            return {}
        
        result = {
            'description': request_body.get('description', ''),
            'required': request_body.get('required', False),
            'content': {}
        }
        
        content = request_body.get('content', {})
        for media_type, schema_info in content.items():
            result['content'][media_type] = {
                'schema': schema_info.get('schema', {}),
                'examples': schema_info.get('examples', {})
            }
        
        return result

    def _get_used_schemas(self, paths: Dict[str, Any], all_schemas: Dict[str, Any]) -> List[str]:
        """Определяет, какие схемы используются в отфильтрованных путях"""
        used_schemas = set()
        
        def extract_schema_refs(obj):
            """Рекурсивно извлекает ссылки на схемы"""
            if isinstance(obj, dict):
                if '$ref' in obj:
                    ref = obj['$ref']
                    if ref.startswith('#/components/schemas/'):
                        schema_name = ref.split('/')[-1]
                        used_schemas.add(schema_name)
                else:
                    for value in obj.values():
                        extract_schema_refs(value)
            elif isinstance(obj, list):
                for item in obj:
                    extract_schema_refs(item)
        
        # Ищем ссылки на схемы во всех путях
        extract_schema_refs(paths)
        
        return list(used_schemas)