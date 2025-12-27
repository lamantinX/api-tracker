"""
Smart comparator with AI integration
Умное сравнение с использованием структурного анализа и AI
"""

from typing import Dict, Optional, Tuple
from deepdiff import DeepDiff
import hashlib
import html2text
import logging

from api_watcher.config import Config

logger = logging.getLogger(__name__)


class SmartComparator:
    """Умный компаратор с поддержкой разных типов контента"""
    
    def __init__(self):
        self.html_converter = html2text.HTML2Text()
        self.html_converter.ignore_links = False
        self.html_converter.ignore_images = True
        self.html_converter.ignore_emphasis = False
    
    def html_to_text(self, html: str) -> str:
        """Конвертирует HTML в читаемый текст"""
        try:
            max_chars = max(1, int(getattr(Config, "MAX_HTML_TO_TEXT_CHARS", 500_000)))
            if len(html) > max_chars:
                # Защита: не конвертируем огромные HTML целиком (это может быть очень дорого).
                # Берём начало и конец, чтобы сохранить контекст и хоть какую-то стабильность сравнения.
                half = max_chars // 2
                html = (
                    html[:half]
                    + "\n<!-- api_watcher: truncated_html_to_text -->\n"
                    + html[-half:]
                )
            return self.html_converter.handle(html)
        except Exception as e:
            logger.error(f"❌ Ошибка конвертации HTML: {e}")
            return html
    
    def calculate_hash(self, content: str) -> str:
        """Вычисляет хеш контента для быстрого сравнения"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def compare_openapi(
        self,
        old_spec: Dict,
        new_spec: Dict,
        ignore_paths: Optional[list] = None
    ) -> Tuple[bool, Optional[Dict]]:
        """
        Структурное сравнение OpenAPI спецификаций
        
        Returns:
            (has_changes, changes_dict)
        """
        if ignore_paths is None:
            ignore_paths = [
                "root['info']['version']",  # Игнорируем версию
                "root['servers']",  # Игнорируем серверы
            ]
        
        try:
            diff = DeepDiff(
                old_spec,
                new_spec,
                ignore_order=True,
                exclude_paths=ignore_paths,
                verbose_level=2
            )
            
            has_changes = bool(diff)
            
            if has_changes:
                logger.info(f"🔍 OpenAPI: обнаружены изменения")
                return True, dict(diff)
            else:
                logger.info(f"✅ OpenAPI: изменений не обнаружено")
                return False, None
                
        except Exception as e:
            logger.error(f"❌ Ошибка сравнения OpenAPI: {e}")
            return False, None
    
    def compare_json(
        self,
        old_data: Dict,
        new_data: Dict,
        ignore_paths: Optional[list] = None
    ) -> Tuple[bool, Optional[Dict]]:
        """
        Структурное сравнение JSON данных
        
        Returns:
            (has_changes, changes_dict)
        """
        if ignore_paths is None:
            ignore_paths = []
        
        try:
            diff = DeepDiff(
                old_data,
                new_data,
                ignore_order=True,
                exclude_paths=ignore_paths,
                verbose_level=2
            )
            
            has_changes = bool(diff)
            
            if has_changes:
                logger.info(f"🔍 JSON: обнаружены изменения")
                return True, dict(diff)
            else:
                logger.info(f"✅ JSON: изменений не обнаружено")
                return False, None
                
        except Exception as e:
            logger.error(f"❌ Ошибка сравнения JSON: {e}")
            return False, None
    
    def quick_compare(self, old_content: str, new_content: str) -> bool:
        """
        Быстрое сравнение по хешу
        
        Returns:
            True если контент изменился
        """
        old_hash = self.calculate_hash(old_content)
        new_hash = self.calculate_hash(new_content)
        
        return old_hash != new_hash
    
    def compare_html_text(
        self,
        old_html: str,
        new_html: str
    ) -> Tuple[bool, str, str]:
        """
        Сравнивает HTML, конвертируя в текст
        
        Returns:
            (has_changes, old_text, new_text)
        """
        old_text = self.html_to_text(old_html)
        new_text = self.html_to_text(new_html)
        
        has_changes = self.quick_compare(old_text, new_text)
        
        return has_changes, old_text, new_text
    
    def categorize_openapi_changes(self, changes_dict: Dict) -> Dict[str, list]:
        """
        Категоризирует изменения OpenAPI для лучшего понимания
        
        Returns:
            {
                'new_endpoints': [...],
                'removed_endpoints': [...],
                'modified_endpoints': [...],
                'schema_changes': [...],
                'breaking_changes': [...]
            }
        """
        categories = {
            'new_endpoints': [],
            'removed_endpoints': [],
            'modified_endpoints': [],
            'schema_changes': [],
            'breaking_changes': []
        }
        
        # Анализируем добавленные элементы
        if 'dictionary_item_added' in changes_dict:
            for item in changes_dict['dictionary_item_added']:
                if 'paths' in item:
                    categories['new_endpoints'].append(item)
                elif 'components' in item or 'schemas' in item:
                    categories['schema_changes'].append(item)
        
        # Анализируем удаленные элементы
        if 'dictionary_item_removed' in changes_dict:
            for item in changes_dict['dictionary_item_removed']:
                if 'paths' in item:
                    categories['removed_endpoints'].append(item)
                    categories['breaking_changes'].append(f"Удален endpoint: {item}")
                elif 'components' in item or 'schemas' in item:
                    categories['schema_changes'].append(item)
                    categories['breaking_changes'].append(f"Удалена схема: {item}")
        
        # Анализируем измененные элементы
        if 'values_changed' in changes_dict:
            for item in changes_dict['values_changed']:
                if 'paths' in str(item):
                    categories['modified_endpoints'].append(item)
                elif 'required' in str(item):
                    categories['breaking_changes'].append(f"Изменены обязательные поля: {item}")
        
        return categories
