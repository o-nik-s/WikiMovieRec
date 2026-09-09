# deploy_server.ps1 - Скрипт развёртывания WikiMovieRec на сервер (PowerShell)

param(
    [string]$Server = "217.144.186.110",
    [string]$User = "root",
    [string]$SshKey = "$HOME\.ssh\id_ed25519",
    [string]$RemoteDir = "/home/on.suslova/wiki-movie-rec"
)

Write-Host "=== Развёртывание WikiMovieRec на сервер $Server ===" -ForegroundColor Green

# 1. Проверка SSH ключа
Write-Host "[1/7] Проверка SSH ключа..." -ForegroundColor Yellow
if (-not (Test-Path $SshKey)) {
    Write-Host "Ошибка: SSH ключ $SshKey не найден" -ForegroundColor Red
    exit 1
}

# 2. Проверка локальных файлов
Write-Host "[2/7] Проверка локальных файлов..." -ForegroundColor Yellow
if (-not (Test-Path "pyproject.toml")) {
    Write-Host "Ошибка: pyproject.toml не найден" -ForegroundColor Red
    exit 1
}

# 3. Создание структуры на сервере
Write-Host "[3/7] Создание структуры на сервере..." -ForegroundColor Yellow
$createStructure = @"
    # Создание директорий
    mkdir -p "$RemoteDir"
    mkdir -p "$RemoteDir/src"
    mkdir -p "$RemoteDir/static"
    mkdir -p "$RemoteDir/logs"
    mkdir -p "$RemoteDir/config"
    mkdir -p "$RemoteDir/scripts"
    mkdir -p "$RemoteDir/notebooks"
    
    # Проверка существования /data для больших файлов
    if [ -d "/data" ]; then
        mkdir -p "/data/wiki-movie-data"
        ln -sf "/data/wiki-movie-data" "$RemoteDir/data" 2>/dev/null || true
    else
        mkdir -p "$RemoteDir/data"
    fi
    
    # Создание models директории
    mkdir -p "$RemoteDir/models"
    
    echo "Структура создана в $RemoteDir"
"@

ssh -i $SshKey $User@$Server $createStructure

# 4. Копирование файлов
Write-Host "[4/7] Копирование файлов..." -ForegroundColor Yellow

# Копирование исходного кода
scp -i $SshKey -r src\* $User@$Server`:$RemoteDir/src/

# Копирование статических файлов
scp -i $SshKey -r static\* $User@$Server`:$RemoteDir/static/

# Копирование основных файлов
$files = @("pyproject.toml", "requirements.txt", "run_server.py", "README.md")
foreach ($file in $files) {
    if (Test-Path $file) {
        scp -i $SshKey $file $User@$Server`:$RemoteDir/
    }
}

# Копирование скриптов
$scriptFiles = @("update_data.py", "validate_data.py")
foreach ($script in $scriptFiles) {
    if (Test-Path $script) {
        scp -i $SshKey $script $User@$Server`:$RemoteDir/scripts/
    }
}

# 5. Настройка окружения
Write-Host "[5/7] Настройка окружения на сервере..." -ForegroundColor Yellow
$setupEnv = @"
    cd "$RemoteDir"
    
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
"@

ssh -i $SshKey $User@$Server $setupEnv

# 6. Создание конфигурационных файлов
Write-Host "[6/7] Создание конфигурационных файлов..." -ForegroundColor Yellow

# Создание конфигурации на сервере
$createConfig = @"
    cd "$RemoteDir/config"
    
    # Создание production конфигурации
    cat > production.yml << 'EOF'
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

    # Создание переменных окружения
    cat > environment.env << 'EOF'
# Переменные окружения для WikiMovieRec
WIKIMODREC_PRESET=fast
WIKIMODREC_BACKEND=keras
WIKIMODREC_PORT=8000
WIKIMODREC_HOST=0.0.0.0
PYTHONPATH=/home/on.suslova/wiki-movie-rec/src
EOF

    echo "Конфигурационные файлы созданы"
"@

ssh -i $SshKey $User@$Server $createConfig

# 7. Создание systemd сервиса
Write-Host "[7/7] Настройка systemd сервиса..." -ForegroundColor Yellow
$setupService = @"
    # Создание systemd сервиса
    cat > /etc/systemd/system/wiki-movie-rec.service << 'EOF'
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

    # Создание пользователя on.suslova если не существует
    if ! id "on.suslova" &>/dev/null; then
        useradd -m -s /bin/bash on.suslova
    fi
    
    # Настройка прав
    chown -R on.suslova:on.suslova "$RemoteDir"
    
    # Перезагрузка systemd и запуск сервиса
    systemctl daemon-reload
    systemctl enable wiki-movie-rec.service
    systemctl start wiki-movie-rec.service
    
    echo "Сервис запущен"
    echo "Проверка статуса: systemctl status wiki-movie-rec.service"
    echo "Логи: journalctl -u wiki-movie-rec.service -f"
"@

ssh -i $SshKey $User@$Server $setupService

Write-Host "=== Развёртывание завершено! ===" -ForegroundColor Green
Write-Host "Сервер доступен по адресу: http://$Server:8000" -ForegroundColor Cyan
Write-Host "API документация: http://$Server:8000/docs" -ForegroundColor Cyan
Write-Host ""
Write-Host "Полезные команды:" -ForegroundColor Yellow
Write-Host "  systemctl status wiki-movie-rec.service  # Статус сервиса"
Write-Host "  journalctl -u wiki-movie-rec.service -f  # Просмотр логов"
Write-Host "  systemctl restart wiki-movie-rec.service # Перезапуск"
Write-Host ""
Write-Host "Для обучения моделей на сервере:" -ForegroundColor Yellow
Write-Host "  ssh $User@$Server 'cd $RemoteDir && source .venv/bin/activate && python -m src.embedding train --preset medium --backend keras'"