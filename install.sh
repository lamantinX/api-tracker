#!/bin/bash
"""
Скрипт установки API Watcher для production окружения
"""

set -e

# Настройки
INSTALL_DIR="/opt/api-watcher"
SERVICE_USER="api-watcher"
SERVICE_GROUP="api-watcher"
PYTHON_VERSION="3.11"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Функции логирования
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Проверка прав root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "Этот скрипт должен быть запущен с правами root"
        exit 1
    fi
}

# Проверка системы
check_system() {
    log_info "Проверка системы..."
    
    # Проверка ОС
    if [[ ! -f /etc/os-release ]]; then
        log_error "Неподдерживаемая операционная система"
        exit 1
    fi
    
    # Проверка Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 не установлен"
        exit 1
    fi
    
    # Проверка pip
    if ! command -v pip3 &> /dev/null; then
        log_error "pip3 не установлен"
        exit 1
    fi
    
    log_info "Система проверена успешно"
}

# Создание пользователя
create_user() {
    log_info "Создание пользователя $SERVICE_USER..."
    
    if ! id "$SERVICE_USER" &>/dev/null; then
        useradd --system --shell /bin/false --home-dir "$INSTALL_DIR" --create-home "$SERVICE_USER"
        log_info "Пользователь $SERVICE_USER создан"
    else
        log_warn "Пользователь $SERVICE_USER уже существует"
    fi
}

# Установка зависимостей
install_dependencies() {
    log_info "Установка системных зависимостей..."
    
    # Определяем пакетный менеджер
    if command -v apt-get &> /dev/null; then
        apt-get update
        apt-get install -y python3-venv python3-pip curl
    elif command -v yum &> /dev/null; then
        yum install -y python3-venv python3-pip curl
    elif command -v dnf &> /dev/null; then
        dnf install -y python3-venv python3-pip curl
    else
        log_error "Неподдерживаемый пакетный менеджер"
        exit 1
    fi
    
    log_info "Системные зависимости установлены"
}

# Копирование файлов
copy_files() {
    log_info "Копирование файлов в $INSTALL_DIR..."
    
    # Создаем директории
    mkdir -p "$INSTALL_DIR"/{api_watcher,snapshots,logs}
    
    # Копируем файлы приложения
    cp -r api_watcher/* "$INSTALL_DIR/api_watcher/"
    cp urls.json "$INSTALL_DIR/"
    cp .env.example "$INSTALL_DIR/.env"
    
    # Устанавливаем права
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"
    chmod +x "$INSTALL_DIR/api_watcher/monitor.sh"
    
    log_info "Файлы скопированы"
}

# Создание виртуального окружения
setup_venv() {
    log_info "Создание виртуального окружения..."
    
    sudo -u "$SERVICE_USER" python3 -m venv "$INSTALL_DIR/venv"
    sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install --upgrade pip
    sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/api_watcher/requirements.txt"
    
    log_info "Виртуальное окружение создано"
}

# Установка systemd сервиса
install_service() {
    log_info "Установка systemd сервиса..."
    
    # Обновляем пути в сервис файле
    sed "s|/opt/api-watcher|$INSTALL_DIR|g" api_watcher.service > /etc/systemd/system/api-watcher.service
    
    # Перезагружаем systemd
    systemctl daemon-reload
    systemctl enable api-watcher.service
    
    log_info "Systemd сервис установлен"
}

# Настройка cron
setup_cron() {
    log_info "Настройка cron задач..."
    
    # Создаем crontab для пользователя
    cat > /tmp/api-watcher-cron << EOF
# API Watcher cron jobs
# Запуск каждые 30 минут
*/30 * * * * cd $INSTALL_DIR && ./api_watcher/monitor.sh run >> logs/cron.log 2>&1

# Проверка здоровья каждые 5 минут
*/5 * * * * cd $INSTALL_DIR && ./api_watcher/monitor.sh monitor >> logs/cron.log 2>&1

# Очистка логов каждый день в 2:00
0 2 * * * cd $INSTALL_DIR && ./api_watcher/monitor.sh cleanup >> logs/cron.log 2>&1
EOF
    
    # Устанавливаем crontab
    sudo -u "$SERVICE_USER" crontab /tmp/api-watcher-cron
    rm /tmp/api-watcher-cron
    
    log_info "Cron задачи настроены"
}

