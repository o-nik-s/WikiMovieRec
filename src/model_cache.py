"""Model caching — save/load trained recommender artifacts.

Models are stored as pickle files in ./models/ with naming convention:
    models/<preset>_<source>_<yr_from>-<yr_to>.pkl

Presets define embedding quality:
    fast   — 32-dim embedding, ~1 sec load, quick recommendations
    medium — 100-dim (default), balance quality vs size
    deep   — 200-dim, best quality, largest file

A model file contains:
    embeddings    — np.ndarray (num_movies × emb_size)
    movie_to_idx  — dict[str, int]
    idx_to_movie  — dict[int, str]
    meta          — dict with source, year range, preset, file size, etc.
"""
import logging
import os
import pickle
import sys
import json
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from src.recommender import MovieRecommender

log = logging.getLogger(__name__)

MODEL_DIR = "models"
ENRICHED_CATALOG = os.path.join("data", "imdb", "movie_titles_enriched.jsonl")

# Preset definitions: {preset: (embedding_size, epochs)}
PRESETS = {
    "fast":   {"embedding_size": 32,  "epochs": 5},
    "medium": {"embedding_size": 100, "epochs": 25},    # default
    "deep":   {"embedding_size": 200, "epochs": 50},
}
DEFAULT_PRESET = "medium"


def _model_path(
    preset: str,
    source: str,
    year_from: int | None,
    year_to: int | None,
    backend: str | None = None,
) -> str:
    yr_from = year_from or "all"
    yr_to = year_to or "all"
    stem = f"{preset}_{backend}" if backend else preset
    base = f"{stem}_{source}_{yr_from}-{yr_to}.pkl"
    return os.path.join(MODEL_DIR, base)


@dataclass
class ModelMeta:
    preset: str
    source: str
    year_from: int | None
    year_to: int | None
    num_movies: int
    embedding_size: int
    epochs: int
    train_date: str
    file_size_mb: float = 0.0


def save_model(
    embeddings: np.ndarray,
    movie_to_idx: dict,
    idx_to_movie: dict,
    year_map: dict[str, int] | None = None,
    preset: str = DEFAULT_PRESET,
    source: str = "imdb",
    year_from: int | None = None,
    year_to: int | None = None,
    epochs: int = 25,
    genre_map: dict[str, list] | None = None,
    rating_map: dict[str, float] | None = None,
    backend: str | None = None,
) -> str:
    """Save trained embeddings to disk. Returns path to saved .pkl file."""
    os.makedirs(MODEL_DIR, exist_ok=True)
    path = _model_path(preset, source, year_from, year_to, backend)

    meta = ModelMeta(
        preset=preset,
        source=source,
        year_from=year_from,
        year_to=year_to,
        num_movies=len(embeddings),
        embedding_size=embeddings.shape[1],
        epochs=epochs,
        train_date=datetime.now().isoformat(),
    )
    data = {
        "embeddings": embeddings,
        "movie_to_idx": movie_to_idx,
        "idx_to_movie": idx_to_movie,
        "backend": backend,
        "year_map": year_map or {},
        "genre_map": genre_map or {},
        "rating_map": rating_map or {},
        "meta": meta,
    }
    with open(path, "wb") as f:
        pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)

    sz = os.path.getsize(path) / 1024 / 1024
    meta.file_size_mb = round(sz, 2)
    log.info("Model saved: %s (%.2f MB, %d movies, %d-dim)",
             os.path.basename(path), sz, meta.num_movies, meta.embedding_size)
    return path


