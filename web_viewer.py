#!/usr/bin/env python3
"""
Веб-интерфейс для просмотра снэпшотов и логов API Watcher
Запускается на http://localhost:8080
"""

import sys
import os
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import html

# Добавляем путь к проекту
sys.path.insert(0, '/opt/api-tracker')

class APIWatcherWebHandler(BaseHTTPRequestHandler):
    """HTTP обработчик для веб-интерфейса"""
    
    def do_GET(self):
        """Обработка GET запросов"""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        query = parse_qs(parsed_path.query)
        
        if path == '/':
            self.serve_dashboard()
        elif path == '/api/snapshots':
            self.serve_snapshots_api(query)
        elif path == '/api/logs':
            self.serve_logs_api(query)
        elif path == '/api/snapshot-details':
            self.serve_snapshot_details(query)
        elif path == '/static/style.css':
            self.serve_css()
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
    <title>API Watcher - Просмотр снэпшотов</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <div class="container">
        <header>
            <h1>🔍 API Watcher Dashboard</h1>
            <div class="stats" id="stats">Загрузка...</div>
        </header>
        
        <nav class="tabs">
            <button class="tab-btn active" onclick="showTab('snapshots')">📸 Снэпшоты</button>
            <button class="tab-btn" onclick="showTab('logs')">📋 Логи</button>
            <button class="tab-btn" onclick="showTab('changes')">🔄 Изменения</button>
        </nav>
        
        <main>
            <!-- Вкладка снэпшотов -->
            <div id="snapshots-tab" class="tab-content active">
                <div class="controls">
                    <input type="text" id="url-filter" placeholder="Фильтр по URL..." onkeyup="filterSnapshots()">
                    <button onclick="refreshSnapshots()">🔄 Обновить</button>
                </div>
                <div id="snapshots-list">Загрузка снэпшотов...</div>
            </div>
            
            <!-- Вкладка логов -->
            <div id="logs-tab" class="tab-content">
                <div class="controls">
                    <select id="log-level" onchange="refreshLogs()">
                        <option value="">Все уровни</option>
                        <option value="ERROR">Только ошибки</option>
                        <option value="WARNING">Предупреждения</option>
                        <option value="INFO">Информация</option>
                    </select>
                    <input type="number" id="log-lines" value="50" min="10" max="1000" onchange="refreshLogs()">
                    <button onclick="refreshLogs()">🔄 Обновить</button>
                </div>
                <div id="logs-list">Загрузка логов...</div>
            </div>
            
            <!-- Вкладка изменений -->
            <div id="changes-tab" class="tab-content">
                <div class="controls">
                    <select id="changes-period" onchange="refreshChanges()">
                        <option value="1">За день</option>
                        <option value="7" selected>За неделю</option>
                        <option value="30">За месяц</option>
                    </select>
                    <button onclick="refreshChanges()">🔄 Обновить</button>
                </div>
                <div id="changes-list">Загрузка изменений...</div>
            </div>
        </main>
    </div>
    
    <!-- Модальное окно для деталей -->
    <div id="modal" class="modal" onclick="closeModal()">
        <div class="modal-content" onclick="event.stopPropagation()">
            <span class="close" onclick="closeModal()">&times;</span>
            <div id="modal-body">Загрузка...</div>
        </div>
    </div>
    
    <script>
        // Переключение вкладок
        function showTab(tabName) {
            document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            
            document.getElementById(tabName + '-tab').classList.add('active');
            event.target.classList.add('active');
            
            if (tabName === 'snapshots') refreshSnapshots();
            else if (tabName === 'logs') refreshLogs();
            else if (tabName === 'changes') refreshChanges();
        }
        
        // Загрузка снэпшотов
        async function refreshSnapshots() {
            const response = await fetch('/api/snapshots');
            const data = await response.json();
            
            let html = '<div class="snapshots-grid">';
            
            data.snapshots.forEach(snapshot => {
                const hasChanges = snapshot.has_changes ? 'has-changes' : '';
                html += `
                    <div class="snapshot-card ${hasChanges}" onclick="showSnapshotDetails(${snapshot.id})">
                        <div class="snapshot-header">
                            <h3>${snapshot.api_name || 'Без названия'}</h3>
                            <span class="snapshot-date">${new Date(snapshot.created_at).toLocaleString('ru')}</span>
                        </div>
                        <div class="snapshot-url">${snapshot.url}</div>
                        <div class="snapshot-method">${snapshot.method_name || 'Не указан'}</div>
                        <div class="snapshot-status">
                            ${snapshot.has_changes ? '🔄 Есть изменения' : '✅ Без изменений'}
                        </div>
                        ${snapshot.ai_summary ? `<div class="ai-summary">${snapshot.ai_summary.substring(0, 100)}...</div>` : ''}
                    </div>
                `;
            });
            
            html += '</div>';
            document.getElementById('snapshots-list').innerHTML = html;
            
            // Обновляем статистику
            document.getElementById('stats').innerHTML = `
                📊 Всего URL: ${data.total_urls} | 
                📸 Снэпшотов: ${data.total_snapshots} | 
                🔄 С изменениями: ${data.snapshots_with_changes}
            `;
        }
        
        // Загрузка логов
        async function refreshLogs() {
            const level = document.getElementById('log-level').value;
            const lines = document.getElementById('log-lines').value;
            
            const response = await fetch(`/api/logs?level=${level}&lines=${lines}`);
            const data = await response.json();
            
            let html = '<div class="logs-list">';
            
            data.logs.forEach(log => {
                const levelClass = log.level ? log.level.toLowerCase() : 'info';
                const icon = {
                    'error': '❌',
                    'warning': '⚠️',
                    'info': '✅',
                    'debug': '🔍'
                }[levelClass] || '📝';
                
                html += `
                    <div class="log-entry ${levelClass}">
                        <div class="log-header">
                            <span class="log-icon">${icon}</span>
                            <span class="log-level">${log.level || 'INFO'}</span>
                            <span class="log-time">${log.timestamp || log.time || 'Unknown'}</span>
                        </div>
                        <div class="log-message">${log.message || log.msg || log.raw || ''}</div>
                    </div>
                `;
            });
            
            html += '</div>';
            document.getElementById('logs-list').innerHTML = html;
        }
        
        // Загрузка изменений
        async function refreshChanges() {
            const period = document.getElementById('changes-period').value;
            
            const response = await fetch(`/api/snapshots?changes_only=true&days=${period}`);
            const data = await response.json();
            
            let html = '<div class="changes-list">';
            
            if (data.snapshots.length === 0) {
                html += '<div class="no-changes">Изменений не найдено за выбранный период</div>';
            } else {
                data.snapshots.forEach(snapshot => {
                    html += `
                        <div class="change-card" onclick="showSnapshotDetails(${snapshot.id})">
                            <div class="change-header">
                                <h3>${snapshot.api_name || 'Без названия'}</h3>
                                <span class="change-date">${new Date(snapshot.created_at).toLocaleString('ru')}</span>
                            </div>
                            <div class="change-url">${snapshot.url}</div>
                            ${snapshot.ai_summary ? `<div class="ai-summary">${snapshot.ai_summary}</div>` : ''}
                        </div>
                    `;
                });
            }
            
            html += '</div>';
            document.getElementById('changes-list').innerHTML = html;
        }
        
        // Показать детали снэпшота
        async function showSnapshotDetails(snapshotId) {
            document.getElementById('modal').style.display = 'block';
            document.getElementById('modal-body').innerHTML = 'Загрузка...';
            
            const response = await fetch(`/api/snapshot-details?id=${snapshotId}`);
            const data = await response.json();
            
            let html = `
                <h2>Детали снэпшота #${data.id}</h2>
                <div class="detail-grid">
                    <div><strong>URL:</strong> <a href="${data.url}" target="_blank">${data.url}</a></div>
                    <div><strong>API:</strong> ${data.api_name || 'Не указано'}</div>
                    <div><strong>Метод:</strong> ${data.method_name || 'Не указан'}</div>
                    <div><strong>Тип:</strong> ${data.content_type}</div>
                    <div><strong>Дата:</strong> ${new Date(data.created_at).toLocaleString('ru')}</div>
                    <div><strong>Изменения:</strong> ${data.has_changes ? 'Да' : 'Нет'}</div>
                    <div><strong>Хеш:</strong> ${data.content_hash}</div>
                </div>
            `;
            
            if (data.ai_summary) {
                html += `<div class="ai-summary-full"><h3>AI Анализ изменений:</h3><p>${data.ai_summary}</p></div>`;
            }
            
            if (data.text_content) {
                html += `
                    <div class="content-section">
                        <h3>Текстовое содержимое (${data.text_content.length} символов):</h3>
                        <pre class="content-preview">${data.text_content.substring(0, 2000)}${data.text_content.length > 2000 ? '...' : ''}</pre>
                    </div>
                `;
            }
            
            document.getElementById('modal-body').innerHTML = html;
        }
        
        // Закрыть модальное окно
        function closeModal() {
            document.getElementById('modal').style.display = 'none';
        }
        
        // Фильтрация снэпшотов
        function filterSnapshots() {
            const filter = document.getElementById('url-filter').value.toLowerCase();
            const cards = document.querySelectorAll('.snapshot-card');
            
            cards.forEach(card => {
                const url = card.querySelector('.snapshot-url').textContent.toLowerCase();
                const api = card.querySelector('.snapshot-header h3').textContent.toLowerCase();
                
                if (url.includes(filter) || api.includes(filter)) {
                    card.style.display = 'block';
                } else {
                    card.style.display = 'none';
                }
            });
        }
        
        // Автообновление каждые 30 секунд
        setInterval(() => {
            const activeTab = document.querySelector('.tab-content.active').id;
            if (activeTab === 'snapshots-tab') refreshSnapshots();
            else if (activeTab === 'logs-tab') refreshLogs();
            else if (activeTab === 'changes-tab') refreshChanges();
        }, 30000);
        
        // Загружаем данные при старте
        refreshSnapshots();
    </script>
