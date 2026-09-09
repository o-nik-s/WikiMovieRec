# Оптимизированная структура проекта для сервера

## Текущие проблемы

1. **Множество виртуальных окружений**: .venv, .venv-py12, .venv-py13
2. **Смешанные файлы в корне**: логи, временные файлы, скрипты
3. **Неоптимальная структура для сервера**
4. **Несовместимость версий Python**: pyproject.toml требует 3.13+, но TensorFlow работает с 3.12

## Предлагаемая структура

```
/home/on.suslova/wiki-movie-rec/
├── .env                          # Переменные окружения
├── .python-version              # Python 3.12
├── pyproject.toml              # Исправленный для Python 3.12
├── requirements.txt            # Основные зависимости
├── requirements-keras.txt      # TensorFlow/Keras зависимости
├── README.md
├── run_server.py
├── scripts/                    # Скрипты администрирования
│   ├── deploy.sh
│   ├── update_data.py
│   ├── train_model.py
│   └── backup.sh
├── src/                        # Исходный код
│   ├── __init__.py
│   ├── api.py
│   ├── app.py
│   ├── config.py
│   ├── data_loader.py
│   ├── embedding.py
│   ├── imdb_loader.py
│   ├── model_cache.py
│   ├── preprocessor.py
│   ├── recommender.py
│   └── i18n.py
├── static/                     # Веб-интерфейс
│   ├── index.html
│   └── style.css
├── config/                     # Конфигурации
│   ├── production.yml
│   ├── development.yml
│   └── logging.yml
├── models/                     # Обученные модели
│   ├── fast_keras_imdb_all-all.pkl
│   ├── medium_keras_imdb_all-all.pkl
│   └── deep_keras_imdb_all-all.pkl
├── data/                       -> /data/wiki-movie-data/ (симлинк)
├── logs/                       # Логи приложения
│   ├── api.log
│   └── errors.log
├── notebooks/                  # Исследовательские ноутбуки
│   └── Система рекомендаций по фильмам.ipynb
└── tests/                      # Тесты
    └── test_pipeline.py
```

## Изменения

### 1. Исправление pyproject.toml
- Изменить `requires-python = ">=3.13"` на `requires-python = ">=3.12"`
- Добавить TensorFlow в основные зависимости или создать отдельный файл

### 2. Разделение зависимостей
- `requirements.txt` - основные зависимости (FastAPI, scikit-learn, pandas)
- `requirements-keras.txt` - TensorFlow/Keras зависимости

### 3. Организация скриптов
- Все скрипты администрирования в `scripts/`
- Логи в `logs/`
- Конфигурации в `config/`

### 4. Симлинк для данных
- Большие файлы данных хранить в `/data/wiki-movie-data/`
- Создать симлинк `data/ -> /data/wiki-movie-data/`

### 5. Управление окружением
- `.env` - переменные окружения
- `.python-version` - указание версии Python

## Преимущества

1. **Чистота**: Корень проекта содержит только основные файлы
2. **Масштабируемость**: Легко добавлять новые скрипты и конфигурации
3. **Простота развертывания**: Четкая структура для сервера
4. **Совместимость**: Python 3.12 для TensorFlow
5. **Логирование**: Централизованное хранение логов

## Миграция

### Шаг 1: Создание структуры
```bash
mkdir -p scripts config logs notebooks
```

### Шаг 2: Перемещение файлов
```bash
mv update_data.py validate_data.py scripts/
mv *.log *.err logs/ 2>/dev/null || true
```

### Шаг 3: Исправление pyproject.toml
```toml
requires-python = ">=3.12"
```

### Шаг 4: Создание конфигураций
```bash
cat > config/production.yml << 'EOF'
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
EOF
```

## Для сервера

### Создание структуры на сервере
```bash
ssh root@217.144.186.110 "mkdir -p /home/on.suslova/wiki-movie-rec/{src,static,logs,config,scripts,notebooks,models}"
```

### Симлинк для данных
```bash
ssh root@217.144.186.110 "mkdir -p /data/wiki-movie-data && ln -sf /data/wiki-movie-data /home/on.suslova/wiki-movie-rec/data"
```

## Обновление скриптов развертывания

Скрипты развертывания будут обновлены для работы с новой структурой.