#!/bin/bash
# deploy_wiki_movie_rec.sh - Скрипт развёртывания WikiMovieRec на сервер

set -e  # Выход при ошибке

# Конфигурация
SERVER="217.144.186.110"
USER="root"
SSH_KEY="$HOME/.ssh/id_ed25519"
REMOTE_DIR="/home/on.suslova/wiki-movie-rec"
LOCAL_DIR="$(pwd)"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Развёртывание WikiMovieRec на сервер $SERVER ===${NC}"

# 1. Проверка SSH ключа
echo -e "${YELLOW}[1/7] Проверка SSH ключа...${NC}"
if [ ! -f "$SSH_KEY" ]; then
    echo -e "${RED}Ошибка: SSH ключ $SSH_KEY не найден${NC}"
    exit 1
fi

# 2. Проверка локальных файлов
echo -e "${YELLOW}[2/7] Проверка локальных файлов...${NC}"
if [ ! -f "pyproject.toml" ]; then
    echo -e "${RED}Ошибка: pyproject.toml не найден${NC}"
    exit 1
fi

# 3. Создание структуры на сервере
echo -e "${YELLOW}[3/7] Создание структуры на сервере...${NC}"
ssh -i "$SSH_KEY" "$USER@$SERVER" << EOF
    # Создание директорий
    mkdir -p "$REMOTE_DIR"
    mkdir -p "$REMOTE_DIR/src"
    mkdir -p "$REMOTE_DIR/static"
    mkdir -p "$REMOTE_DIR/logs"
    mkdir -p "$REMOTE_DIR/config"
    mkdir -p "$REMOTE_DIR/scripts"
    mkdir -p "$REMOTE_DIR/notebooks"
    
    # Проверка существования /data для больших файлов
    if [ -d "/data" ]; then
        mkdir -p "/data/wiki-movie-data"
        ln -sf "/data/wiki-movie-data" "$REMOTE_DIR/data" 2>/dev/null || true
    else
        mkdir -p "$REMOTE_DIR/data"
    fi
    
    # Создание models директории
    mkdir -p "$REMOTE_DIR/models"
    
    echo "Структура создана в $REMOTE_DIR"
EOF

# 4. Копирование файлов
echo -e "${YELLOW}[4/7] Копирование файлов...${NC}"

# Копирование исходного кода
scp -i "$SSH_KEY" -r src/* "$USER@$SERVER:$REMOTE_DIR/src/"

# Копирование статических файлов
scp -i "$SSH_KEY" -r static/* "$USER@$SERVER:$REMOTE_DIR/static/"

# Копирование основных файлов
scp -i "$SSH_KEY" \
    pyproject.toml \
    requirements.txt \
    run_server.py \
    README.md \
    "$USER@$SERVER:$REMOTE_DIR/"

# Копирование скриптов
scp -i "$SSH_KEY" \
    update_data.py \
    validate_data.py \
    "$USER@$SERVER:$REMOTE_DIR/scripts/"

# 5. Настройка окружения
echo -e "${YELLOW}[5/7] Настройка окружения на сервере...${NC}"
ssh -i "$SSH_KEY" "$USER@$SERVER" << 'EOF'
    cd "$REMOTE_DIR"
    
    # Обновление пакетов
    apt-get update && apt-get upgrade -y
    
    # Установка Python 3.12
    if ! command -v python3.12 &> /dev/null; then
        echo "Установка Python 3.12..."
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
    
    # Установка TensorFlow для Python 3.12
    pip install tensorflow==2.10
    
    echo "Окружение настроено"
EOF

# 6. Создание конфигурационных файлов
echo -e "${YELLOW}[6/7] Создание конфигурационных файлов...${NC}"
cat > config.production.yml << 'EOF'
# Конфигурация для продакшн сервера
server:
  host: "0.0.0.0"
  port: 8000
  workers: 4
  reload: false

model:
  preset: "fast"
  backend: "keras"
  source: "imdb"

data:
  imdb_dir: "/data/wiki-movie-data/imdb"
  models_dir: "./models"
  logs_dir: "./logs"

logging:
  level: "INFO"
  file: "./logs/api.log"
  max_size: "10MB"
  backup_count: 5
EOF

cat > environment.env << 'EOF'
# Переменные окружения для WikiMovieRec
WIKIMODREC_PRESET=fast
WIKIMODREC_BACKEND=keras
WIKIMODREC_PORT=8000
WIKIMODREC_HOST=0.0.0.0
PYTHONPATH=/home/on.suslova/wiki-movie-rec/src
EOF

# Копирование конфигураций на сервер
scp -i "$SSH_KEY" \
    config.production.yml \
    environment.env \
    "$USER@$SERVER:$REMOTE_DIR/config/"

# 7. Создание systemd сервиса
echo -e "${YELLOW}[7/7] Настройка systemd сервиса...${NC}"
cat > wiki-movie-rec.service << 'EOF'
[Unit]
Description=WikiMovieRec Recommendation API
After=network.target

[Service]
Type=simple
User=on.suslova
Group=on.suslova
WorkingDirectory=/home/on.suslova/wiki-movie-rec
EnvironmentFile=/home/on.suslova/wiki-movie-rec/config/environment.env
ExecStart=/home/on.suslova/wiki-movie-rec/.venv/bin/python -m uvicorn src.api:create_app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=wiki-movie-rec

[Install]
WantedBy=multi-user.target
EOF

scp -i "$SSH_KEY" wiki-movie-rec.service "$USER@$SERVER:/etc/systemd/system/"

ssh -i "$SSH_KEY" "$USER@$SERVER" << 'EOF'
    # Создание пользователя on.suslova если не существует
    if ! id "on.suslova" &>/dev/null; then
        useradd -m -s /bin/bash on.suslova
    fi
    
    # Настройка прав
    chown -R on.suslova:on.suslova "$REMOTE_DIR"
    
    # Перезагрузка systemd и запуск сервиса
    systemctl daemon-reload
    systemctl enable wiki-movie-rec.service
    systemctl start wiki-movie-rec.service
    
    echo "Сервис запущен"
    echo "Проверка статуса: systemctl status wiki-movie-rec.service"
    echo "Логи: journalctl -u wiki-movie-rec.service -f"
EOF

# Очистка временных файлов
rm -f config.production.yml environment.env wiki-movie-rec.service

echo -e "${GREEN}=== Развёртывание завершено! ===${NC}"
echo -e "Сервер доступен по адресу: http://$SERVER:8000"
echo -e "API документация: http://$SERVER:8000/docs"
echo -e ""
echo -e "Полезные команды:"
echo -e "  systemctl status wiki-movie-rec.service  # Статус сервиса"
echo -e "  journalctl -u wiki-movie-rec.service -f  # Просмотр логов"
echo -e "  systemctl restart wiki-movie-rec.service # Перезапуск"
echo -e ""
echo -e "Для обучения моделей на сервере:"
echo -e "  ssh $USER@$SERVER 'cd $REMOTE_DIR && source .venv/bin/activate && python -m src.embedding train --preset medium --backend keras'"
EOF