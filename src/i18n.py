"""Internationalization — EN / RU strings for the pipeline.

Usage:
    from src.i18n import get_locale, lang, _

    locale = get_locale()  # auto-detect or explicit
    print(lang("hello"))   # "Hello" / "Привет"
    print(lang("similar", movie="Inception"))
"""
import locale as _locale
import os

from src.config import LANGUAGE as _CFG_LANGUAGE

# --------------- translation catalogue ---------------

_MESSAGES: dict[str, dict[str, str]] = {
    "hello": {
        "en": "WikiMovieRec — Movie Recommender",
        "ru": "WikiMovieRec — Система рекомендаций фильмов",
    },
    "loading_data": {
        "en": "Loading data (metadata={source})…",
        "ru": "Загрузка данных (источник={source})…",
    },
    "preprocessing": {
        "en": "Preprocessing…",
        "ru": "Предобработка…",
    },
    "total_movies": {
        "en": "Total movies: {n}",
        "ru": "Всего фильмов: {n}",
    },
    "work_option": {
        "en": "Work option ({n}): {desc}",
        "ru": "Вариант признаков ({n}): {desc}",
    },
    "building_link_index": {
        "en": "Building link index…",
        "ru": "Построение индекса ссылок…",
    },
    "link_vocab": {
        "en": "Links vocabulary: {links}, Movies: {movies}",
        "ru": "Словарь ссылок: {links}, Фильмов: {movies}",
    },
    "building_pairs": {
        "en": "Building training pairs…",
        "ru": "Построение обучающих пар…",
    },
    "total_pairs": {
        "en": "Total pairs: {n}",
        "ru": "Всего пар: {n}",
    },
    "training_embeddings": {
        "en": "Training embeddings ({epochs} epochs)…",
        "ru": "Обучение эмбеддингов ({epochs} эпох)…",
    },
    "embeddings_shape": {
        "en": "Embeddings shape: {shape}",
        "ru": "Форма эмбеддингов: {shape}",
    },
    "classifier": {
        "en": "Classifier: {name}",
        "ru": "Классификатор: {name}",
    },
    "cv_accuracy": {
        "en": "CV accuracy: {mean:.4f} (+/- {std:.4f})",
        "ru": "CV accuracy: {mean:.4f} (+/- {std:.4f})",
    },
    "cv_f1": {
        "en": "CV f1: {mean:.4f} (+/- {std:.4f})",
        "ru": "CV f1: {mean:.4f} (+/- {std:.4f})",
    },
    "top_ranked": {
        "en": "Top 10 ranked movies:",
        "ru": "Топ-10 фильмов по рейтингу:",
    },
    "demo_header": {
        "en": "=== Demo ===",
        "ru": "=== Демо ===",
    },
    "similar_to": {
        "en": "Similar to '{movie}':",
        "ru": "Похожие на '{movie}':",
    },
    "distance": {
        "en": "distance",
        "ru": "расстояние",
    },
    "if_you_like": {
        "en": "If you like '{movie}', try '{rec}'",
        "ru": "Если понравился '{movie}', попробуйте '{rec}'",
    },
    "no_rec": {
        "en": "No recommendations for: {movie}",
        "ru": "Нет рекомендаций для: {movie}",
    },
    "movie_not_found": {
        "en": "Movie not found: {movie}",
        "ru": "Фильм не найден: {movie}",
    },
    "year_filter": {
        "en": "Year range: {yr_from} – {yr_to}",
        "ru": "Диапазон годов: {yr_from} – {yr_to}",
    },
    "source_csv": {
        "en": "csv (wiki plots)",
        "ru": "csv (описания Википедии)",
    },
    "source_imdb": {
        "en": "imdb",
        "ru": "imdb",
    },
}


def get_locale(cfg: str | None = None) -> str:
    """Return 'en' or 'ru'.

    Priority: explicit cfg > LANGUAGE config > system locale > 'en'.
    """
    if cfg is not None:
        return cfg
    if _CFG_LANGUAGE is not None:
        return _CFG_LANGUAGE
    # Detect from system locale
    try:
        loc = _locale.getdefaultlocale()[0] or ""
        if loc.startswith("ru"):
            return "ru"
    except Exception:
        pass
    # Fallback: check LC_ALL, LANG env vars
    for env in ("LC_ALL", "LANG", "LANGUAGE"):
        val = os.environ.get(env, "")
        if val.startswith("ru"):
            return "ru"
    return "en"


# Module-level locale (set by main or get_locale)
_current_locale: str = "en"


def set_locale(loc: str):
    """Set the active locale for lang()."""
    global _current_locale
    _current_locale = loc if loc in ("en", "ru") else "en"


def lang(key: str, **kwargs) -> str:
    """Look up a translated string and format with kwargs."""
    msg = _MESSAGES.get(key, {}).get(_current_locale, key)
    if kwargs:
        try:
            return msg.format(**kwargs)
        except (KeyError, ValueError):
            return msg
    return msg


# Alias for quick inline use
_ = lang