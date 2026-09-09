# WikiMovieRec

Рекомендательная система фильмов на основе графа ссылок Wikipedia + метаданных (жанр, режиссёр, актёры, страна).

## Описание

Проект строит векторные представления фильмов из пересечения исходящих Wikipedia-ссылок
и обогащает их метаданными из внешних источников. Фильмы со схожими
темами и жанрами оказываются «близко» в векторном пространстве.

Поддерживается **предварительное обучение моделей с сохранением** — на сайте загружается
готовая модель (`models/*.pkl`) за доли секунды вместо пересчёта с нуля.

В интерфейс переведён на **два языка (EN/RU)** с автодетектом по локали или явным флагом `--lang`.

## Архитектура

```
┌───────────────────┐    ┌───────────────────┐    ┌──────────────────────┐
│  NDJSON (10 000)  │───▶│  Preprocess links │───▶│  Build link index    │
│  wiki movie links │    │  + ratings        │    │  (freq ≥ 10)         │
└───────────────────┘    └───────────────────┘          │                │
                                                         ▼                │
┌──────────────────┐   ┌──────────────────────┐         │                ▼  ┌────────────────────────────┐
│  CSV (34 886)    │   │  Genre + Director    │─────────┼── build_pairs ─┤──▶│ Train embeddings (SVD)    │
│  (wiki plots     │   │  + Cast + Origin     │         │                │  │  (Keras Siamese NN if     │
│   legacy)        │──▶│  + Year (decade)     │────    │                │  │   TensorFlow available)     │
└──────────────────┘   └──────────────────────┘         │                │  └──────────────┬──────────────┘
┌───────────────────┐   ┌──────────────────────┐         │                │                 │
│  IMDb (755 945)   │   │  Genre + Director    │─────────┼                │                 │
│  movies (updated  │   │  + IMDb_Rating       │         │                │                 │
│   daily, 2026)    │──▶│  + IMDb_Votes        │─────────┘                │                 │
└───────────────────┘   └──────────────────────┘                         │                 │
                                                                         │                 │
              ┌──────────────────────────────────────────────────────────┘                 │
              │                                                                            │
              ▼                                                                            ▼
    ┌───────────────────┐    ┌──────────────────────┐   ┌────────────────────────────────────┐
    │  Model Cache      │◀───│  Embeddings (pkl)    │   │  ModelPresets (выбор качества)    │
    │  models/          │    │  + movie_to_idx      │   ├── fast:     32d,  5 epochs, ~2 MB │
    │  (*.pkl)          │    │  + idx_to_movie      │   ├── medium:   100d, 25 epochs, ~8 MB│
    └────────┬──────────┘    │  + meta (timestamp)  │   └── deep:     200d, 50 epochs, ~15MB│
             │               └──────────────────────┘   └────────────────────────────────────┘
             │ (0.1sec load)
             ▼
    ┌───────────────────┐    ┌─────────────────────┐    ┌──────────────────────────┐
    │  Recommender      │◀───│  Similar (cosine)   │    │  Interface (i18n)          │
    │  (instant)        │    │  Weighted random    │    ├─ English (auto-detect)    │
    └───────────────────┘    │  Format string      │    └─ Русский (--lang ru)      │
                             └─────────────────────┘    └──────────────────────────┘
```

## Структура

```
├── src/
│   ├── __init__.py
│   ├── api.py             # FastAPI: 6 endpoints + CORS
│   ├── app.py             # Uvicorn entry point
│   ├── config.py          # Конфиг: источники, пресеты, язык, годы
│   ├── data_loader.py     # Загрузка NDJSON + CSV + IMDb
│   ├── preprocessor.py    # Feature engineering + merge (CSV/IMDb)
│   ├── embedding.py       # SVD (sklearn fallback) / Siamese NN (Keras)
│   ├── classifier.py      # 7 sklearn-классификаторов + cross-validation
│   ├── recommender.py     # Cosine similarity + year filter (post-hoc)
│   ├── model_cache.py     # Save/load моделей (models/*.pkl)
│   ├── imdb_loader.py     # Скачивание + парсинг IMDb TSV.gz
│   ├── i18n.py            # Двуязычный интерфейс (EN/RU)
│   ├── ru_names.py        # Русско-английский маппинг (90+ фильмов)
│   └── main.py            # Entry point — train/load авто-режим
├── tests/
│   └── test_pipeline.py   # Unit-тесты (8 тестов)
├── models/                # Сохранённые модели (gitignored)
│   ├── fast_imdb_all-all.pkl
│   ├── medium_imdb_all-all.pkl
│   └── deep_imdb_all-all.pkl
├── data/imdb/             # Скачанные IMDb TSV.gz (gitignored)
├── run_server.py          # Старт API + проверка среды
├── update_data.py         # Скрипт обновления данных + переобучения
├── requirements.txt
├── pyproject.toml
├── .gitignore
└── README.md
```

