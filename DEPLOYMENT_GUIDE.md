# Развёртывание WikiMovieRec на сервер

## Подготовка

### 1. SSH ключ
Создан SSH ключ `id_ed25519` для подключения к серверу 217.144.186.110.

**Публичный ключ для добавления на сервер:**
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPh4pvWGUWifJRotgF4aZTeYwAiVW9RaZpnNr/9Pigg1 on.suslova@217.144.186.110
```

### 2. Структура проекта на сервере
```
/home/on.suslova/wiki-movie-rec/
├── .venv/                     # Виртуальное окружение Python 3.12
├── src/                      # Исходный код
├── static/                   # Веб-интерфейс
├── logs/                     # Логи приложения
├── config/                   # Конфигурационные файлы
├── scripts/                  # Скрипты администрирования
├── data/ -> /data/wiki-movie-data/  # Симлинк на большой диск
├── models/                   # Обученные модели
├── notebooks/                # Исследовательские ноутбуки
├── pyproject.toml           # Зависимости
└── README.md                # Документация
```

## Скрипты развёртывания

### Для Windows (PowerShell)
```powershell
.\deploy_server.ps1
```

### Для Linux/macOS (Bash)
```bash
chmod +x deploy_server.sh
./deploy_server.sh
```

## Ручное развёртывание

### 1. Подключение к серверу
```bash
ssh -i ~/.ssh/id_ed25519 root@217.144.186.110
```

### 2. Создание структуры
```bash
mkdir -p /home/on.suslova/wiki-movie-rec
mkdir -p /home/on.suslova/wiki-movie-rec/{src,static,logs,config,scripts,notebooks,models}
```

### 3. Копирование файлов
```bash
# С локальной машины
scp -i ~/.ssh/id_ed25519 -r src/* root@217.144.186.110:/home/on.suslova/wiki-movie-rec/src/
scp -i ~/.ssh/id_ed25519 -r static/* root@217.144.186.110:/home/on.suslova/wiki-movie-rec/static/
scp -i ~/.ssh/id_ed25519 pyproject.toml requirements.txt run_server.py README.md root@217.144.186.110:/home/on.suslova/wiki-movie-rec/
```

### 4. Настройка окружения
```bash
# На сервере
cd /home/on.suslova/wiki-movie-rec

# Установка Python 3.12
apt-get update
apt-get install -y software-properties-common
add-apt-repository -y ppa:deadsnakes/ppa
apt-get update
apt-get install -y python3.12 python3.12-venv python3.12-dev

# Создание виртуального окружения
python3.12 -m venv .venv
source .venv/bin/activate

# Установка зависимостей
pip install --upgrade pip
pip install -r requirements.txt
pip install tensorflow==2.10
```

### 5. Запуск сервера
```bash
# Тестовый запуск
source .venv/bin/activate
python -m uvicorn src.api:create_app --host 0.0.0.0 --port 8000

# Или через run_server.py
python run_server.py --production
```

## Systemd сервис

### Создание сервиса
```bash
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
```

### Управление сервисом
```bash
# Перезагрузка systemd
systemctl daemon-reload

# Включение автозапуска
systemctl enable wiki-movie-rec.service

# Запуск сервиса
systemctl start wiki-movie-rec.service

# Проверка статуса
systemctl status wiki-movie-rec.service

# Просмотр логов
journalctl -u wiki-movie-rec.service -f
```

## Конфигурация

### environment.env
```
WIKIMODREC_PRESET=fast
WIKIMODREC_BACKEND=keras
WIKIMODREC_PORT=8000
WIKIMODREC_HOST=0.0.0.0
PYTHONPATH=/home/on.suslova/wiki-movie-rec/src
```

### config/production.yml
```yaml
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
```

## Обучение моделей на сервере

### Обучение medium модели
```bash
cd /home/on.suslova/wiki-movie-rec
source .venv/bin/activate
python -m src.embedding train --preset medium --backend keras
```

### Обучение deep модели
```bash
python -m src.embedding train --preset deep --backend keras
```

## Мониторинг

### Проверка работы API
```bash
# Проверка health endpoint
curl http://217.144.186.110:8000/api/health

# Тестовый запрос рекомендаций
curl "http://217.144.186.110:8000/api/similar?movie=Titanic&top_k=5"
```

### Логи
- Логи приложения: `/home/on.suslova/wiki-movie-rec/logs/`
- Systemd логи: `journalctl -u wiki-movie-rec.service`
- Ошибки: `/home/on.suslova/wiki-movie-rec/logs/errors.log`

## Устранение неполадок

### 1. Проблемы с SSH подключением
```bash
# Проверка ключа
ssh-keygen -l -f ~/.ssh/id_ed25519

# Проверка подключения
ssh -v -i ~/.ssh/id_ed25519 root@217.144.186.110
```

### 2. Проблемы с Python окружением
```bash
# Проверка версии Python
python3.12 --version

# Пересоздание виртуального окружения
rm -rf .venv
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Проблемы с сервисом
```bash
# Перезапуск сервиса
systemctl restart wiki-movie-rec.service

# Проверка логов
journalctl -u wiki-movie-rec.service --since "1 hour ago"
```

## Контакты
- Сервер: 217.144.186.110
- Пользователь: on.suslova
- Порт API: 8000
- Документация API: http://217.144.186.110:8000/docs