import json
import yaml
from typing import Dict, Optional, Any, List

from api_watcher.storage.repository import SnapshotRepository
from api_watcher.notifier.base import NotifierManager, ChangeNotification
from api_watcher.utils.smart_comparator import SmartComparator
from api_watcher.logging_config import get_logger

logger = get_logger(__name__)


class ChangeDetector:
    """
    Handles content comparison, AI analysis, and change notifications.
    """
    
    def __init__(
        self, 
        repository: SnapshotRepository,
        notifiers: NotifierManager,
        ai_analyzer: Any = None
    ):
        self.repository = repository
        self.notifiers = notifiers
        self.ai_analyzer = ai_analyzer
        self.comparator = SmartComparator()

    def _save_snapshot(
        self,
        url: str,
        raw_html: str,
        text_content: str,
        api_name: Optional[str],
        method_name: Optional[str],
        content_type: str,
        content_hash: str,
        has_changes: bool,
        ai_summary: Optional[str] = None,
        structured_data: Optional[dict] = None
    ) -> None:
        """Сохраняет snapshot в репозиторий (DRY helper)"""
        self.repository.save(
            url=url,
            raw_html=raw_html,
            text_content=text_content,
            api_name=api_name,
            method_name=method_name,
            content_type=content_type,
            structured_data=structured_data,
            content_hash=content_hash,
            has_changes=has_changes,
            ai_summary=ai_summary
        )

    def _send_notification(
        self,
        api_name: Optional[str],
        method_name: Optional[str],
        url: str,
        summary: str,
        severity: str,
        key_changes: Optional[List[str]] = None
    ) -> None:
        """Отправляет уведомление об изменениях (DRY helper)"""
        notification = ChangeNotification(
            api_name=api_name or 'Unknown API',
            method_name=method_name,
            url=url,
            summary=summary,
            severity=severity,
            key_changes=key_changes
        )
        self.notifiers.send_change(notification)

    def detect_changes(
        self,
        old_snapshot,
        new_html: str,
        content_type: str,
        url: str,
        api_name: Optional[str],
        method_name: Optional[str]
    ) -> Dict:
        """
        Orchestrates the comparison process based on content type.
        """
        if content_type == 'openapi':
            return self._compare_openapi(old_snapshot, new_html, url, api_name, method_name)
        elif content_type == 'json':
            return self._compare_json(old_snapshot, new_html, url, api_name, method_name)
        else:
            return self._compare_html(old_snapshot, new_html, url, api_name, method_name)

    def _compare_openapi(
        self,
        old_snapshot,
        new_html: str,
        url: str,
        api_name: Optional[str],
        method_name: Optional[str]
    ) -> Dict:
        logger.info("comparing_openapi", url=url)
        
        try:
            # Parse old spec
            if old_snapshot.structured_data:
                old_spec = json.loads(old_snapshot.structured_data)
            else:
                # Try JSON first, then YAML
                try:
                    old_spec = json.loads(old_snapshot.raw_html)
                except (json.JSONDecodeError, ValueError):
                    old_spec = yaml.safe_load(old_snapshot.raw_html)
            
            # Parse new spec
            try:
                new_spec = json.loads(new_html)
            except (json.JSONDecodeError, ValueError):
                new_spec = yaml.safe_load(new_html)
            
            has_changes, changes_dict = self.comparator.compare_openapi(old_spec, new_spec)
            
            if not has_changes:
                logger.info("no_openapi_changes", url=url)
                return {'url': url, 'has_changes': False}
            
            logger.info("openapi_changes_detected", url=url)
            
            # Determine severity
            categories = self.comparator.categorize_openapi_changes(changes_dict)
            if categories['breaking_changes']:
                severity = 'major'
            elif categories['new_endpoints'] or categories['removed_endpoints']:
                severity = 'moderate'
            else:
                severity = 'minor'
            
            # AI analysis
            ai_summary = "OpenAPI specification changes detected"
            
            if self.ai_analyzer and changes_dict and severity in ['moderate', 'major']:
                logger.info("ai_analysis_openapi", severity=severity, url=url)
                ai_summary = self.ai_analyzer.analyze_openapi_changes(changes_dict, api_name)
            elif severity == 'minor':
                change_count = len(changes_dict.get('modified', []))
                ai_summary = f"Minor changes ({change_count} items)"
            
            # Save snapshot
            content_hash = self.comparator.calculate_hash(new_html)
            self._save_snapshot(
                url=url,
                raw_html=new_html,
                text_content=json.dumps(new_spec, indent=2),
                api_name=api_name,
                method_name=method_name,
                content_type='openapi',
                content_hash=content_hash,
                has_changes=True,
                ai_summary=ai_summary,
                structured_data=new_spec
            )
            
            # Notify
            self._send_notification(
                api_name=api_name,
                method_name=method_name,
                url=url,
                summary=ai_summary,
                severity=severity
            )
            
            return {
                'url': url,
                'has_changes': True,
                'summary': ai_summary,
                'severity': severity,
                'changes': changes_dict
            }
            
        except Exception as e:
            logger.error("openapi_comparison_error", url=url, error=str(e), exc_info=True)
            return {'url': url, 'has_changes': False, 'error': str(e)}

    def _compare_json(
        self,
        old_snapshot,
        new_html: str,
        url: str,
        api_name: Optional[str],
        method_name: Optional[str]
    ) -> Dict:
        logger.info("comparing_json", url=url)
        
        try:
            old_data = json.loads(old_snapshot.structured_data) if old_snapshot.structured_data else json.loads(old_snapshot.raw_html)
            new_data = json.loads(new_html)
            
            has_changes, changes_dict = self.comparator.compare_json(old_data, new_data)
            
            if not has_changes:
                logger.info("no_json_changes", url=url)
                return {'url': url, 'has_changes': False}
            
            logger.info("json_changes_detected", url=url)
            
            content_hash = self.comparator.calculate_hash(new_html)
            summary = f"JSON changes: {len(changes_dict)} items"
            
            self._save_snapshot(
                url=url,
                raw_html=new_html,
                text_content=json.dumps(new_data, indent=2),
                api_name=api_name,
                method_name=method_name,
                content_type='json',
                content_hash=content_hash,
                has_changes=True,
                ai_summary=summary,
                structured_data=new_data
            )
            
            return {
                'url': url,
                'has_changes': True,
                'summary': summary,
                'severity': 'moderate'
            }
            
        except Exception as e:
            logger.error("json_comparison_error", url=url, error=str(e), exc_info=True)
            return {'url': url, 'has_changes': False, 'error': str(e)}

    def _compare_html(
        self,
        old_snapshot,
        new_html: str,
        url: str,
        api_name: Optional[str],
        method_name: Optional[str]
    ) -> Dict:
        logger.info("comparing_html", url=url)
        
        # Fast hash check
        new_hash = self.comparator.calculate_hash(new_html)
        if old_snapshot.content_hash == new_hash:
            logger.info("content_unchanged_hash_match", url=url)
            return {'url': url, 'has_changes': False}
        
        has_changes, old_text, new_text = self.comparator.compare_html_text(
            old_snapshot.raw_html, new_html
        )
        
        if not has_changes:
            logger.info("no_text_changes", url=url)
            return {'url': url, 'has_changes': False}
        
        logger.info("html_changes_detected", url=url)
        
        # AI analysis
        ai_result = {
            'has_significant_changes': True,
            'summary': 'Changes detected',
            'severity': 'moderate'
        }
        
        if self.ai_analyzer:
            logger.info("ai_analysis_html", url=url)
            ai_result = self.ai_analyzer.analyze_changes(
                old_text, new_text, api_name, method_name
            )
        
        if not ai_result.get('has_significant_changes'):
            logger.info("insignificant_changes", url=url)
            self._save_snapshot(
                url=url,
                raw_html=new_html,
                text_content=new_text,
                api_name=api_name,
                method_name=method_name,
                content_type='html',
                content_hash=new_hash,
                has_changes=False,
                ai_summary="Insignificant changes"
            )
            return {'url': url, 'has_changes': False, 'reason': 'insignificant'}
        
        summary = ai_result.get('summary', 'Significant changes')
        severity = ai_result.get('severity', 'moderate')
        key_changes = ai_result.get('key_changes', [])
        
        self._save_snapshot(
            url=url,
            raw_html=new_html,
            text_content=new_text,
            api_name=api_name,
            method_name=method_name,
            content_type='html',
            content_hash=new_hash,
            has_changes=True,
            ai_summary=summary
        )
        
        # Notify
        self._send_notification(
            api_name=api_name,
            method_name=method_name,
            url=url,
            summary=summary,
            severity=severity,
            key_changes=key_changes
        )
        
        return {
            'url': url,
            'has_changes': True,
            'summary': summary,
            'severity': severity,
            'key_changes': key_changes
        }
