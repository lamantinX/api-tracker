# 📊 Руководство по просмотру снэпшотов и логов API Watcher

## 🗂️ Где хранятся данные

### Снэпшоты
- **База данных**: `/opt/api-tracker/api_watcher.db` (SQLite)
- **Файлы**: `/opt/api-tracker/snapshots/` (JSON файлы, устаревший формат)
- **Конфигурация**: `SNAPSHOTS_DIR` в `.env` (по умолчанию `snapshots`)

### Логи
- **Системные логи**: `/var/log/api-watcher/`
  - `watcher.log` - основные логи
  - `watcher.error.log` - ошибки
- **Логи приложения**: `/opt/api-tracker/api_watcher.log`
- **Systemd журнал**: `journalctl -u api-watcher.service`

## 🖥️ Способы просмотра

### 1. Веб-интерфейс (Рекомендуется)

```bash
# На сервере
cd /opt/api-tracker
python web_viewer.py 8080

# Откройте в браузере на ПК
http://YOUR_SERVER_IP:8080
```

**Возможности:**
- 📸 Просмотр всех снэпшотов с фильтрацией
- 🔄 Отслеживание изменений в реальном времени
- 📋 Просмотр логов с фильтрацией по уровням
- 🔍 Детальный просмотр каждого снэпшота
- 📊 Статистика и аналитика

### 2. Командная строка - Снэпшоты

```bash
cd /opt/api-tracker

# Просмотр всех снэпшотов
python view_snapshots.py

# Только база данных
python view_snapshots.py db

# Только файлы
python view_snapshots.py files

# Детали изменений
python view_snapshots.py details

# Детали для конкретного URL
python view_snapshots.py details "https://api.example.com"
```

### 3. Командная строка - Логи

```bash
cd /opt/api-tracker

# Общий обзор логов
python view_logs.py

# Отслеживание в реальном времени
python view_logs.py follow

# Только systemd логи
python view_logs.py systemd 100

# Только файловые логи
python view_logs.py files 50

# Структурированные JSON логи
python view_logs.py json

# Только ошибки
python view_logs.py errors

# Поиск в логах
python view_logs.py search "error"

# Статистика файлов
python view_logs.py stats
```

### 4. Прямой доступ к базе данных

```bash
# SQLite командная строка
sqlite3 /opt/api-tracker/api_watcher.db

# Основные запросы
.tables
SELECT COUNT(*) FROM snapshots;
SELECT url, api_name, created_at FROM snapshots WHERE has_changes = 1 ORDER BY created_at DESC LIMIT 10;
SELECT DISTINCT url FROM snapshots;
```

### 5. Системные команды

```bash
# Логи systemd
sudo journalctl -u api-watcher.service -f
sudo journalctl -u api-watcher.service -n 100

# Файловые логи
sudo tail -f /var/log/api-watcher/watcher.log
sudo tail -f /var/log/api-watcher/watcher.error.log

# Поиск в логах
sudo grep -i "error" /var/log/api-watcher/*.log
sudo grep -A 5 -B 5 "exception" /var/log/api-watcher/*.log
```

## 📱 Удаленный доступ с ПК

### Через SSH туннель (Безопасно)

```bash
# На ПК создайте SSH туннель
ssh -L 8080:localhost:8080 user@your-server.com

# На сервере запустите веб-интерфейс
python web_viewer.py 8080

# Откройте на ПК: http://localhost:8080
```

### Через VPN или прямое подключение

```bash
# На сервере откройте порт в файрволе
sudo ufw allow 8080

# Запустите веб-интерфейс
python web_viewer.py 8080

# Откройте на ПК: http://SERVER_IP:8080
```

### Копирование файлов на ПК

```bash
# Скачать базу данных
scp user@server:/opt/api-tracker/api_watcher.db ./

# Скачать логи
scp user@server:/var/log/api-watcher/*.log ./

# Скачать снэпшоты
scp -r user@server:/opt/api-tracker/snapshots ./
```

## 🔍 Структура данных

### Снэпшот в базе данных
```sql
CREATE TABLE snapshots (
    id INTEGER PRIMARY KEY,
    url VARCHAR(500),
    api_name VARCHAR(200),
    method_name VARCHAR(200),
    content_type VARCHAR(50),
    raw_html TEXT,
    text_content TEXT,
    structured_data TEXT,
    created_at DATETIME,
    has_changes BOOLEAN,
    ai_summary TEXT,
    content_hash VARCHAR(64)
);
```

### Формат JSON лога
```json
{
    "timestamp": "2025-12-27T10:30:00.123456",
    "level": "INFO",
    "logger": "api_watcher.watcher",
    "message": "Processing URL: https://api.example.com",
    "app": "api_watcher",
    "url": "https://api.example.com",
    "api_name": "Example API"
}
```

## 🛠️ Полезные команды

### Очистка старых данных
```bash
# Удалить снэпшоты старше 30 дней
sqlite3 /opt/api-tracker/api_watcher.db "DELETE FROM snapshots WHERE created_at < datetime('now', '-30 days');"

# Очистить логи старше недели
sudo find /var/log/api-watcher/ -name "*.log" -mtime +7 -delete
```

### Экспорт данных
```bash
# Экспорт снэпшотов в CSV
sqlite3 -header -csv /opt/api-tracker/api_watcher.db "SELECT * FROM snapshots;" > snapshots.csv

# Экспорт изменений за неделю
sqlite3 -header -csv /opt/api-tracker/api_watcher.db "SELECT url, api_name, created_at, ai_summary FROM snapshots WHERE has_changes = 1 AND created_at > datetime('now', '-7 days');" > changes.csv
```

### Мониторинг размера данных
```bash
# Размер базы данных
ls -lh /opt/api-tracker/api_watcher.db

# Размер логов
du -sh /var/log/api-watcher/

# Количество записей
sqlite3 /opt/api-tracker/api_watcher.db "SELECT COUNT(*) as total_snapshots, COUNT(CASE WHEN has_changes = 1 THEN 1 END) as with_changes FROM snapshots;"
```

## 🚀 Быстрый старт

1. **Запустите веб-интерфейс:**
   ```bash
   cd /opt/api-tracker
   python web_viewer.py 8080
   ```

2. **Откройте в браузере:** `http://SERVER_IP:8080`

3. **Для безопасности используйте SSH туннель:**
   ```bash
   ssh -L 8080:localhost:8080 user@server
   ```

4. **Просматривайте данные через удобный веб-интерфейс!**