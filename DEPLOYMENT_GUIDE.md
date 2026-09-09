# Развёртывание WikiMovieRec на сервер

## Обзор

Продакшн-сервер: **VPS**, порт **5041**.
Сервис работает как systemd-юнит `wikimovierec` из каталога `/root/WikiMovieRec`.

## Структура на сервере

```
/root/WikiMovieRec/
├── .venv/                  # Виртуальное окружение Python 3.12
├── src/                    # Исходный код
├── static/                 # Веб-интерфейс (index.html, style.css)
├── config/                 # Конфигурации (production.yml, development.yml)
├── scripts/                # Скрипты администрирования
├── models/                 # Обученные модели (*.pkl)
├── data/imdb/              # Скачанные IMDb-файлы
├── logs/                   # Логи
├── run_server.py
├── update_data.py
└── requirements.txt
```

## Подключение

```bash
ssh -i ~/.ssh/id_ed25519 root@SERVER_IP
```

## systemd-сервис

Файл юнита: `/etc/systemd/system/wikimovierec.service`

```ini
[Unit]
Description=WikiMovieRec API Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/WikiMovieRec
Environment=PYTHONUNBUFFERED=1
Environment=WIKIMODREC_PRESET=fast
Environment=WIKIMODREC_BACKEND=keras
Environment=WIKIMODREC_SOURCE=imdb
ExecStart=/root/WikiMovieRec/.venv/bin/python -m uvicorn src.api:create_app --host 0.0.0.0 --port 5041
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Управление

```bash
systemctl status wikimovierec     # статус
systemctl restart wikimovierec    # перезапуск после обновления
systemctl stop wikimovierec       # остановка
systemctl enable wikimovierec     # автозапуск при загрузке
journalctl -u wikimovierec -n 100 --no-pager   # логи
```

## Деплой кода

### 1. Копирование файлов

```bash
# С локальной машины (Windows)
scp -i ~/.ssh/id_ed25519 -r src/* root@SERVER_IP:/root/WikiMovieRec/src/
scp -i ~/.ssh/id_ed25519 -r static/* root@SERVER_IP:/root/WikiMovieRec/static/
scp -i ~/.ssh/id_ed25519 requirements.txt run_server.py root@SERVER_IP:/root/WikiMovieRec/
```

### 2. Перезапуск сервиса

```bash
ssh -i ~/.ssh/id_ed25519 root@SERVER_IP "systemctl restart wikimovierec"
```

### 3. Проверка

```bash
curl http://SERVER_IP:5041/api/health
```

Ожидаемый ответ:

```json
{"status": "ok", "model": "fast", "movies": 9583, "year_map": 8767}
```

## Скрипты деплоя

- `deploy_server.ps1` — PowerShell (Windows)
- `deploy_server.sh` — Bash (Linux/macOS)

## Обновление модели

Модель обучается на сервере и сохраняется в `models/`. После обучения перезапустите сервис, чтобы он подхватил новую модель:

```bash
# Обучить medium-модель (в фоне)
cd /root/WikiMovieRec && nohup .venv/bin/python -m src.main --train --preset medium --source imdb > medium_train.log 2>&1 &

# После завершения — перезапустить сервис
systemctl restart wikimovierec
```

Чтобы переключить сервис на другую модель, измените `WIKIMODREC_PRESET` в юните (fast / medium / deep) и перезапустите.

## Переменные окружения

| Переменная | Значение на сервере | Описание |
|-----------|--------------------|----------|
| `WIKIMODREC_PRESET` | `fast` | Пресет модели |
| `WIKIMODREC_BACKEND` | `keras` | Бэкенд обучения |
| `WIKIMODREC_SOURCE` | `imdb` | Источник метаданных |
| `PYTHONUNBUFFERED` | `1` | Не буферизовать вывод Python |
