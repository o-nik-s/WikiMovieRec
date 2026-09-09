# WikiMovieRec

Рекомендательная система фильмов, построенная на графе исходящих ссылок Википедии. Фильмы, которые ссылаются друг на друга в статьях, считаются «похожими» — модель обучает векторные эмбеддинги так, чтобы такие фильмы оказывались близко в векторном пространстве.

Живой пример доступен по запросу.

## Что умеет

- **Похожие фильмы** — по одному фильму находит ближайших соседей по косинусной близости эмбеддингов.
- **Профиль вкуса** — рекомендации по нескольким любимым фильмам (усреднённый вектор).
- **«Случайный» подбор (кубик)** — вероятностная выборка из пула похожих фильмов: чем ближе фильм, тем выше шанс выпасть, но каждый раз список разный.
- **Фильтры** — по жанру, диапазону лет и минимальному рейтингу IMDb.
- **Два языка** — русский и английский интерфейс, переключается на лету.
- **Русские названия** — сопоставление английских названий с русскими через IMDb akas.

## Стек

- **Python 3.12**, **TensorFlow / Keras** — обучение эмбеддингов
- **FastAPI + uvicorn** — API и раздача фронтенда
- **NumPy / Pandas** — обработка данных
- **vanilla JavaScript** — фронтенд без фреймворков
- **IMDb Non-Commercial Datasets** — метаданные (жанр, режиссёр, рейтинг, год)
- **systemd + VPS** — продакшн-деплой

## Как это работает

1. Берём датасет фильмов из Википедии (`wp_movies_10k.ndjson`) — для каждого фильма список исходящих ссылок.
2. Строим пары «фильм → ссылка» и обучаем Keras-модель с embedding-слоями (по аналогии с word2vec): фильмы, у которых много общих ссылок, получают близкие векторы.
3. Метаданные (жанр, режиссёр, рейтинг, год) подтягиваются из IMDb и используются для фильтрации.
4. Готовая модель сохраняется в `models/` и загружается при старте сервера за доли секунды — пересчёт на лету не нужен.

## Структура проекта

```
├── src/
│   ├── api.py             # FastAPI: эндпоинты + раздача статики
│   ├── app.py             # Точка входа uvicorn
│   ├── config.py          # Конфигурация (пресеты, источники, годы)
│   ├── data_loader.py     # Загрузка NDJSON / CSV / IMDb
│   ├── preprocessor.py    # Feature engineering + слияние с метаданными
│   ├── embedding.py       # Обучение эмбеддингов (Keras / SVD fallback)
│   ├── recommender.py     # Косинусная близость + фильтры
│   ├── model_cache.py     # Сохранение/загрузка моделей
│   ├── imdb_loader.py     # Скачивание и парсинг IMDb TSV.gz
│   ├── i18n.py            # EN/RU локализация
│   ├── ru_names.py        # Русско-английский маппинг названий
│   └── main.py            # CLI: обучение / загрузка
├── static/
│   ├── index.html         # Фронтенд
│   └── style.css
├── tests/
│   └── test_pipeline.py
├── models/                # Обученные модели (в gitignore)
├── data/imdb/             # Скачанные IMDb-файлы (в gitignore)
├── run_server.py          # Запуск API
├── update_data.py         # Обновление данных и переобучение
└── requirements.txt
```

## Установка

```bash
git clone https://github.com/o-nik-s/WikiMovieRec.git
cd WikiMovieRec

# Windows
py -3.12 -m venv .venv
.venv\Scripts\activate

# Linux / macOS
python3.12 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt -r requirements-keras.txt
```

## Обучение модели

```bash
# Быстрая (32d) — для проверки
python -m src.main --train --preset fast

# Сбалансированная (100d) — дефолт для продакшена
python -m src.main --train --preset medium

# Глубокая (200d) — дольше, точнее
python -m src.main --train --preset deep
```

Модели сохраняются в `models/`. Пресеты:

| Пресет | Размерность | Эпохи | Размер файла |
|--------|-------------|-------|--------------|
| `fast` | 32 | 5 | ~2 MB |
| `medium` | 100 | 25 | ~8 MB |
| `deep` | 200 | 50 | ~15 MB |

## Запуск сервера

```bash
# Development (hot-reload)
python run_server.py

# Production
python run_server.py --production
```

По умолчанию сервер слушает порт `8000`. Параметры задаются через переменные окружения:

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `WIKIMODREC_HOST` | `0.0.0.0` | Адрес привязки |
| `WIKIMODREC_PORT` | `8000` | Порт |
| `WIKIMODREC_WORKERS` | `1` | Число воркеров |
| `WIKIMODREC_PRESET` | `medium` | Пресет модели |
| `WIKIMODREC_DEBUG` | `0` | Hot-reload (только dev) |

Пример с другим портом и моделью:

```bash
WIKIMODREC_PORT=9000 WIKIMODREC_PRESET=fast python run_server.py
```

## API

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| GET | `/api/health` | Статус сервиса и загруженной модели |
| GET | `/api/search?q=` | Поиск фильма по названию |
| GET | `/api/similar?movie=` | Похожие фильмы по одному фильму |
| GET | `/api/profile?movies=` | Рекомендации по профилю вкуса |
| GET | `/api/profile-sample?movies=` | «Случайный» подбор (кубик) |
| POST | `/api/recommend` | Рекомендация (JSON) |
| GET | `/api/genres` | Список жанров |
| GET | `/api/ru-names?names=` | Русские названия для списка фильмов |
| GET | `/api/models` | Список доступных моделей |

Пример:

```bash
curl "http://localhost:8000/api/similar?movie=Titanic&top_k=5"
```

```json
{
  "similar": [
    {"name": "Evita", "similarity": 0.9786, "year": 1996, "genres": ["Biography", "Drama"]},
    {"name": "Empire of the Sun", "similarity": 0.9649, "year": 1987, "genres": ["Drama", "War"]}
  ]
}
```

Swagger UI доступен на `/docs`.

## Обновление данных

IMDb-датасеты обновляются ежедневно. Скрипт `update_data.py` скачивает свежие файлы и при необходимости переобучает модель:

```bash
# Скачать данные + статистика
python update_data.py

# Скачать + переобучить medium
python update_data.py --train medium

# Переобучить все пресеты
python update_data.py --retrain

# Только статистика
python update_data.py --check
```

## Деплой на VPS

Продакшн-сервер работает как systemd-сервис `wikimovierec`:

```bash
# Проверить статус
systemctl status wikimovierec

# Перезапустить после обновления кода
systemctl restart wikimovierec

# Логи
journalctl -u wikimovierec -n 100 --no-pager
```

Сервис запускает uvicorn с загруженной моделью. Файлы деплоя — `deploy_server.sh` (Linux) и `deploy_server.ps1` (Windows).

## Тесты

```bash
python -m unittest tests.test_pipeline -v
```

## Примечание о данных

Основной датасет фильмов (`wp_movies_10k.ndjson`) собран из Википедии и содержит в основном фильмы до ~2016 года. Свежих фильмов (2024–2026) в нём мало, поэтому фильтры по последним годам дают немного результатов. Годы и метаданные подтягиваются из IMDb, но только для тех фильмов, что есть в датасете.

