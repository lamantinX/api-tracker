#!/usr/bin/env python3
"""
HTTP сервер для health check endpoint
Может использоваться для мониторинга в Kubernetes, Docker Swarm и других оркестраторах
"""

import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import argparse
import sys
from health_check import check_health


class HealthHandler(BaseHTTPRequestHandler):
    """HTTP обработчик для health check запросов"""
    
    def do_GET(self):
        """Обрабатывает GET запросы"""
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == '/health':
            self._handle_health_check(parsed_path)
        elif parsed_path.path == '/':
            self._handle_root()
        else:
            self._send_error(404, "Not Found")
    
    def _handle_health_check(self, parsed_path):
        """Обрабатывает запрос health check"""
        try:
            # Получаем параметры запроса
            query_params = parse_qs(parsed_path.query)
            max_age = int(query_params.get('max_age', [60])[0])
            
            # Выполняем проверку здоровья
            result = check_health(max_age_minutes=max_age)
            
            # Определяем HTTP статус код
            if result['healthy']:
                status_code = 200
            elif result['status'] in ['degraded', 'warning']:
                status_code = 200  # Degraded все еще считается рабочим
            else:
                status_code = 503  # Service Unavailable
            
            self._send_json_response(status_code, result)
            
        except Exception as e:
            logging.error(f"Error in health check: {e}")
            self._send_error(500, f"Internal Server Error: {e}")
    
    def _handle_root(self):
        """Обрабатывает корневой запрос"""
        response = {
            "service": "API Watcher",
            "endpoints": {
                "/health": "Health check endpoint",
                "/health?max_age=120": "Health check with custom max age (minutes)"
            }
        }
        self._send_json_response(200, response)
    
    def _send_json_response(self, status_code, data):
        """Отправляет JSON ответ"""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        
        json_data = json.dumps(data, indent=2, ensure_ascii=False)
        self.wfile.write(json_data.encode('utf-8'))
    
    def _send_error(self, status_code, message):
        """Отправляет ошибку"""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        
        error_data = {
            "error": message,
            "status_code": status_code
        }
        json_data = json.dumps(error_data, ensure_ascii=False)
        self.wfile.write(json_data.encode('utf-8'))
    
    def log_message(self, format, *args):
        """Переопределяем логирование для использования стандартного логгера"""
        logging.info(f"{self.address_string()} - {format % args}")


def main():
    parser = argparse.ArgumentParser(description='Health Check HTTP сервер для API Watcher')
    parser.add_argument('--host', default='0.0.0.0', help='Хост для привязки сервера')
    parser.add_argument('--port', type=int, default=8080, help='Порт для привязки сервера')
    parser.add_argument('--log-level', default='INFO', help='Уровень логирования')
    
    args = parser.parse_args()
    
    # Настройка логирования
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    try:
        # Создаем и запускаем сервер
        server = HTTPServer((args.host, args.port), HealthHandler)
        logging.info(f"Health check сервер запущен на http://{args.host}:{args.port}")
        logging.info("Доступные endpoints:")
        logging.info(f"  http://{args.host}:{args.port}/health - Health check")
        logging.info(f"  http://{args.host}:{args.port}/ - Информация о сервисе")
        
        server.serve_forever()
        
    except KeyboardInterrupt:
        logging.info("Получен сигнал прерывания, завершение работы...")
        server.shutdown()
        sys.exit(0)
    except Exception as e:
        logging.error(f"Ошибка запуска сервера: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()