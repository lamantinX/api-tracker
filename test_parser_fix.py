#!/usr/bin/env python3
"""
Test script to verify the OpenAPI parser error handling improvements
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'api_watcher'))

from api_watcher.parsers.openapi_parser import OpenAPIParser
from api_watcher.services.content_processor import ContentProcessor
from api_watcher.notifier.base import NotifierManager
from api_watcher.notifier.adapters import ConsoleAdapter

def test_openapi_parser_error_handling():
    """Test OpenAPI parser with various error scenarios"""
    print("\n" + "="*60)
    print("🧪 TESTING OPENAPI PARSER ERROR HANDLING")
    print("="*60)
    
    parser = OpenAPIParser()
    
    # Test cases that should trigger better error messages
    test_cases = [
        {
            'name': 'Empty response',
            'url': 'https://httpbin.org/status/204',  # Returns empty response
            'expected_error': 'пустой ответ'
        },
        {
            'name': 'HTML error page',
            'url': 'https://httpbin.org/html',  # Returns HTML
            'expected_error': 'HTML вместо JSON'
        },
        {
            'name': '404 Not Found',
            'url': 'https://httpbin.org/status/404',  # Returns 404
            'expected_error': 'HTTP ошибка 404'
        }
    ]
    
    for test_case in test_cases:
        print(f"\n🔍 Testing: {test_case['name']}")
        print(f"URL: {test_case['url']}")
        
        try:
            result = parser.parse(test_case['url'])
            print(f"❌ Expected error but got result: {type(result)}")
        except Exception as e:
            error_msg = str(e)
            print(f"✅ Got expected error: {error_msg}")
            
            # Check if error message contains expected text
            if any(keyword in error_msg.lower() for keyword in test_case['expected_error'].lower().split()):
                print(f"✅ Error message contains expected keywords")
            else:
                print(f"⚠️ Error message doesn't contain expected keywords: {test_case['expected_error']}")
    
    print("\n" + "="*60)

def test_content_processor():
    """Test content processor improvements"""
    print("\n" + "="*60)
    print("🧪 TESTING CONTENT PROCESSOR")
    print("="*60)
    
    notifier_manager = NotifierManager()
    notifier_manager.register(ConsoleAdapter())
    processor = ContentProcessor(notifier_manager)
    
    # Test content type detection
    test_contents = [
        ('', 'Empty content'),
        ('{"test": "json"}', 'Valid JSON'),
        ('<html><body>Error 404</body></html>', 'HTML content'),
        ('invalid json {', 'Invalid JSON'),
        ('{"openapi": "3.0.0"}', 'OpenAPI JSON'),
    ]
    
    for content, description in test_contents:
        print(f"\n🔍 Testing: {description}")
        content_type = processor.detect_content_type('https://example.com/test', content)
        print(f"Detected type: {content_type}")
        
        # Test validation
        is_valid, reason = processor.is_valid_response(content, 'https://example.com/test', return_details=True)
        print(f"Valid: {is_valid}")
        if reason:
            print(f"Reason: {reason}")
    
    print("\n" + "="*60)

if __name__ == '__main__':
    print("\n🚀 API WATCHER - PARSER ERROR HANDLING TEST")
    
    try:
        test_content_processor()
        test_openapi_parser_error_handling()
        
        print("\n🎉 All tests completed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)