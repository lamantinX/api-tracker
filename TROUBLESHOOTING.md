# Устранение проблем API Watcher Service

## Проблема: api-watcher.service падает с exit-code 1

### Быстрая диагностика

1. **Скопируйте файлы диагностики на сервер:**
```bash
# Скопируйте эти файлы в /opt/api-tracker/:
# - debug_service.sh
# - quick_debug.sh  
# - fix_service.sh
# - test_watcher.py
# - deployment/api-watcher-fixed.service
```

2. **Запустите быструю диагностику:**
```bash
cd /opt/api-tracker
chmod +x quick_debug.sh
sudo bash quick_debug.sh
```

3. **Запустите полную диагностику:**
```bash
chmod +x debug_service.sh
sudo bash debug_service.sh
```

### Автоматическое исправление

```bash
cd /opt/api-tracker
chmod +x fix_service.sh
sudo bash fix_service.sh
```

### Ручное исправление

#### 1. Проверьте пользователя и права

```bash
# Создайте пользователя apiwatcher
sudo useradd -r -s /bin/false apiwatcher

# Установите права
sudo chown -R apiwatcher:apiwatcher /opt/api-tracker
sudo mkdir -p /var/log/api-watcher
sudo chown -R apiwatcher:apiwatcher /var/log/api-watcher
```

#### 2. Проверьте виртуальное окружение

```bash
cd /opt/api-tracker

# Если venv не существует, создайте его
python3 -m venv venv
source venv/bin/activate
pip install -r api_watcher/requirements.txt
```

#### 3. Проверьте зависимости Python

```bash
cd /opt/api-tracker
python test_watcher.py
```

#### 4. Проверьте конфигурацию

```bash
# Убедитесь, что файлы существуют
ls -la /opt/api-tracker/.env
ls -la /opt/api-tracker/urls.json
ls -la /opt/api-tracker/api_watcher/watcher.py
```

#### 5. Тестовый запуск

```bash
cd /opt/api-tracker
export PYTHONPATH=/opt/api-tracker
export API_WATCHER_URLS_FILE=/opt/api-tracker/urls.json

# Тест от пользователя apiwatcher
sudo -u apiwatcher /opt/api-tracker/venv/bin/python -u /opt/api-tracker/api_watcher/watcher.py
```

#### 6. Обновите systemd сервис

```bash
# Скопируйте исправленный сервис
sudo cp /opt/api-tracker/deployment/api-watcher-fixed.service /etc/systemd/system/api-watcher.service

# Перезагрузите systemd
sudo systemctl daemon-reload

# Запустите сервис
sudo systemctl start api-watcher.service

# Проверьте статус
sudo systemctl status api-watcher.service
```

### Просмотр логов

```bash
# Логи systemd
sudo journalctl -u api-watcher.service -f

# Логи приложения
sudo tail -f /var/log/api-watcher/watcher.log
sudo tail -f /var/log/api-watcher/watcher.error.log
```

### Частые проблемы и решения

#### 1. ModuleNotFoundError
```bash
# Убедитесь, что PYTHONPATH установлен
export PYTHONPATH=/opt/api-tracker

# Проверьте установку зависимостей
cd /opt/api-tracker
source venv/bin/activate
pip install -r api_watcher/requirements.txt
```

#### 2. Permission denied
```bash
# Проверьте права доступа
sudo chown -R apiwatcher:apiwatcher /opt/api-tracker
sudo chmod +x /opt/api-tracker/api_watcher/watcher.py
```

#### 3. Database connection error
```bash
# Проверьте права на файл БД
sudo chown apiwatcher:apiwatcher /opt/api-tracker/api_watcher.db
```

#### 4. File not found errors
```bash
# Убедитесь, что все файлы на месте
ls -la /opt/api-tracker/urls.json
ls -la /opt/api-tracker/.env
ls -la /opt/api-tracker/api_watcher/watcher.py
```

### Проверка после исправления

```bash
# Запустите тесты
cd /opt/api-tracker
python test_watcher.py

# Запустите сервис
sudo systemctl start api-watcher.service

# Проверьте статус
sudo systemctl status api-watcher.service

# Включите автозапуск
sudo systemctl enable api-watcher.service
```

### Если проблема не решена

1. Запустите полную диагностику: `sudo bash debug_service.sh`
2. Проверьте логи: `sudo journalctl -u api-watcher.service -n 50`
3. Запустите тестовый скрипт: `python test_watcher.py`
4. Проверьте версии Python и зависимостей

### Контакты для поддержки

Если проблема не решается, предоставьте:
- Вывод `sudo bash debug_service.sh`
- Вывод `python test_watcher.py`  
- Логи `sudo journalctl -u api-watcher.service -n 100`