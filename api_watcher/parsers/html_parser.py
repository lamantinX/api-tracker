"""
HTML Parser - парсер для HTML-страниц документации
Извлекает h2, code, p элементы из API-секций
"""

import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Any, Optional
from requests.exceptions import Timeout, ConnectionError, HTTPError

from api_watcher.config import Config
from api_watcher.logging_config import get_logger

logger = get_logger(__name__)


class HTMLParser:
    def __init__(self, user_agent: Optional[str] = None):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': user_agent or Config.USER_AGENT
        })

    def parse(self, url: str, selector: str = None) -> Dict[str, Any]:
        """Парсит HTML-страницу и извлекает API-документацию"""
        # Разделяем URL и якорь
        base_url = url.split('#')[0]
        anchor = url.split('#')[1] if '#' in url else None
        
        try:
            # Stream, чтобы можно было ограничить размер скачиваемого контента
            response = self.session.get(base_url, timeout=Config.REQUEST_TIMEOUT, stream=True)
            response.raise_for_status()
        except Timeout:
            raise Exception(f"Timeout при подключении к {base_url}")
        except ConnectionError as e:
            raise Exception(f"Ошибка подключения к {base_url}: {str(e)}")
        except HTTPError as e:
            status_code = e.response.status_code if e.response else 'unknown'
            raise Exception(f"HTTP ошибка {status_code} для {base_url}")
        except Exception as e:
            raise Exception(f"Неожиданная ошибка при запросе {base_url}: {str(e)}")
        
        # Проверяем Content-Type на HTML (минимальная защита от неожиданных бинарных/огромных ответов)
        content_type = (response.headers.get('content-type') or '').lower()
        if content_type and 'text/html' not in content_type and 'application/xhtml' not in content_type:
            logger.warning("non_html_content_type", url=base_url, content_type=content_type)

        # Читаем контент с ограничением по размеру
        max_bytes = max(1, int(getattr(Config, "MAX_RESPONSE_BYTES", 2 * 1024 * 1024)))
        content_length = response.headers.get("Content-Length")
        if content_length:
            try:
                if int(content_length) > max_bytes:
                    raise Exception(f"Слишком большой HTML ответ для {base_url}: {content_length} bytes > {max_bytes}")
            except ValueError:
                pass

        content_bytes = bytearray()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            content_bytes.extend(chunk)
            if len(content_bytes) > max_bytes:
                raise Exception(f"Слишком большой HTML ответ для {base_url}: read>{max_bytes} bytes")

        # Проверяем, что контент не пустой
        if not content_bytes:
            logger.warning("empty_html_response", url=base_url)
            raise Exception(f"Сервер вернул пустой ответ для {base_url}")
        
        soup = BeautifulSoup(bytes(content_bytes), 'html.parser')
        
        # Определяем целевую секцию
        if selector:
            target_section = soup.select_one(selector)
            if not target_section:
                logger.warning("selector_not_found", selector=selector, url=base_url)
                target_section = soup
        elif anchor:
            # Ищем элемент с id равным якорю
            target_section = soup.find(id=anchor)
            if not target_section:
                # Ищем ссылку на якорь
                anchor_link = soup.find('a', {'name': anchor})
                if anchor_link:
                    target_section = anchor_link.find_parent()
                else:
                    # Ищем заголовок, содержащий якорь в тексте
                    headers = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
                    for header in headers:
                        if anchor.lower().replace('-', ' ') in header.get_text().lower():
                            target_section = header
                            break
                    
                    if not target_section or target_section == soup:
                        # Ищем по data-атрибутам или классам
                        target_section = soup.find(attrs={'data-anchor': anchor}) or \
                                       soup.find(class_=anchor) or \
                                       soup.find(attrs={'data-id': anchor})
                        
                        if not target_section:
                            logger.warning("anchor_not_found", anchor=anchor, url=base_url)
                            target_section = soup
        else:
            target_section = soup
        
        # Если найдена конкретная секция, извлекаем её и соседние элементы
        if target_section and target_section != soup:
            method_content = self._extract_method_content(target_section)
        else:
            # Fallback к поиску API-секций
            api_sections = self._find_api_sections(soup)
            method_content = []
            for section in api_sections:
                section_data = {
                    'headers': self._extract_headers(section),
                    'code_blocks': self._extract_code_blocks(section),
                    'paragraphs': self._extract_paragraphs(section)
                }
                method_content.append(section_data)
        
        result = {
            'url': url,
            'title': self._get_page_title(soup),
            'target_selector': selector or f"#{anchor}" if anchor else "full_page",
            'method_content': method_content
        }
        
        return result

    def _find_api_sections(self, soup: BeautifulSoup) -> List:
        """Находит секции с API-документацией"""
        # Ищем по различным селекторам, характерным для API-документации
        selectors = [
            '[class*="api"]',
            '[id*="api"]',
            '[class*="endpoint"]',
            '[class*="method"]',
            '.documentation',
            '.docs',
            'main',
            'article'
        ]
        
        sections = []
        for selector in selectors:
            found = soup.select(selector)
            if found:
                sections.extend(found)
                break  # Используем первый найденный селектор
        
        # Если ничего не найдено, используем весь body
        if not sections:
            body = soup.find('body')
            if body:
                sections = [body]
        
        return sections

    def _get_page_title(self, soup: BeautifulSoup) -> str:
        """Извлекает заголовок страницы"""
        title_tag = soup.find('title')
        return title_tag.get_text().strip() if title_tag else 'No title'

    def _extract_headers(self, section) -> List[str]:
        """Извлекает заголовки h2"""
        headers = section.find_all('h2')
        return [h.get_text().strip() for h in headers]

    def _extract_code_blocks(self, section) -> List[str]:
        """Извлекает блоки кода"""
        code_elements = section.find_all(['code', 'pre'])
        return [code.get_text().strip() for code in code_elements if code.get_text().strip()]

    def _extract_paragraphs(self, section) -> List[str]:
        """Извлекает параграфы"""
        paragraphs = section.find_all('p')
        return [p.get_text().strip() for p in paragraphs if p.get_text().strip()]

    def _extract_method_content(self, target_section) -> Dict[str, Any]:
        """Извлекает контент конкретного метода API"""
        method_data = {
            'method_name': self._get_method_name(target_section),
            'description': self._get_method_description(target_section),
            'parameters': self._extract_parameters_table(target_section),
            'request_examples': self._extract_request_examples(target_section),
            'response_examples': self._extract_response_examples(target_section),
            'headers': self._extract_headers(target_section),
            'code_blocks': self._extract_code_blocks(target_section),
            'tables': self._extract_tables(target_section)
        }
        
        # Также ищем контент в следующих элементах (до следующего заголовка того же уровня)
        next_content = self._get_method_section_content(target_section)
        if next_content:
            method_data.update(next_content)
        
        return method_data

    def _get_method_name(self, section) -> str:
        """Извлекает название метода"""
        try:
            # Ищем заголовок в самой секции
            for tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                header = section.find(tag)
                if header and hasattr(header, 'get_text'):
                    return header.get_text().strip()
            
            # Если не найден, возвращаем ID секции или URL якорь
            section_id = section.get('id') if hasattr(section, 'get') else None
            if section_id:
                return section_id
            
            return 'Unknown Method'
        except Exception as e:
            return f'Method (error: {str(e)})'

    def _get_method_description(self, section) -> str:
        """Извлекает описание метода"""
        # Ищем первый параграф с описанием
        description_p = section.find('p')
        if description_p:
            return description_p.get_text().strip()
        return ""

    def _extract_parameters_table(self, section) -> List[Dict[str, str]]:
        """Извлекает таблицу параметров"""
        parameters = []
        tables = section.find_all('table')
        
        for table in tables:
            headers = [th.get_text().strip().lower() for th in table.find_all('th')]
            if any(keyword in ' '.join(headers) for keyword in ['parameter', 'param', 'field', 'name']):
                rows = table.find_all('tr')[1:]  # Пропускаем заголовок
                for row in rows:
                    cells = [td.get_text().strip() for td in row.find_all(['td', 'th'])]
                    if len(cells) >= 2:
                        param = {
                            'name': cells[0],
                            'description': cells[1] if len(cells) > 1 else '',
                            'type': cells[2] if len(cells) > 2 else '',
                            'required': cells[3] if len(cells) > 3 else ''
                        }
                        parameters.append(param)
        
        return parameters

    def _extract_request_examples(self, section) -> List[str]:
        """Извлекает примеры запросов"""
        examples = []
        
        # Ищем блоки кода, которые могут быть примерами запросов
        code_blocks = section.find_all(['pre', 'code'])
        for block in code_blocks:
            text = block.get_text().strip()
            # Проверяем, похоже ли на HTTP запрос
            if any(method in text.upper() for method in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']):
                examples.append(text)
            elif 'curl' in text.lower() or 'http' in text.lower():
                examples.append(text)
        
        return examples

    def _extract_response_examples(self, section) -> List[str]:
        """Извлекает примеры ответов"""
        examples = []
        
        # Ищем JSON блоки или блоки с ответами
        code_blocks = section.find_all(['pre', 'code'])
        for block in code_blocks:
            text = block.get_text().strip()
            # Проверяем, похоже ли на JSON ответ
            if text.startswith('{') and text.endswith('}'):
                examples.append(text)
            elif ('response' in (block.get('class') or []) or 
                  'response' in (block.parent.get('class') if block.parent else [])):
                examples.append(text)
        
        return examples

    def _extract_tables(self, section) -> List[Dict[str, Any]]:
        """Извлекает все таблицы из секции"""
        tables_data = []
        tables = section.find_all('table')
        
        for table in tables:
            headers = [th.get_text().strip() for th in table.find_all('th')]
            rows = []
            
            for tr in table.find_all('tr')[1:]:  # Пропускаем заголовок
                row_data = [td.get_text().strip() for td in tr.find_all(['td', 'th'])]
                if row_data:
                    rows.append(row_data)
            
            if headers or rows:
                tables_data.append({
                    'headers': headers,
                    'rows': rows
                })
        
        return tables_data

    def _get_method_section_content(self, target_section) -> Dict[str, Any]:
        """Получает весь контент секции метода до следующего заголовка"""
        content = {
            'full_text': '',
            'additional_elements': []
        }
        
        # Собираем текст из текущего элемента
        content['full_text'] = target_section.get_text().strip()
        
        # Ищем следующие элементы до следующего заголовка того же уровня
        current = target_section.next_sibling
        while current:
            if hasattr(current, 'name'):
                # Если встретили заголовок того же или более высокого уровня - останавливаемся
                if current.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    break
                
                # Добавляем контент элемента
                if current.get_text().strip():
                    content['additional_elements'].append({
                        'tag': current.name,
                        'text': current.get_text().strip(),
                        'class': current.get('class', [])
                    })
            
            current = current.next_sibling
        
        return content