# Настройка logrotate
setup_logrotate() {
    log_info "Настройка ротации логов..."
    
    cat > /etc/logrotate.d/api-watcher << EOF
$INSTALL_DIR/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 $SERVICE_USER $SERVICE_GROUP
    postrotate
        systemctl reload api-watcher.service || true
    endscript
}
EOF
    
    log_info "Ротация логов настроена"
}

# Проверка установки
verify_installation() {
    log_info "Проверка установки..."
    
    # Проверяем файлы
    if [[ ! -f "$INSTALL_DIR/api_watcher/main.py" ]]; then
        log_error "Основные файлы не найдены"
        exit 1
    fi
    
    # Проверяем виртуальное окружение
    if [[ ! -f "$INSTALL_DIR/venv/bin/python" ]]; then
        log_error "Виртуальное окружение не создано"
        exit 1
    fi
    
    # Проверяем сервис
    if ! systemctl is-enabled api-watcher.service &>/dev/null; then
        log_error "Systemd сервис не активирован"
        exit 1
    fi
    
    # Тестовый запуск
    log_info "Выполнение тестового запуска..."
    sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/api_watcher/main.py" --health-check
    
    log_info "Установка проверена успешно"
}

# Показать информацию после установки
show_info() {
    log_info "Установка завершена успешно!"
    echo
    echo "Полезные команды:"
    echo "  Запуск сервиса:     sudo systemctl start api-watcher"
    echo "  Остановка сервиса:  sudo systemctl stop api-watcher"
    echo "  Статус сервиса:     sudo systemctl status api-watcher"
    echo "  Логи сервиса:       sudo journalctl -u api-watcher -f"
    echo "  Ручной запуск:      sudo -u $SERVICE_USER $INSTALL_DIR/venv/bin/python $INSTALL_DIR/api_watcher/main.py"
    echo "  Health check:       sudo -u $SERVICE_USER $INSTALL_DIR/api_watcher/health_check.py"
    echo "  Мониторинг:         sudo -u $SERVICE_USER $INSTALL_DIR/api_watcher/monitor.sh health"
    echo
    echo "Конфигурационные файлы:"
    echo "  URLs:               $INSTALL_DIR/urls.json"
    echo "  Environment:        $INSTALL_DIR/.env"
    echo "  Snapshots:          $INSTALL_DIR/snapshots/"
    echo "  Logs:               $INSTALL_DIR/logs/"
    echo
    echo "Следующие шаги:"
    echo "1. Отредактируйте $INSTALL_DIR/urls.json для добавления ваших URL"
    echo "2. Настройте Telegram уведомления в $INSTALL_DIR/.env (опционально)"
    echo "3. Запустите сервис: sudo systemctl start api-watcher"
}

# Основная функция
main() {
    log_info "Начало установки API Watcher..."
    
    check_root
    check_system
    create_user
    install_dependencies
    copy_files
    setup_venv
    install_service
    setup_cron
    setup_logrotate
    verify_installation
    show_info
}

# Обработка аргументов
case "${1:-install}" in
    "install")
        main
        ;;
    "uninstall")
        log_info "Удаление API Watcher..."
        systemctl stop api-watcher.service || true
        systemctl disable api-watcher.service || true
        rm -f /etc/systemd/system/api-watcher.service
        rm -f /etc/logrotate.d/api-watcher
        sudo -u "$SERVICE_USER" crontab -r || true
        userdel "$SERVICE_USER" || true
        rm -rf "$INSTALL_DIR"
        systemctl daemon-reload
        log_info "API Watcher удален"
        ;;
    *)
        echo "Использование: $0 [install|uninstall]"
        exit 1
        ;;
esac