## Установка

**Требуется Python 3.13+**

```bash
git clone <repo-url>
cd WikiMovieRec

# На Windows
py -3.13 -m venv .venv-py13
.venv-py13\Scripts\activate

# На Linux/Mac
python3.13 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

## Быстрый старт

### 1. Скачать/обновить IMDb данные

```bash
python update_data.py                    # скачать (300 MB) + статистика
python update_data.py --check            # только статистика
python update_data.py --force            # перескачать всё

# Пересобрать русские и альтернативные названия из локальных источников
python update_titles.py

# Построить обогащённый каталог для текущей medium-модели
python build_title_catalog.py --preset medium

# Дополнительно обогатить названия русскими labels из Wikidata
# (требует доступного Wikidata SPARQL; результаты кэшируются)
python wikidata_titles.py
```

### 2. Обучить модель (первый раз)

```bash
# Быстрая модель (32d, ~1 мин)
python -m src.main --train --preset fast

# Сбалансированная модель (100d, ~2 мин) — дефолт
python -m src.main --train --preset medium

# Глубокая модель (200d, дольше)
python -m src.main --train --preset deep
```

Модели сохраняются в `models/*.pkl`.

### 3. Запуск (авто: загрузить из кэша или обучить если нет)

```bash
python -m src.main                      # авто-режим
python -m src.main --load               # явно загрузить из кэша
```

**Сайт:** всегда используйте `--load` — модель загружается за ~50-100ms.

## Командная строка

| Флаг | Описание |
|------|----------|
| `--train` | Обучить модель с нуля (создаёт `models/*.pkl`) |
| `--load` | Загрузить кэшированную модель (быстрый путь) |
| (без флага) | Авто: если модель есть — загрузить, иначе — обучить |
| `--list-models` | Список сохранённых моделей |
| `--source csv` | Источник метаданных: wiki plots CSV (1901–2017) |
| `--source imdb` | Источник метаданных: IMDb (1894–2026, обновляется) |
| `--preset fast` | Быстрая модель: 32d эмбеддинг, 5 эпох, ~2 MB |
| `--preset medium` | Сбалансированная: 100d, 25 эпох, ~8 MB |
| `--preset deep` | Глубокая: 200d, 50 эпох, ~15 MB |
| `--year-from 2015` | Фильтр по году (включительно) |
| `--year-to 2020` | Фильтр по году (включительно) |
| `--lang en` | Английский интерфейс |
| `--lang ru` | Русский интерфейс |
| `--no-save` | Не сохранять модель после обучения |

Примеры:

```bash
# Обучить модель только для фильмов 2020+
python -m src.main --train --source imdb --year-from 2020 --preset medium

# Загрузить модель и показать на русском
python -m src.main --load --lang ru

# Список моделей
python -m src.main --list-models
```

## Обновление данных и переобучение

IMDb данные обновляются ежедневно, но модель не нужно переобучать каждый день.
Резертренинг добавляет новые фильмы, обновляет метаданные (жанры, режиссёры, рейтинги) и уточняет эмбеддинги.

### Рекомендованная частота

| Режим | Частота | Время старта | Длительность | Что происходит |
|-------|---------|-------------|-------------|---------------|
| **Сбор данных** | ежедневно | 03:00 | ~30 сек | Скачивание свежих IMDb TSV.gz ~300MB. Если файлы уже есть — проверка наличия новых. |
| **Production** | еженедельно (пн) | 02:00 | ~3 мин | Скачивание + переобучение `medium` (~8MB). API перезапускается автоматически (HUP-сигнал). |
| **Полный** | ежемесячно (1-е число) | 01:00 | ~10 мин | Скачивание + переобучение fast + medium + deep. API перезапускается автоматически. |

### Время выполнения (измерено)

| Этап | Время |
|------|-------|
| Скачивание (новые файлы) | 30-60 сек |
| Скачивание (инкрементальное, файлы есть) | <1 сек |
| Парсинг IMDb (title.basics + ratings + crew) | ~35 сек |
| Preprocessing + link index | ~3 сек |
| SVD embeddings fast (32d) | ~1 сек |
| SVD embeddings medium (100d) | ~2 сек |
| SVD embeddings deep (200d) | ~6 сек |
| **Итого medium (--train medium)** | **~45-50 сек** |
| **Итого full (--retrain)** | **~55-60 сек** |

### Команды

```bash
# Скачать данные + статистика
python update_data.py

# Скачать + переобучить medium (production)
python update_data.py --train medium

# Скачать + переобучить конкретные пресеты
python update_data.py --train fast medium

# Скачать + переобучить все 3 пресета (full retrain)
python update_data.py --retrain

# Только переобучить (если данные уже скачены)
python update_data.py --no-download --train medium

# Без статистики (для cron)
python update_data.py --no-download --skip-stats --train medium

# Только проверить статистику
python update_data.py --check

# Принудительно перескачать всё
python update_data.py --force
```

### Флаги update_data.py

| Флаг | Описание |
|------|----------|
| `--no-download` | Пропустить скачивание (использовать существующие данные) |
| `--skip-stats` | Пропустить статистику (ускоряет cron) |
| `--force` | Перескачать все файлы заново |
| `--train [preset...]` | Переобучить указанные пресеты (`--train medium`, `--train fast medium`). Без аргументов = medium |
| `--retrain` | Переобучить все 3 пресета |
| `--check` | Показать статистику без скачивания |

### Расписание (cron / Task Scheduler)

Оптимизированные команды для cron (без лишнего скачивания):

```bash
# Linux crontab
# Daily: собрать IMDb данные (только скачать, без обучения)
0 3 * * * cd /path/to/WikiMovieRec && .venv/bin/python update_data.py --skip-stats >> logs/update.log 2>&1

# Weekly Monday: переобучить medium (production модель) + перезапуск API
0 2 * * 1 cd /path/to/WikiMovieRec && .venv/bin/python update_data.py --no-download --skip-stats --train medium >> logs/retrain.log 2>&1

# Monthly 1st: полное переобучение всех пресетов
0 1 1 * * cd /path/to/WikiMovieRec && .venv/bin/python update_data.py --no-download --skip-stats --retrain >> logs/retrain-all.log 2>&1
```

Windows Task Scheduler:

```bash
# Daily сборка данных
schtasks /create /tn "WikiMovieRec_Data" /sc daily /st 03:00 /tr ^
  "cmd /c cd /d \"C:\path\to\WikiMovieRec\" && .venv-py13\Scripts\python.exe update_data.py --skip-stats"

# Weekly ретренин medium
schtasks /create /tn "WikiMovieRec_Medium" /sc weekly /d MON /st 02:00 /tr ^
  "cmd /c cd /d \"C:\path\to\WikiMovieRec\" && .venv-py13\Scripts\python.exe update_data.py --no-download --skip-stats --train medium"

# Monthly полный ретренин
schtasks /create /tn "WikiMovieRec_Full" /sc monthly /d 1 /st 01:00 /tr ^
  "cmd /c cd /d \"C:\path\to\WikiMovieRec\" && .venv-py13\Scripts\python.exe update_data.py --no-download --skip-stats --retrain"
```

### После переобучения

Перезапустите API сервер — модель перезагрузится при старте (~100ms):

```bash
# Linux — graceful restart
kill -HUP <uvicorn-pid>
# или
systemctl restart wikimovierec

# Windows — перезапуск сервиса
nssm restart WikiMovieRec
# или
net stop WikiMovieRec && net start WikiMovieRec
```

### Логи

```bash
# Ежедневный ротейшн логов (logrotate)
/path/to/WikiMovieRec/logs/*.log {
    daily
    rotate 14
    compress
    missingok
    create 0644 www-data www-data
}
```

## Модель-кэш (`models/`)

Обученные модели сохраняются в `models/` как pickle-файлы:

| Файл | Описание | Размер |
|------|----------|--------|
| `fast_imdb_all-all.pkl` | 32d, все фильмы | ~2.6 MB |
| `medium_imdb_all-all.pkl` | 100d, все фильмы | ~7.6 MB |
| `deep_imdb_all-all.pkl` | 200d, все фильмы | ~15 MB |

Модель содержит **year_map** (movie → year), поэтому для раздела «Свежие» или «2015–2020» **не нужно отдельного обучения** — фильтруйте по году на лету:

```python
rec, meta = load_model(source="imdb")
# Только фильмы с 2020 года
rec.similar_movies("Deadpool (film)", top_k=10, year_from=2020)
```

### API для моделей

```python
from src.model_cache import load_model, save_model, list_models, PRESETS

# Загрузить последнюю модель по источнику
rec, meta = load_model(source="imdb")

# Загрузить конкретный пресет
rec, meta = load_model(preset="fast", source="imdb")

# Сохранить модель вручную
from src.model_cache import save_model
save_model(embeddings, movie_to_idx, idx_to_movie,
           preset="medium", source="imdb", year_from=2015)

# Список моделей
for m in list_models():
    print(f"{m['file']}: {m['preset']}, {m['num_movies']} movies, {m['file_size_mb']} MB")
```

## Двуязычный интерфейс

Язык определяется автоматически из локали системы. Можно задать явно:

```bash
python -m src.main --lang ru
python -m src.main --lang en
```

Или в коде:

```python
from src.i18n import set_locale, lang
set_locale("ru")

rec = load_model(source="imdb")[0]
print(rec.format_recommendation("Deadpool (film)"))
# → Если понравился 'Deadpool (film)', попробуйте 'Wolverine'
```

## Фильтр по годам

Глобальный фильтр для обучения модели (модель будет содержать только фильмы указанного диапазона):

```bash
# Только фильмы 2015–2020
python -m src.main --train --source imdb --year-from 2015 --year-to 2020 --preset medium

# Только новые фильмы (с 2020)
python -m src.main --train --source imdb --year-from 2020 --preset fast
```

## Конфигурация (`src/config.py`)

| Параметр | По умолчанию | Описание |
|----------|-------------|----------|
| `METADATA_SOURCE` | `"csv"` | Источник метаданных: `"csv"` или `"imdb"` |
| `YEAR_FROM` | `None` | Минимальный год (None = без limiti) |
| `YEAR_TO` | `None` | Максимальный год |
| `LANGUAGE` | `None` | Язык: `"ru"`, `"en"`, `None` = автодетект |
| `WORK_OPTION` | 1 | Режим признаков (1–5) |
| `CLASS_OPTION` | 2 | Классификатор (1–7) |
| `IMDB_MIN_VOTES` | 1000 | Мин. кол-во голосов IMDb для фильтра |
| `IMDB_BASE_URL` | `datasets.imdbws.com` | URL IMDb datasets |
| `IMDB_DATA_DIR` | `data/imdb` | Папка файлов IMDb |
| `RANDOM_SEED` | 17 | Seed воспроизводимости |

### Режимы признаков (`WORK_OPTION`)

| # | Признаки |
|---|----------|
| 1 | Все Wikipedia links (дубликаты) + Genre + Director + Cast + Origin + Year |
| 2 | Уникальные Wikipedia links + те же метаданные |
| 3 | Поля инфобокса + метаданные |
| 4 | Ссылки на фильмы из датасета + метаданные |
| 5 | Ссылки на категории Wikipedia + метаданные |

### Классификаторы (`CLASS_OPTION`)

| # | Модель |
|---|--------|
| 1 | SVC |
| 2 | **LinearSVC** (дефолт) |
| 3 | LogisticRegression |
| 4 | SGDClassifier |
| 5 | RidgeClassifier |
| 6 | GradientBoostingClassifier |
| 7 | AdaBoostClassifier |

## Источники данных

| Источник | Годы | Фильмов | Что даёт | Обновление |
|----------|------|---------|----------|------------|
| **CSV** (wiki_movie_plots) | 1901–2017 | 34 886 | Genre, Director, Cast, Origin/Ethnicity | Ручной |
| **IMDb Datasets** | 1894–2026 | 755 945 | Genre, Director, IMDb_Rating, IMDb_Votes | Ежедневно (`update_data.py`) |
| **NDJSON** (wp_movies_10k) | — | 10 000 | Wikipedia outgoing links + Wikipedia ratings | Статичный |

## API

```python
from src.model_cache import load_model
from src.i18n import set_locale, lang

# Настройка языка
set_locale("ru")

# Быстрая загрузка модели
rec, meta = load_model(source="imdb")

# Похожие фильмы
for name, dist in rec.similar_movies("Titanic (1997 film)")[:5]:
    print(f"  {name}  ({dist})")

# Одна рекомендация
print(rec.recommend("Titanic (1997 film)"))

# Форматированная строка (авто-язык)
print(rec.format_recommendation("Titanic (1997 film)"))
# → Если понравился 'Titanic (1997 film)', попробуйте 'Gone with the Wind (film)'
```

## API для сайта (Fast Path)

На старте web-сервера:

```python
from src.model_cache import load_model

# Загрузить модель один раз при старте (~50-100ms)
rec, meta = load_model(source="imdb")

# Для каждого запроса пользователя — мгновенно
def get_recommendation(movie_title: str, top_k: int = 5):
    similar = rec.similar_movies(movie_title, top_k)
    return similar  # список (title, distance)
```

Модель держится в памяти. 100d-эмбеддинг для 10K фильмов = ~8 MB в pickle,
~4 MB в RAM (numpy float64).

## Тесты

```bash
python -m unittest tests.test_pipeline -v
```

## Требования к серверу

| Параметр | Minimum | Recommended |
|----------|---------|-------------|
| Python | 3.13 | 3.13 |
| RAM | 2 GB | 4 GB (для обучения deep) |
| Disk | 500 MB | 1 GB (data + models) |
| CPU | 1 core | 2+ core (для обучения) |
| Выход в интернет | Да (первый запуск ~300 MB) | Только для `update_data.py` |

После первого запуска и обучения моделей интернет не нужен — всё работает офлайн.

## Деплой на сервер

### 1. Первый запуск (подготовка)

```bash
# 1. Python 3.13
py -3.13 -m venv .venv-py13
.venv-py13\Scripts\activate
pip install -r requirements.txt

# 2. IMDb данные (~300 MB)
python update_data.py

# 3. Тренировка моделей
python -m src.main --train --preset fast
python -m src.main --train --preset medium  # production
python -m src.main --train --preset deep    # опционально
```

### 2. Запуск API

```bash
# Development
python run_server.py

# Production (2 воркера)
python run_server.py --production

# Custom preset (fast модель меньше потребляет RAM):
WIKIMODREC_PRESET=fast python run_server.py --production
```

### 3. Переменные окружения

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `WIKIMODREC_HOST` | `0.0.0.0` | Host для привязки |
| `WIKIMODREC_PORT` | `8000` | Порт |
| `WIKIMODREC_WORKERS` | `1` | Кол-во воркеров (production: `2`) |
| `WIKIMODREC_PRESET` | `medium` | Пресет модели (fast/medium/deep) |
| `WIKIMODREC_DEBUG` | `0` | Hot-reload (только dev) |

### 4. Nginx (reverse proxy)

```nginx
server {
    listen 80;
    server_name api.wikimovierec.com;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

### 5. Windows Task Scheduler — автообновление

```bash
schtasks /create /tn "WikiMovieRec_Update" /sc daily /st 03:00 ^
  /tr "cmd /c cd C:\path\to\WikiMovieRec && .venv-py13\Scripts\python.exe update_data.py --retrain"
```

### 6. Swagger UI (документация API)

После запуска сервера:
- `http://localhost:8000/docs` — Swagger UI (интерактивная документация)
- `http://localhost:8000/redoc` — ReDoc

## Технологии

- **Python 3.13+**
- **FastAPI / uvicorn** — API сервер
- **scikit-learn** — классификация, cross-validation, TruncatedSVD
- **scipy** — sparse matrix (fallback embeddings)
- **pandas / numpy** — обработка данных
- **pickle** — кэширование моделей
- **IMDb Non-Commercial Datasets** — `datasets.imdbws.com` (ежедневное обновление)
- **i18n** — EN/RU переводы, автодетект локали