# Web Deployment Guide

Руководство по развёртыванию WikiMovieRec в продакшн.

## Обзор

Сервис состоит из:
- **FastAPI + uvicorn** — API и раздача статики
- **Keras-модель** — векторные эмбеддинги фильмов
- **vanilla JavaScript** — фронтенд
- **systemd** — управление процессом на сервере

## Локальный запуск

```bash
# Активировать окружение
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux/macOS

# Установить зависимости
pip install -r requirements.txt -r requirements-keras.txt

# Запустить dev-сервер
python run_server.py
```

Откройте http://localhost:8000.

## Продакшн-деплой

### 1. Подготовка сервера

```bash
# Python 3.12
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-keras.txt
```

### 2. Копирование кода

```bash
scp -r src/ static/ config/ scripts/ root@SERVER:/path/to/WikiMovieRec/
scp requirements.txt requirements-keras.txt run_server.py root@SERVER:/path/to/WikiMovieRec/
```

### 3. systemd-сервис

Создайте `/etc/systemd/system/wikimovierec.service`:

```ini
[Unit]
Description=WikiMovieRec API Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/path/to/WikiMovieRec
Environment=PYTHONUNBUFFERED=1
Environment=WIKIMODREC_PRESET=fast
Environment=WIKIMODREC_BACKEND=keras
Environment=WIKIMODREC_SOURCE=imdb
ExecStart=/path/to/WikiMovieRec/.venv/bin/python -m uvicorn src.api:create_app --host 0.0.0.0 --port 5041
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now wikimovierec
```

### 4. Проверка

```bash
curl http://localhost:5041/api/health
```

```json
{"status": "ok", "model": "fast", "movies": 9583, "year_map": 8767}
```

## Управление сервисом

```bash
systemctl status wikimovierec
systemctl restart wikimovierec
journalctl -u wikimovierec -n 100 --no-pager
```

## Обновление

1. Скопировать новые файлы на сервер.
2. Перезапустить сервис: `systemctl restart wikimovierec`.
3. Проверить `/api/health`.

## Переменные окружения

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `WIKIMODREC_HOST` | `0.0.0.0` | Адрес привязки |
| `WIKIMODREC_PORT` | `8000` | Порт |
| `WIKIMODREC_WORKERS` | `1` | Число воркеров |
| `WIKIMODREC_PRESET` | `medium` | Пресет модели (fast/medium/deep) |
| `WIKIMODREC_BACKEND` | `keras` | Бэкенд обучения |
| `WIKIMODREC_SOURCE` | `imdb` | Источник метаданных |
| `WIKIMODREC_DEBUG` | `0` | Hot-reload (только dev) |

## Обучение модели на сервере

```bash
# В фоне (занимает ~1.5 часа для medium)
nohup .venv/bin/python -m src.main --train --preset medium --source imdb > medium_train.log 2>&1 &

# После завершения — перезапустить сервис
systemctl restart wikimovierec
```

## Troubleshooting

### Сервис не стартует

```bash
journalctl -u wikimovierec -n 50 --no-pager
```

### Модель не загружается

- Проверьте, что файл есть в `models/`.
- Проверьте `WIKIMODREC_PRESET` в юните.
- Убедитесь, что `unidecode` установлен: `.venv/bin/pip install unidecode`.

### Порт занят

```bash
ss -tlnp | grep 5041
```
