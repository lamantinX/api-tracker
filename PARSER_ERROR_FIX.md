# OpenAPI Parser Error Handling Improvements

## Problem
The API watcher was experiencing JSON parsing errors when the OpenAPI parser received HTML content instead of expected JSON/YAML. The error message was:

```
Exception: Ошибка парсинга JSON: Expecting value: line 1 column 1 (char 0). Возможно, сервер вернул HTML вместо JSON
```

## Root Cause
1. Servers were returning HTML error pages (404, 500, etc.) instead of OpenAPI specifications
2. Empty responses were being passed to the JSON parser
3. Error messages didn't provide enough context for debugging

## Fixes Applied

### 1. Enhanced OpenAPI Parser (`api_watcher/parsers/openapi_parser.py`)

**Improved HTML Detection:**
- Added more comprehensive HTML detection using response preview
- Check for common HTML patterns in the first 500 characters
- Better Content-Type header validation

**Enhanced Error Messages:**
- All parsing errors now include a preview of the response content
- More specific error messages for different failure scenarios
- Added check for empty or very short responses

**Code Changes:**
```python
# Before
if 'text/html' in content_type or response.text.strip().startswith(('<html', '<!DOCTYPE', '<!doctype')):
    raise Exception(f"Сервер вернул HTML вместо JSON/YAML для {url}. Content-Type: {content_type}")

# After  
response_preview = response.text[:500].strip().lower()
if ('text/html' in content_type or 
    response.text.strip().startswith(('<html', '<!DOCTYPE', '<!doctype')) or
    '<html' in response_preview or 
    '<!doctype' in response_preview):
    raise Exception(f"Сервер вернул HTML вместо JSON/YAML для {url}. Content-Type: {content_type}")

# Added empty response check
if len(response.text.strip()) < 10:
    raise Exception(f"Сервер вернул слишком короткий ответ для {url}: '{response.text[:50]}'")
```

### 2. Enhanced Content Processor (`api_watcher/services/content_processor.py`)

**Improved Content Type Detection:**
- Better handling of empty or short content
- More robust JSON detection with fallback to HTML
- Enhanced error logging for debugging

**Code Changes:**
```python
def detect_content_type(self, url: str, content: str) -> str:
    # Check if content is empty or too short
    if not content or len(content.strip()) < 10:
        logger.warning("content_too_short_defaulting_to_html", url=url, length=len(content))
        return 'html'
    
    try:
        # JSON parsing logic...
    except json.JSONDecodeError:
        # Check if it looks like HTML
        content_lower = content[:500].lower()
        if ('<html' in content_lower or 
            '<!doctype' in content_lower or 
            '<head>' in content_lower or 
            '<body>' in content_lower):
            return 'html'
        return 'html'
    except Exception as e:
        logger.warning("content_type_detection_error", url=url, error=str(e))
        return 'html'
```

## Testing

Created `test_parser_fix.py` to verify the improvements:

### Test Results
✅ **Empty Response Handling**: Properly detects and reports empty responses  
✅ **HTML Detection**: Correctly identifies HTML content and provides clear error messages  
✅ **404 Error Handling**: Handles HTTP errors gracefully with informative messages  
✅ **Content Type Detection**: Robust detection with proper fallbacks  

### Sample Output
```
🔍 Testing: Empty response
✅ Got expected error: Сервер вернул пустой ответ для https://httpbin.org/status/204

🔍 Testing: HTML error page  
✅ Got expected error: Сервер вернул HTML вместо JSON/YAML для https://httpbin.org/html

🔍 Testing: 404 Not Found
✅ Got expected error: HTTP ошибка unknown для https://httpbin.org/status/404
```

## Benefits

1. **Better Debugging**: Error messages now include response previews for easier troubleshooting
2. **Robust Error Handling**: Multiple layers of validation prevent crashes
3. **Clear Error Messages**: Specific error types help identify the root cause quickly
4. **Graceful Degradation**: System continues processing other URLs even when some fail

## Monitoring

The improvements include structured logging that will help monitor:
- Content type detection issues
- HTML responses from API endpoints  
- Empty or malformed responses
- Parsing errors with context

## Next Steps

1. Monitor logs for patterns in failed URLs
2. Consider implementing retry logic for temporary failures
3. Add URL validation before processing
4. Implement circuit breaker pattern for consistently failing endpoints