def load_model(
    preset: str | None = None,
    source: str | None = None,
    backend: str | None = None,
) -> tuple:
    """Load a cached model. Returns (MovieRecommender, ModelMeta).

    Year filtering is done at recommendation time via year_map embedded
    in the model file — no separate models per year range needed.

    backend: optional 'keras' or 'svd'. If None, prefers 'keras' when
    available, then falls back to any preset file (legacy/SVD).
    """
    candidates = []
    if os.path.isdir(MODEL_DIR):
        for f in os.listdir(MODEL_DIR):
            if f.endswith(".pkl"):
                candidates.append(os.path.join(MODEL_DIR, f))

    if not candidates:
        log.warning("No model files found in %s. Train first.", MODEL_DIR)
        return None, None

    # Exact backend-aware match first
    if preset and source is not None and backend:
        want = _model_path(preset, source, None, None, backend)
        if want in candidates:
            return _load_single(want)

    # Prefer keras whenever explicitly requested
    if backend == "keras" and preset:
        for c in candidates:
            if c.startswith(f"models/{preset}_keras_"):
                return _load_single(c)

    # Explicit backend requested but no exact match: do not fall back to a
    # different backend (e.g. keras request should never return an SVD model).
    if backend is not None:
        log.warning(
            "No model matching preset=%r source=%r backend=%r in %s",
            preset, source, backend, MODEL_DIR,
        )
        return None, None

    # Fuzzy: match source
    if source is not None:
        for c in candidates:
            if f"_{source}_" in os.path.basename(c):
                return _load_single(c)

    if preset:
        for c in candidates:
            if c.startswith(f"models/{preset}_"):
                return _load_single(c)

    # Most recently modified
    newest = max(candidates, key=os.path.getmtime)
    return _load_single(newest)


def _load_single(path: str) -> tuple:
    with open(path, "rb") as f:
        raw = pickle.load(f)
    embeddings = raw["embeddings"]
    movie_to_idx = raw["movie_to_idx"]
    idx_to_movie = raw["idx_to_movie"]
    year_map = raw.get("year_map", {})
    genre_map = raw.get("genre_map", {})
    rating_map = raw.get("rating_map", {})
    genre_map, rating_map = _enrich_maps_from_catalog(
        movie_to_idx, genre_map, rating_map
    )
    meta = raw["meta"]
    rec = MovieRecommender(
        embeddings, movie_to_idx, idx_to_movie,
        year_map=year_map if year_map else None,
        genre_map=genre_map if genre_map else None,
        rating_map=rating_map if rating_map else None,
    )
    log.info("Model loaded: %s (%d movies, %d-dim, year_map=%d, genre=%d, rating=%d, trained %s)",
             os.path.basename(path), meta.num_movies, meta.embedding_size,
             len(year_map), len(genre_map), len(rating_map), meta.train_date[:10])
    return rec, meta


def _enrich_maps_from_catalog(
    movie_to_idx: dict,
    genre_map: dict[str, list],
    rating_map: dict[str, float],
) -> tuple[dict[str, list], dict[str, float]]:
    """Fill missing metadata from the staged local IMDb catalog."""
    if not os.path.exists(ENRICHED_CATALOG):
        return genre_map, rating_map
    try:
        with open(ENRICHED_CATALOG, "r", encoding="utf-8") as fh:
            for line in fh:
                item = json.loads(line)
                model_title = item.get("model_title")
                if model_title not in movie_to_idx:
                    continue
                genres = item.get("genres") or []
                if model_title not in genre_map and genres:
                    genre_map[model_title] = genres
                rating = item.get("rating")
                if model_title not in rating_map and rating is not None:
                    rating_map[model_title] = float(rating)
    except (OSError, ValueError, TypeError):
        log.exception("Could not enrich model metadata from %s", ENRICHED_CATALOG)
    return genre_map, rating_map


def list_models() -> list[dict]:
    """List all cached models with metadata."""
    models = []
    if not os.path.isdir(MODEL_DIR):
        return models
    for f in sorted(os.listdir(MODEL_DIR)):
        if not f.endswith(".pkl"):
            continue
        path = os.path.join(MODEL_DIR, f)
        with open(path, "rb") as fh:
            raw = pickle.load(fh)
        m = raw["meta"]
        models.append({
            "file": f,
            "preset": m.preset,
            "source": m.source,
            "year_from": m.year_from,
            "year_to": m.year_to,
            "num_movies": m.num_movies,
            "embedding_size": m.embedding_size,
            "train_date": m.train_date,
            "file_size_mb": round(os.path.getsize(path) / 1024 / 1024, 2),
        })
    return models