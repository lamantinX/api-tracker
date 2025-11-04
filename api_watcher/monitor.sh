#!/bin/bash
"""
Скрипт мониторинга для API Watcher
Может использоваться в cron для регулярных проверок
"""

# Настройки
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/../logs/monitor.log"
HEALTH_FILE="${SCRIPT_DIR}/health.json"
MAX_AGE_MINUTES=60
NOTIFICATION_WEBHOOK=""  # Webhook для уведомлений (Slack, Discord, etc.)

# Создаем директорию для логов если не существует
mkdir -p "$(dirname "$LOG_FILE")"

# Функция логирования
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Функция отправки уведомлений
send_notification() {
    local message="$1"
    local level="$2"  # info, warning, error
    
    log "$level: $message"
    
    # Отправляем webhook если настроен
    if [[ -n "$NOTIFICATION_WEBHOOK" ]]; then
        curl -s -X POST "$NOTIFICATION_WEBHOOK" \
            -H "Content-Type: application/json" \
            -d "{\"text\": \"API Watcher [$level]: $message\"}" \
            >> "$LOG_FILE" 2>&1
    fi
}

# Основная функция мониторинга
monitor() {
    log "Начало проверки здоровья API Watcher"
    
    # Проверяем health check
    if python3 "$SCRIPT_DIR/health_check.py" --health-file "$HEALTH_FILE" --max-age "$MAX_AGE_MINUTES" --quiet; then
        log "Health check прошел успешно"
        return 0
    else
        local exit_code=$?
        local health_data=""
        
        if [[ -f "$HEALTH_FILE" ]]; then
            health_data=$(cat "$HEALTH_FILE" 2>/dev/null)
        fi
        
        case $exit_code in
            1)
                send_notification "API Watcher не работает корректно. Health data: $health_data" "error"
                ;;
            *)
                send_notification "Неизвестная ошибка при проверке API Watcher (код: $exit_code)" "error"
                ;;
        esac
        
        return $exit_code
    fi
}

# Функция запуска API Watcher
run_watcher() {
    log "Запуск API Watcher"
    
    cd "$SCRIPT_DIR/.."
    
    if python3 "$SCRIPT_DIR/main.py" >> "$LOG_FILE" 2>&1; then
        log "API Watcher выполнен успешно"
        send_notification "API Watcher выполнен успешно" "info"
        return 0
    else
        local exit_code=$?
        send_notification "API Watcher завершился с ошибкой (код: $exit_code)" "error"
        return $exit_code
    fi
}

# Функция очистки старых логов
cleanup_logs() {
    # Удаляем логи старше 30 дней
    find "$(dirname "$LOG_FILE")" -name "*.log" -mtime +30 -delete 2>/dev/null || true
    
    # Ограничиваем размер текущего лог файла (последние 1000 строк)
    if [[ -f "$LOG_FILE" ]] && [[ $(wc -l < "$LOG_FILE") -gt 1000 ]]; then
        tail -n 1000 "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
    fi
}

# Обработка аргументов командной строки
case "${1:-monitor}" in
    "monitor")
        monitor
        ;;
    "run")
        run_watcher
        ;;
    "cleanup")
        cleanup_logs
        log "Очистка логов завершена"
        ;;
    "health")
        python3 "$SCRIPT_DIR/health_check.py" --health-file "$HEALTH_FILE" --max-age "$MAX_AGE_MINUTES"
        ;;
    *)
        echo "Использование: $0 [monitor|run|cleanup|health]"
        echo "  monitor  - Проверить здоровье приложения (по умолчанию)"
        echo "  run      - Запустить API Watcher"
        echo "  cleanup  - Очистить старые логи"
        echo "  health   - Показать текущее состояние здоровья"
        exit 1
        ;;
esac