</body>
</html>
        """
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html_content.encode('utf-8'))
    
    def serve_css(self):
        """CSS стили"""
        css_content = """
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
            color: #333;
        }
        
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        
        header {
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        header h1 { color: #2c3e50; margin-bottom: 10px; }
        .stats { color: #666; font-size: 14px; }
        
        .tabs {
            display: flex;
            background: white;
            border-radius: 8px;
            margin-bottom: 20px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        .tab-btn {
            flex: 1;
            padding: 15px;
            border: none;
            background: white;
            cursor: pointer;
            transition: background 0.3s;
        }
        
        .tab-btn:hover { background: #f8f9fa; }
        .tab-btn.active { background: #3498db; color: white; }
        
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        
        .controls {
            background: white;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            display: flex;
            gap: 10px;
            align-items: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        .controls input, .controls select, .controls button {
            padding: 8px 12px;
            border: 1px solid #ddd;
            border-radius: 4px;
        }
        
        .controls button {
            background: #3498db;
            color: white;
            border: none;
            cursor: pointer;
        }
        
        .controls button:hover { background: #2980b9; }
        
        .snapshots-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 20px;
        }
        
        .snapshot-card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
            border-left: 4px solid #95a5a6;
        }
        
        .snapshot-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.15);
        }
        
        .snapshot-card.has-changes { border-left-color: #e74c3c; }
        
        .snapshot-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 10px;
        }
        
        .snapshot-header h3 {
            color: #2c3e50;
            font-size: 16px;
            margin-right: 10px;
        }
        
        .snapshot-date {
            font-size: 12px;
            color: #666;
            white-space: nowrap;
        }
        
        .snapshot-url {
            font-size: 12px;
            color: #3498db;
            margin-bottom: 8px;
            word-break: break-all;
        }
        
        .snapshot-method {
            font-size: 14px;
            color: #666;
            margin-bottom: 8px;
        }
        
        .snapshot-status {
            font-size: 12px;
            font-weight: bold;
        }
        
        .ai-summary {
            margin-top: 10px;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 4px;
            font-size: 12px;
            color: #555;
        }
        
        .logs-list { background: white; border-radius: 8px; padding: 20px; }
        
        .log-entry {
            padding: 10px;
            border-bottom: 1px solid #eee;
            font-family: 'Courier New', monospace;
            font-size: 12px;
        }
        
        .log-entry:last-child { border-bottom: none; }
        
        .log-header {
            display: flex;
            gap: 10px;
            align-items: center;
            margin-bottom: 5px;
        }
        
        .log-level {
            background: #ecf0f1;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 10px;
            font-weight: bold;
        }
        
        .log-entry.error .log-level { background: #e74c3c; color: white; }
        .log-entry.warning .log-level { background: #f39c12; color: white; }
        .log-entry.info .log-level { background: #27ae60; color: white; }
        .log-entry.debug .log-level { background: #95a5a6; color: white; }
        
        .log-time { color: #666; font-size: 10px; }
        .log-message { color: #333; }
        
        .changes-list { display: flex; flex-direction: column; gap: 15px; }
        
        .change-card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            cursor: pointer;
            border-left: 4px solid #e74c3c;
        }
        
        .change-card:hover { box-shadow: 0 4px 8px rgba(0,0,0,0.15); }
        
        .change-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        
        .change-url {
            font-size: 12px;
            color: #3498db;
            margin-bottom: 10px;
            word-break: break-all;
        }
        
        .no-changes {
            text-align: center;
            padding: 40px;
            color: #666;
            background: white;
            border-radius: 8px;
        }
        
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.5);
        }
        
        .modal-content {
            background-color: white;
            margin: 5% auto;
            padding: 20px;
            border-radius: 8px;
            width: 90%;
            max-width: 800px;
            max-height: 80vh;
            overflow-y: auto;
            position: relative;
        }
        
        .close {
            position: absolute;
            right: 20px;
            top: 15px;
            font-size: 28px;
            font-weight: bold;
            cursor: pointer;
            color: #aaa;
        }
        
        .close:hover { color: #000; }
        
        .detail-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 10px;
            margin: 20px 0;
        }
        
        .detail-grid div {
            padding: 10px;
            background: #f8f9fa;
            border-radius: 4px;
        }
        
        .ai-summary-full {
            margin: 20px 0;
            padding: 15px;
            background: #e8f5e8;
            border-radius: 8px;
            border-left: 4px solid #27ae60;
        }
        
        .content-section {
            margin: 20px 0;
        }
        
        .content-preview {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 4px;
            overflow-x: auto;
            font-size: 11px;
            line-height: 1.4;
            max-height: 300px;
            overflow-y: auto;
        }
        """
        
        self.send_response(200)
        self.send_header('Content-type', 'text/css')
        self.end_headers()
        self.wfile.write(css_content.encode('utf-8'))
    
    def serve_snapshots_api(self, query):
        """API для получения снэпшотов"""
        try:
            from api_watcher.config import Config
            from api_watcher.storage.database import DatabaseManager
            
            db = DatabaseManager(Config.DATABASE_URL)
            
            changes_only = query.get('changes_only', ['false'])[0].lower() == 'true'
            days = int(query.get('days', ['7'])[0])
            
            if changes_only:
                snapshots = db.get_snapshots_with_changes(days=days)
            else:
                # Получаем последние снэпшоты для каждого URL
                urls = db.get_all_urls()
                snapshots = []
                for url in urls:
                    latest = db.get_latest_snapshot(url)
                    if latest:
                        snapshots.append(latest)
                
                # Сортируем по дате
                snapshots.sort(key=lambda x: x.created_at, reverse=True)
            
            # Статистика
            total_urls = len(db.get_all_urls())
            total_snapshots = len(snapshots)
            snapshots_with_changes = len([s for s in snapshots if s.has_changes])
            
            # Преобразуем в JSON
            snapshots_data = []
            for snapshot in snapshots[:50]:  # Ограничиваем 50 записями
                snapshots_data.append({
                    'id': snapshot.id,
                    'url': snapshot.url,
                    'api_name': snapshot.api_name,
                    'method_name': snapshot.method_name,
                    'content_type': snapshot.content_type,
                    'created_at': snapshot.created_at.isoformat(),
                    'has_changes': snapshot.has_changes,
                    'ai_summary': snapshot.ai_summary,
                    'content_hash': snapshot.content_hash
                })
            
            response_data = {
                'snapshots': snapshots_data,
                'total_urls': total_urls,
                'total_snapshots': total_snapshots,
                'snapshots_with_changes': snapshots_with_changes
            }
            
            db.close()
            
            self.send_json_response(response_data)
            
        except Exception as e:
            self.send_json_response({'error': str(e)}, status=500)
    
    def serve_logs_api(self, query):
        """API для получения логов"""
        try:
            level_filter = query.get('level', [''])[0]
            lines_count = int(query.get('lines', ['50'])[0])
            
            logs = []
            
            # Пытаемся читать из разных источников логов
            log_files = [
                '/var/log/api-watcher/watcher.log',
                '/opt/api-tracker/api_watcher.log',
                'api_watcher.log'
            ]
            
            for log_file in log_files:
                if os.path.exists(log_file):
                    try:
                        with open(log_file, 'r', encoding='utf-8') as f:
                            lines = f.readlines()[-lines_count:]
                            
                        for line in lines:
                            line = line.strip()
                            if not line:
                                continue
                            
                            try:
                                # Пытаемся парсить как JSON
                                log_entry = json.loads(line)
                                
                                # Фильтруем по уровню
                                if level_filter:
                                    entry_level = log_entry.get('level', '').upper()
                                    if entry_level != level_filter.upper():
                                        continue
                                
                                logs.append(log_entry)
                                
                            except json.JSONDecodeError:
                                # Если не JSON, добавляем как текст
                                if not level_filter:
                                    logs.append({
                                        'raw': line,
                                        'level': 'INFO',
                                        'timestamp': datetime.now().isoformat()
                                    })
                        
                        break  # Используем первый найденный файл
                        
                    except Exception as e:
                        continue
            
            self.send_json_response({'logs': logs[-lines_count:]})
            
        except Exception as e:
            self.send_json_response({'error': str(e)}, status=500)
    
    def serve_snapshot_details(self, query):
        """API для получения деталей снэпшота"""
        try:
            snapshot_id = int(query.get('id', ['0'])[0])
            
            from api_watcher.config import Config
            from api_watcher.storage.database import DatabaseManager
            
            db = DatabaseManager(Config.DATABASE_URL)
            
            # Получаем снэпшот по ID
            snapshot = db.session.query(db.session.query(db.session.bind.execute(
                "SELECT * FROM snapshots WHERE id = ?", (snapshot_id,)
            )).fetchone())
            
            # Простой способ получения снэпшота
            conn = sqlite3.connect(Config.DATABASE_URL.replace('sqlite:///', ''))
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM snapshots WHERE id = ?", (snapshot_id,))
            row = cursor.fetchone()
            
            if not row:
                self.send_json_response({'error': 'Snapshot not found'}, status=404)
                return
            
            # Получаем названия колонок
            cursor.execute("PRAGMA table_info(snapshots)")
            columns = [col[1] for col in cursor.fetchall()]
            
            # Создаем словарь
            snapshot_data = dict(zip(columns, row))
            
            conn.close()
            
            self.send_json_response(snapshot_data)
            
        except Exception as e:
            self.send_json_response({'error': str(e)}, status=500)
    
    def send_json_response(self, data, status=200):
        """Отправка JSON ответа"""
        self.send_response(status)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.end_headers()
        
        json_data = json.dumps(data, ensure_ascii=False, indent=2)
        self.wfile.write(json_data.encode('utf-8'))

def main():
    """Запуск веб-сервера"""
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    
    print(f"=== API Watcher Web Viewer ===")
    print(f"Запуск веб-сервера на порту {port}")
    print(f"Откройте в браузере: http://localhost:{port}")
    print("Для остановки нажмите Ctrl+C")
    
    try:
        server = HTTPServer(('', port), APIWatcherWebHandler)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nСервер остановлен")

if __name__ == '__main__':
    main()