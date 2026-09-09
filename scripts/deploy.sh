#!/bin/bash
# Скрипт развёртывания на сервер

set -e

SERVER="217.144.186.110"
USER="on.suslova"
REMOTE_DIR="/home/on.suslova/wiki-movie-rec"
SSH_KEY="$HOME/.ssh/id_ed25519"

echo "=== Развёртывание WikiMovieRec на сервер $SERVER ==="

# Проверка SSH ключа
if [ ! -f "$SSH_KEY" ]; then
    echo "Ошибка: SSH ключ $SSH_KEY не найден"
    exit 1
fi

# Создание структуры на сервере
echo "[1/6] Создание структуры на сервере..."
ssh -i "$SSH_KEY" "$USER@$SERVER" "
    mkdir -p \"$REMOTE_DIR\"
    mkdir -p \"$REMOTE_DIR/src\"
    mkdir -p \"$REMOTE_DIR/static\"
    mkdir -p \"$REMOTE_DIR/logs\"
    mkdir -p \"$REMOTE_DIR/config\"
    mkdir -p \"$REMOTE_DIR/scripts\"
    mkdir -p \"$REMOTE_DIR/models\"
    echo 'Структура создана в $REMOTE_DIR'
"

# Копирование файлов
echo "[2/6] Копирование файлов..."
scp -i "$SSH_KEY" -r src/* "$USER@$SERVER:$REMOTE_DIR/src/"
scp -i "$SSH_KEY" -r static/* "$USER@$SERVER:$REMOTE_DIR/static/"
scp -i "$SSH_KEY" pyproject.toml requirements.txt requirements-keras.txt "$USER@$SERVER:$REMOTE_DIR/"
scp -i "$SSH_KEY" run_server.py README.md .env "$USER@$SERVER:$REMOTE_DIR/"
scp -i "$SSH_KEY" config/* "$USER@$SERVER:$REMOTE_DIR/config/"

# Настройка окружения
echo "[3/6] Настройка окружения на сервере..."
ssh -i "$SSH_KEY" "$USER@$SERVER" "
    cd \"$REMOTE_DIR\"
    
    # Установка Python 3.12
    if ! command -v python3.12 &> /dev/null; then
        echo 'Установка Python 3.12...'
        apt-get update
        apt-get install -y software-properties-common
        add-apt-repository -y ppa:deadsnakes/ppa
        apt-get update
        apt-get install -y python3.12 python3.12-venv python3.12-dev
    fi
    
    # Создание виртуального окружения
    python3.12 -m venv .venv
    
    # Активация и установка зависимостей
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    pip install -r requirements-keras.txt
    
    echo 'Окружение настроено'
"

# Создание systemd сервиса
echo "[4/6] Настройка systemd сервиса..."
ssh -i "$SSH_KEY" "$USER@$SERVER" "
    # Создание systemd сервиса
    cat > /etc/systemd/system/wiki-movie-rec.service << 'EOF'
[Unit]
Description=WikiMovieRec Recommendation API
After=network.target

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$REMOTE_DIR
EnvironmentFile=$REMOTE_DIR/.env
ExecStart=$REMOTE_DIR/.venv/bin/python -m uvicorn src.api:create_app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=wiki-movie-rec

[Install]
WantedBy=multi-user.target
EOF

    # Перезагрузка systemd и запуск сервиса
    systemctl daemon-reload
    systemctl enable wiki-movie-rec.service
    systemctl start wiki-movie-rec.service
    
    echo 'Сервис запущен'
"

echo "[5/6] Проверка работы сервиса..."
ssh -i "$SSH_KEY" "$USER@$SERVER" "
    sleep 3
    systemctl status wiki-movie-rec.service --no-pager
"

echo "[6/6] Проверка API..."
ssh -i "$SSH_KEY" "$USER@$SERVER" "
    curl -s http://localhost:8000/api/health || echo 'API пока не отвечает, подождите несколько секунд'
"

echo "=== Развёртывание завершено! ==="
echo "Сервер доступен по адресу: http://$SERVER:8000"
echo "API документация: http://$SERVER:8000/docs"
echo ""
echo "Полезные команды:"
echo "  systemctl status wiki-movie-rec.service  # Статус сервиса"
echo "  journalctl -u wiki-movie-rec.service -f  # Просмотр логов"
echo "  systemctl restart wiki-movie-rec.service # Перезапуск"