#!/usr/bin/env python3
"""
Простой веб-интерфейс для просмотра снепшотов API Watcher
Запускается на http://localhost:8080
"""

import sqlite3
import json
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import html

class SimpleWebHandler(BaseHTTPRequestHandler):
    """Простой HTTP обработчик"""
    
    def do_GET(self):
        """Обработка GET запросов"""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        query = parse_qs(parsed_path.query)
        
        if path == '/':
            self.serve_dashboard()
        elif path == '/api/snapshots':
            self.serve_snapshots_api(query)
        elif path == '/api/snapshot':
            self.serve_snapshot_details(query)
        else:
            self.send_error(404)
    
    def serve_dashboard(self):
        """Главная страница"""
        html_content = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>API Watcher - Просмотр снепшотов</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1 { color: #333; text-align: center; }
        .stats { background: #e3f2fd; padding: 15px; border-radius: 5px; margin: 20px 0; text-align: center; }
        .controls { margin: 20px 0; }
        .controls input, .controls select, .controls button { margin: 5px; padding: 8px; }
        .snapshot-card { border: 1px solid #ddd; margin: 10px 0; padding: 15px; border-radius: 5px; cursor: pointer; }
        .snapshot-card:hover { background: #f9f9f9; }
        .snapshot-card.has-changes { border-left: 4px solid #ff9800; }
        .snapshot-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
        .snapshot-url { color: #666; font-size: 0.9em; margin: 5px 0; word-break: break-all; }
        .snapshot-status { font-weight: bold; }
        .has-changes .snapshot-status { color: #ff9800; }
        .ai-summary { background: #f0f0f0; padding: 8px; border-radius: 3px; margin-top: 10px; font-size: 0.9em; }
        .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); }
        .modal-content { background: white; margin: 5% auto; padding: 20px; width: 80%; max-width: 800px; border-radius: 8px; max-height: 80vh; overflow-y: auto; }
        .close { float: right; font-size: 28px; font-weight: bold; cursor: pointer; }
        .close:hover { color: red; }
        .loading { text-align: center; padding: 20px; color: #666; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 API Watcher Dashboard</h1>
        <div class="stats" id="stats">Загрузка статистики...</div>
        
        <div class="controls">
            <input type="text" id="search" placeholder="Поиск по URL или API..." onkeyup="filterSnapshots()">
            <select id="filter-changes" onchange="filterSnapshots()">
                <option value="">Все снепшоты</option>
                <option value="true">Только с изменениями</option>
                <option value="false">Без изменений</option>
            </select>
            <button onclick="loadSnapshots()">🔄 Обновить</button>
        </div>
        
        <div id="snapshots-container">
            <div class="loading">Загрузка снепшотов...</div>
        </div>
    </div>
    
    <!-- Модальное окно -->
    <div id="modal" class="modal" onclick="closeModal()">
        <div class="modal-content" onclick="event.stopPropagation()">
            <span class="close" onclick="closeModal()">&times;</span>
            <div id="modal-body">Загрузка...</div>
        </div>
    </div>
    
    <script>
        let allSnapshots = [];
        
        // Загрузка снепшотов
        async function loadSnapshots() {
            try {
                const response = await fetch('/api/snapshots');
                const data = await response.json();
                allSnapshots = data.snapshots || [];
                
                // Обновляем статистику
                document.getElementById('stats').innerHTML = `
                    📊 Всего URL: ${data.total_urls || 0} | 
                    📸 Снепшотов: ${data.total_snapshots || 0} | 
                    🔄 С изменениями: ${data.snapshots_with_changes || 0}
                `;
                
                displaySnapshots(allSnapshots);
            } catch (error) {
                document.getElementById('snapshots-container').innerHTML = 
                    '<div class="loading">❌ Ошибка загрузки: ' + error.message + '</div>';
            }
        }
        
        // Отображение снепшотов
        function displaySnapshots(snapshots) {
            const container = document.getElementById('snapshots-container');
            
            if (!snapshots || snapshots.length === 0) {
                container.innerHTML = '<div class="loading">📭 Снепшоты не найдены</div>';
                return;
            }
            
            let html = '';
            snapshots.forEach(snapshot => {
                const hasChanges = snapshot.has_changes ? 'has-changes' : '';
                const date = new Date(snapshot.created_at).toLocaleString('ru');
                
                html += `
                    <div class="snapshot-card ${hasChanges}" onclick="showSnapshotDetails(${snapshot.id})">
                        <div class="snapshot-header">
                            <h3>${snapshot.api_name || 'Без названия'}</h3>
                            <span>${date}</span>
                        </div>
                        <div class="snapshot-url">${snapshot.url}</div>
                        <div>Метод: ${snapshot.method_name || 'Не указан'}</div>
                        <div class="snapshot-status">
                            ${snapshot.has_changes ? '🔄 Есть изменения' : '✅ Без изменений'}
                        </div>
                        ${snapshot.ai_summary ? `<div class="ai-summary">${snapshot.ai_summary.substring(0, 200)}...</div>` : ''}
                    </div>
                `;
            });
            
            container.innerHTML = html;
        }
        
        // Фильтрация снепшотов
        function filterSnapshots() {
            const search = document.getElementById('search').value.toLowerCase();
            const changesFilter = document.getElementById('filter-changes').value;
            
            let filtered = allSnapshots.filter(snapshot => {
                // Фильтр по тексту
                const matchesSearch = !search || 
                    (snapshot.url && snapshot.url.toLowerCase().includes(search)) ||
                    (snapshot.api_name && snapshot.api_name.toLowerCase().includes(search)) ||
                    (snapshot.method_name && snapshot.method_name.toLowerCase().includes(search));
                
                // Фильтр по изменениям
                const matchesChanges = !changesFilter || 
                    (changesFilter === 'true' && snapshot.has_changes) ||
                    (changesFilter === 'false' && !snapshot.has_changes);
                
                return matchesSearch && matchesChanges;
            });
            
            displaySnapshots(filtered);
        }
        
        // Показать детали снепшота
        async function showSnapshotDetails(id) {
            document.getElementById('modal').style.display = 'block';
            document.getElementById('modal-body').innerHTML = '<div class="loading">Загрузка деталей...</div>';
            
            try {
                const response = await fetch(`/api/snapshot?id=${id}`);
                const data = await response.json();
                
                let html = `
                    <h2>${data.api_name || 'Снепшот'}</h2>
                    <p><strong>URL:</strong> <a href="${data.url}" target="_blank">${data.url}</a></p>
                    <p><strong>Дата:</strong> ${new Date(data.created_at).toLocaleString('ru')}</p>
                    <p><strong>Тип контента:</strong> ${data.content_type || 'Не указан'}</p>
                    <p><strong>Изменения:</strong> ${data.has_changes ? '🔄 Да' : '✅ Нет'}</p>
                `;
                
                if (data.ai_summary) {
                    html += `<h3>AI Анализ изменений:</h3><div class="ai-summary">${data.ai_summary}</div>`;
                }
                
                if (data.text_content) {
                    const preview = data.text_content.substring(0, 1000);
                    html += `<h3>Содержимое (первые 1000 символов):</h3><pre style="background: #f5f5f5; padding: 10px; border-radius: 3px; overflow-x: auto;">${preview}${data.text_content.length > 1000 ? '...' : ''}</pre>`;
                }
                
                document.getElementById('modal-body').innerHTML = html;
            } catch (error) {
                document.getElementById('modal-body').innerHTML = '<div class="loading">❌ Ошибка загрузки деталей: ' + error.message + '</div>';
            }
        }
        
        // Закрыть модальное окно
        function closeModal() {
            document.getElementById('modal').style.display = 'none';
        }
        
        // Загружаем данные при старте
        loadSnapshots();
    </script>
</body>
</html>
        """
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html_content.encode('utf-8'))
    
    def serve_snapshots_api(self, query):
        """API для получения снепшотов"""
        try:
            conn = sqlite3.connect('api_watcher.db')
            cursor = conn.cursor()
            
            # Статистика
            cursor.execute("SELECT COUNT(*) FROM snapshots")
            total_snapshots = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(DISTINCT url) FROM snapshots")
            total_urls = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM snapshots WHERE has_changes = 1")
            snapshots_with_changes = cursor.fetchone()[0]
            
            # Последние снепшоты
            limit = int(query.get('limit', ['50'])[0])
            cursor.execute("""
                SELECT id, url, api_name, method_name, content_type, created_at, has_changes, ai_summary
                FROM snapshots 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (limit,))
            
            snapshots = []
            for row in cursor.fetchall():
                snapshots.append({
                    'id': row[0],
                    'url': row[1],
                    'api_name': row[2],
                    'method_name': row[3],
                    'content_type': row[4],
                    'created_at': row[5],
                    'has_changes': bool(row[6]),
                    'ai_summary': row[7]
                })
            
            response_data = {
                'total_snapshots': total_snapshots,
                'total_urls': total_urls,
                'snapshots_with_changes': snapshots_with_changes,
                'snapshots': snapshots
            }
            
            conn.close()
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps(response_data, ensure_ascii=False).encode('utf-8'))
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            error_response = {'error': str(e)}
            self.wfile.write(json.dumps(error_response, ensure_ascii=False).encode('utf-8'))
    
    def serve_snapshot_details(self, query):
        """API для получения деталей снепшота"""
        try:
            snapshot_id = query.get('id', [None])[0]
            if not snapshot_id:
                raise ValueError("ID снепшота не указан")
            
            conn = sqlite3.connect('api_watcher.db')
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, url, api_name, method_name, content_type, raw_html, text_content, 
                       created_at, has_changes, ai_summary, content_hash
                FROM snapshots 
                WHERE id = ?
            """, (snapshot_id,))
            
            row = cursor.fetchone()
            if not row:
                raise ValueError("Снепшот не найден")
            
            snapshot = {
                'id': row[0],
                'url': row[1],
                'api_name': row[2],
                'method_name': row[3],
                'content_type': row[4],
                'raw_html': row[5],
                'text_content': row[6],
                'created_at': row[7],
                'has_changes': bool(row[8]),
                'ai_summary': row[9],
                'content_hash': row[10]
            }
            
            conn.close()
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps(snapshot, ensure_ascii=False).encode('utf-8'))
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            error_response = {'error': str(e)}
            self.wfile.write(json.dumps(error_response, ensure_ascii=False).encode('utf-8'))

def main():
    """Запуск веб-сервера"""
    port = 8080
    server_address = ('', port)
    
    print(f"🌐 Запуск веб-интерфейса API Watcher...")
    print(f"📍 Адрес: http://localhost:{port}")
    print(f"🔍 База данных: api_watcher.db")
    print(f"⏹️  Для остановки нажмите Ctrl+C")
    
    try:
        httpd = HTTPServer(server_address, SimpleWebHandler)
        httpd.serve_forever()
    except KeyboardInterrupt:
        print(f"\n🛑 Сервер остановлен")
        httpd.server_close()

if __name__ == '__main__':
    main()