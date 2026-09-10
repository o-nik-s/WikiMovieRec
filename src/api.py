"""FastAPI application for WikiMovieRec."""
import os
import re
import time
import threading
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Optional
from unidecode import unidecode
import unicodedata

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import BaseModel, Field

from src.i18n import set_locale, lang as i18n_lang
from src.model_cache import load_model, list_models as list_cached_models, DEFAULT_PRESET
from src.ru_names import resolve_movie, EN_TO_RU, get_russian_name

# ── Request models ───────────────────────────────────────────────────
class RecommendRequest(BaseModel):
    movie: str = Field(..., min_length=1)
    top_k: int = Field(default=10, ge=1, le=600)
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    genres: Optional[str] = None
    min_rating: Optional[float] = Field(default=None, ge=0, le=10)
    lang: Optional[str] = None


# ── Module-level model state ────────────────────────────────────────
_model = None
_meta = None
_loaded_at: str | None = None
_movie_list: list[str] = []
_year_map: dict[str, int] = {}


def _fmt_name(name: str) -> str:
    """Strip (film), (film series), year, etc. from display names."""
    return re.sub(r'\s*\([^)]*film[^)]*\)\s*', '', name, flags=re.I).strip()


_CIRILLIC_RE = re.compile('[\u0400-\u04FF]')


def _transliterate_name(q: str) -> str:
    """Transliterate Cyrillic to Latin for matching against English titles."""
    if not _CIRILLIC_RE.search(q):
        return q
    raw = unidecode(q)
    return raw.strip() or q


def _extract_query_year(q: str) -> int | None:
    """Extract a target year from the query string for better duplicate filtering."""
    m = re.search(r'\(\d{4}', q)
    if m:
        yr = int(m.group()[1:5])
        if 1900 <= yr <= 2027:
            return yr
    return None


def _init_model():
    """Load the default model at startup. Prefers preset from WIKIMODREC_PRESET env var."""
    global _model, _meta, _loaded_at, _movie_list, _year_map
    try:
        preset = os.environ.get("WIKIMODREC_PRESET", DEFAULT_PRESET)
        # Prefer Keras-trained embeddings (closer to the original notebook).
        _model, _meta = load_model(preset=preset, source="imdb", backend="keras")
        # If the requested preset lacks a keras artifact, fall back to any keras preset.
        if _model is None:
            for candidate in ("fast", "medium", "deep"):
                if candidate == preset:
                    continue
                _model, _meta = load_model(
                    preset=candidate, source="imdb", backend="keras"
                )
                if _model is not None:
                    break
        if _model is None:
            _model, _meta = load_model(preset=preset, source="imdb")
        if _model is None:
            _model, _meta = load_model(source="imdb")
        if _model is not None:
            _loaded_at = datetime.now(timezone.utc).isoformat()
            _movie_list = sorted(_model.idx_to_movie.values())
            _year_map = _model.year_map or {}
    except Exception:
        _model = None
        _meta = None


# ── LRU cache with TTL ─────────────────────────────────────────────
class TTLCache:
    """Simple thread-safe LRU cache with time-to-live."""

    def __init__(self, maxsize: int = 1000, ttl: float = 60):
        self._maxsize = maxsize
        self._ttl = ttl
        self._cache: dict = {}
        self._times: dict = {}
        self._lock = threading.Lock()

    def get(self, key: tuple):
        with self._lock:
            if key in self._cache:
                if time.monotonic() - self._times[key] < self._ttl:
                    return self._cache[key]
                del self._cache[key]
                del self._times[key]
            return None

    def put(self, key: tuple, value):
        with self._lock:
            if len(self._cache) >= self._maxsize and key not in self._cache:
                oldest = min(self._times, key=self._times.get)
                del self._cache[oldest]
                del self._times[oldest]
            self._cache[key] = value
            self._times[key] = time.monotonic()


_rec_cache = TTLCache(maxsize=1000, ttl=60)


def _should_include_year(movie: str, year_from: Optional[int], year_to: Optional[int]) -> bool:
    yr = _year_map.get(movie)
    if yr is None:
        return False
    if year_from is not None and yr < year_from:
        return False
    if year_to is not None and yr > year_to:
        return False
    return True


def _match_model_title(title: str) -> str | None:
    """Resolve a canonical title/alias to the model's suffixed title."""
    if _model is None:
        return None
    if title in _model.movie_to_idx:
        return title
    core = title.lower().split(" (")[0].strip()
    for model_name in _model.movie_to_idx:
        if model_name.lower().split(" (")[0].strip() == core:
            return model_name
    return None


def _resolve_profile_name(raw_name: str) -> str | None:
    """Resolve a user-supplied movie name (RU/EN/alias) to a model title."""
    if _model is None:
        return None
    if raw_name in _model.movie_to_idx:
        return raw_name
    resolved = resolve_movie(raw_name)
    if resolved:
        if resolved in _model.movie_to_idx:
            return resolved
        matched = _match_model_title(resolved)
        if matched:
            return matched
    base_name = re.sub(r'\s*\(\d{4}\s*f\w*\s*\)\s*$', '', raw_name).strip()
    for model_name in _model.movie_to_idx:
        if model_name.lower() == base_name.lower():
            return model_name
    return None


# ── App factory ──────────────────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(
        title="WikiMovieRec",
        description="Movie recommendation API based on Wikipedia link embeddings.",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def startup():
        _init_model()

    def _model_error():
        return {"error": "Model not loaded"}

    static_dir = Path(__file__).parent.parent / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        @app.get("/")
        def root():
            return _serve_index()

        def _serve_index():
            idx = static_dir / "index.html"
            if idx.exists():
                return FileResponse(str(idx))
            return {"error": "Frontend not found"}, 404

    def _set_lang(lg: Optional[str] = None):
        if lg is not None:
            set_locale(lg)

    def _resolve_ru(name: str) -> str:
        """Get Russian name for a movie if known."""
        ru = get_russian_name(name)
        return ru or name

    def _movie_error():
        return JSONResponse(
            status_code=503,
            content={"error": "Model not loaded. Train a model first."},
        )

    @app.get("/api/health")
    def health(lang: Optional[str] = Query(None)):
        _set_lang(lang)
        if _model is None:
            return JSONResponse(
                status_code=503,
                content={"status": "no_model", "error": "Model not loaded."},
            )
        return {
            "status": "ok",
            "model": _meta.preset if _meta else "unknown",
            "movies": _meta.num_movies if _meta else 0,
            "year_map": len(_year_map),
            "loaded_at": _loaded_at,
        }

    @app.get("/api/genres")
    def genres_list():
        """Return list of all available genres."""
        if _model is None:
            return _model_error()
        
        all_genres = set()
        for genre_list in _model.genre_map.values():
            if isinstance(genre_list, list):
                all_genres.update(genre_list)
        
        return {"genres": sorted(all_genres)}

    def _filter_and_build(
        c, sim, matched, seen, year_from, year_to,
        genre_list, min_rating, sample=False, sample_n=12,
    ):
        import random
        name = _model.idx_to_movie[c]
        if name in seen:
            return None, None
        if year_from is not None or year_to is not None:
            yr = _year_map.get(name)
            if yr is None:
                return None, None
            if year_from is not None and yr < year_from:
                return None, None
            if year_to is not None and yr > year_to:
                return None, None
        if genre_list:
            movie_genres = _model.genre_map.get(name, [])
            if not any(g.lower() in [gg.lower() for gg in genre_list] for g in movie_genres):
                return None, None
        if min_rating is not None:
            rating = _model.rating_map.get(name)
            if rating is None or rating < min_rating:
                return None, None
        if sample:
            return round(float(sim), 4), None
        return round(float(sim), 4), {
            "name": name,
            "display_name": _fmt_name(name),
            "ru_name": _resolve_ru(name),
            "similarity": round(float(sim), 4),
            "year": _year_map.get(name),
            "genres": _model.genre_map.get(name, []),
            "rating": _model.rating_map.get(name),
        }

    @app.get("/api/profile")
    def profile(
        movies: str = Query(..., description="Comma-separated movie names"),
        top_k: int = Query(10, ge=1, le=600),
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        genres: Optional[str] = None,
        min_rating: Optional[float] = None,
        lang: Optional[str] = None,
    ):
        """Average embeddings of liked movies → recommend similar."""
        _set_lang(lang)
        if _model is None:
            return _model_error()

        names = [m.strip() for m in movies.split(",") if m.strip()]
        if not names:
            return {"similar": []}

        import numpy as np
        vectors = []
        matched = []
        unmatched = []
        for raw_name in names:
            target = _resolve_profile_name(raw_name)
            if target is not None:
                idx = _model.movie_to_idx[target]
                vectors.append(_model.embeddings[idx])
                matched.append(target)
            else:
                unmatched.append(raw_name)

        if not vectors:
            return {"similar": [], "matched": [], "unmatched": unmatched}

        avg_vec = np.mean(vectors, axis=0)
        sims = np.dot(_model.embeddings, avg_vec)
        ranked = np.argsort(sims)[::-1]

        genre_list = [g.strip() for g in genres.split(",") if g.strip()] if genres else None
        result = []
        seen = set(matched)
        for c in ranked:
            sim, item = _filter_and_build(
                c, sims[c], matched, seen, year_from, year_to,
                genre_list, min_rating,
            )
            if item is not None:
                result.append(item)
                if len(result) >= top_k:
                    break

        result.sort(key=lambda item: item["similarity"], reverse=True)
        return {"similar": result, "matched": matched, "unmatched": unmatched}

    @app.get("/api/profile-sample")
    def profile_sample(
        movies: str = Query(..., description="Comma-separated movie names"),
        sample_n: int = Query(12, ge=1, le=100),
        pool_size: int = Query(720, ge=1, le=6000, description="Pool of best movies to sample from (e.g. 3x table top_k)"),
        sharpness: float = Query(30.0, ge=1.0, le=200.0, description="Softmax sharpness (higher = best more likely)"),
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        genres: Optional[str] = None,
        min_rating: Optional[float] = None,
        lang: Optional[str] = None,
    ):
        """Weighted random sample from all matching movies (probability ∝ similarity)."""
        _set_lang(lang)
        if _model is None:
            return _model_error()

        if sample_n > pool_size:
            return JSONResponse(
                status_code=400,
                content={"error": f"sample_n ({sample_n}) cannot exceed pool_size ({pool_size})"},
            )

        names = [m.strip() for m in movies.split(",") if m.strip()]
        if not names:
            return {"similar": []}

        import numpy as np
        import random
        vectors = []
        matched = []
        unmatched = []
        for raw_name in names:
            target = _resolve_profile_name(raw_name)
            if target is not None:
                idx = _model.movie_to_idx[target]
                vectors.append(_model.embeddings[idx])
                matched.append(target)
            else:
                unmatched.append(raw_name)

        if not vectors:
            return {"similar": [], "matched": [], "unmatched": unmatched}

        avg_vec = np.mean(vectors, axis=0)
        sims = np.dot(_model.embeddings, avg_vec)
        ranked = np.argsort(sims)[::-1]
        genre_list = [g.strip() for g in genres.split(",") if g.strip()] if genres else None
        seen = set(matched)
        pool = pool_size
        candidates = []
        for c in ranked:
            sim, _ = _filter_and_build(
                c, sims[c], matched, seen, year_from, year_to,
                genre_list, min_rating, sample=True,
            )
            if sim is not None:
                candidates.append(c)
            if len(candidates) >= pool:
                break
        if not candidates:
            return {"similar": [], "matched": matched, "unmatched": unmatched}

        # Softmax weights: w_i = exp(sharpness * (sim_i - max_sim)), normalized.
        # Amplifies small similarity differences so best movies are more likely,
        # worst less likely, while keeping every movie pickable (surprise variety).
        cand_sims = np.array([float(sims[c]) for c in candidates])
        max_sim = cand_sims.max()
        w = np.exp(sharpness * (cand_sims - max_sim))
        w = w / w.sum()

        # Sample without replacement: pick one, remove it, repeat.
        k = min(sample_n, len(candidates))
        idx_pool = list(range(len(candidates)))
        w_pool = w.tolist()
        picked = []
        for _ in range(k):
            j = random.choices(range(len(idx_pool)), weights=w_pool, k=1)[0]
            picked.append(candidates[idx_pool.pop(j)])
            w_pool.pop(j)
        result = []
        for c in sorted(picked, key=lambda c: sims[c], reverse=True):
            sim = round(float(sims[c]), 4)
            name = _model.idx_to_movie[c]
            result.append({
                "name": name,
                "display_name": _fmt_name(name),
                "ru_name": _resolve_ru(name),
                "similarity": sim,
                "year": _year_map.get(name),
                "genres": _model.genre_map.get(name, []),
                "rating": _model.rating_map.get(name),
            })
        result.sort(key=lambda item: item["similarity"], reverse=True)
        return {"similar": result, "matched": matched, "unmatched": unmatched}

    def _resolve(movie: str) -> str:
        """Resolve russian/alias name to English title in model."""
        resolved = resolve_movie(movie)
        if resolved:
            if resolved in _model.movie_to_idx:
                return resolved
            # resolve_movie may return a suffixed title (e.g. "Titanic (1997 film)")
            # while the model stores the bare title ("Titanic").
            matched = _match_model_title(resolved)
            if matched:
                return matched
        if movie in _model.movie_to_idx:
            return movie
        # Fuzzy fallback
        q_lower = movie.lower()
        best_score = 0.6
        best_name = None
        for name in _movie_list:
            if name == movie:
                return name
            ratio = SequenceMatcher(None, q_lower, name.lower()).ratio()
            if ratio > best_score:
                best_score = ratio
                best_name = name
        return best_name or movie

    @app.post("/api/recommend")
    def recommend(body: RecommendRequest):
        _set_lang(body.lang)
        if _model is None:
            return _model_error()

        movie = _resolve(body.movie)
        if movie not in _model.movie_to_idx:
            return JSONResponse(
                status_code=404,
                content={"error": i18n_lang("movie_not_found", movie=body.movie)},
            )

        genre_list = [g.strip() for g in body.genres.split(",") if g.strip()] if body.genres else None
        cache_key = ("recommend", movie, body.top_k, body.year_from, body.year_to, tuple(genre_list or []), body.min_rating)
        cached = _rec_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            suggestion = _model.format_recommendation(
                movie, body.top_k, body.year_from, body.year_to,
                genres=genre_list, min_rating=body.min_rating,
            )
            similar = _model.similar_movies(
                movie, body.top_k, body.year_from, body.year_to,
                genres=genre_list, min_rating=body.min_rating,
            )
        except KeyError:
            return JSONResponse(
                status_code=404,
                content={"error": i18n_lang("movie_not_found", movie=movie)},
            )

        recs = [
            {"name": name, "ru_name": _resolve_ru(name), "similarity": dist,
             "year": _year_map.get(name),
             "genres": _model.genre_map.get(name, []),
             "rating": _model.rating_map.get(name)}
            for name, dist in similar
        ]
        result = {"recommendations": recs, "suggestion": suggestion}
        _rec_cache.put(cache_key, result)
        return result

    @app.get("/api/similar")
    def similar(
        movie: str,
        top_k: int = Query(10, ge=1, le=600),
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        genres: Optional[str] = None,
        min_rating: Optional[float] = None,
        lang: Optional[str] = None,
    ):
        _set_lang(lang)
        if _model is None:
            return _model_error()

        resolved = _resolve(movie)
        if resolved not in _model.movie_to_idx:
            return JSONResponse(
                status_code=404,
                content={"error": i18n_lang("movie_not_found", movie=movie)},
            )

        genre_list = [g.strip() for g in genres.split(",") if g.strip()] if genres else None
        cache_key = ("similar", resolved, top_k, year_from, year_to, tuple(genre_list or []), min_rating)
        cached = _rec_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            res = _model.similar_movies(resolved, top_k, year_from, year_to,
                                        genres=genre_list, min_rating=min_rating)
        except KeyError:
            return JSONResponse(
                status_code=404,
                content={"error": i18n_lang("movie_not_found", movie=resolved)},
            )

        out = {"similar": [{"name": n, "display_name": _fmt_name(n), "ru_name": _resolve_ru(n), "similarity": round(d, 4),
                    "year": _year_map.get(n),
                            "genres": _model.genre_map.get(n, []),
                            "rating": _model.rating_map.get(n)} for n, d in res]}
        return out

    @app.get("/api/search")
    def search(q: str, lang: Optional[str] = None):
        _set_lang(lang)
        if _model is None:
            return _model_error()

        if not q or len(q) < 2:
            return {"matches": [], "count": 0}

        target_year = _extract_query_year(q)
        # Strip year from query for better fuzzy matching
        q_clean = re.sub(r'\(\d{4}\)', '', q).strip().lower()
        if not q_clean and target_year:
            q_clean = q.lower()

        # 1. Check Russian title mapping first
        resolved = resolve_movie(q)
        resolved_model_title = _match_model_title(resolved) if resolved else None
        if resolved_model_title:
            resolved = resolved_model_title
            res_year = _year_map.get(resolved)
            year_bonus = 0.05 if target_year and res_year and abs(res_year - target_year) <= 2 else 0
            matches = [
                {"name": resolved, "display_name": _fmt_name(resolved), "ru_name": _resolve_ru(resolved), "year": res_year, "score": 1.0 + year_bonus},
            ]
            scored = []
            for name in _movie_list:
                if name == resolved:
                    continue
                ratio = SequenceMatcher(None, q_clean, name.lower()).ratio()
                if ratio >= 0.4:
                    year_bonus = 0.03 if target_year and _year_map.get(name) and abs(_year_map.get(name) - target_year) <= 1 else 0
                    scored.append((name, round(ratio + year_bonus, 4)))
            scored.sort(key=lambda x: x[1], reverse=True)
            for n, s in scored[:19]:
                matches.append({"name": n, "display_name": _fmt_name(n), "ru_name": _resolve_ru(n), "year": _year_map.get(n), "score": min(s, 1.0)})
            return {"matches": matches, "count": len(matches)}

        # 2. Transliterate Cyrillic query for fallback matching
        is_cyrillic = _CIRILLIC_RE.search(q)
        q_latin = _transliterate_name(q_clean) if is_cyrillic else q_clean

        # 3. Fuzzy English search with transliteration
        scored: list[tuple[str, float]] = []
        q_words = [w for w in q_clean.split() if len(w) >= 3]
        q_words_latin = [w for w in q_latin.split() if len(w) >= 3] if q_latin else []
        for name in _movie_list:
            nm = name.lower()
            nm_core = nm.split('(')[0].strip()
            # Use transliterated query for Cyrillic matching
            match_query = q_latin if is_cyrillic else q_clean
            ratio = SequenceMatcher(None, match_query, nm_core).ratio()
            # Containment checks on core name
            if q_clean in nm_core:
                ratio = max(ratio, 0.95)
            if is_cyrillic and q_latin and q_latin in nm_core:
                ratio = max(ratio, 0.95)
            if nm_core.startswith(q_clean):
                ratio = max(ratio, 0.92)
            if is_cyrillic and q_latin and nm_core.startswith(q_latin):
                ratio = max(ratio, 0.92)
            # Word-level containment
            all_words = list(set(q_words + q_words_latin))
            if any(w in nm_core for w in all_words if len(w) >= 4):
                ratio = max(ratio, 0.85)
            if any(nm_core.startswith(w) for w in all_words):
                ratio = max(ratio, 0.85)
            minimum_score = 0.65 if is_cyrillic else 0.4
            if ratio >= minimum_score:
                year_bonus = 0.05 if target_year and _year_map.get(name) and abs(_year_map.get(name) - target_year) <= 1 else 0
                scored.append((name, round(ratio + year_bonus, 4)))

        scored.sort(key=lambda x: x[1], reverse=True)
        # Deduplicate by core title (keep best matching year)
        seen_titles = {}
        for n, s in scored:
            core = n.lower().split('(')[0].strip()
            if core not in seen_titles or s > seen_titles[core][1]:
                seen_titles[core] = (n, s)
        
        top = list(seen_titles.values())[:20]
        matches = [{"name": n, "display_name": _fmt_name(n), "ru_name": _resolve_ru(n), "year": _year_map.get(n), "score": min(s, 1.0)} for n, s in top]
        return {"matches": matches, "count": len(matches)}

    @app.get("/api/movies")
    def movies(
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        genre: Optional[str] = None,
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        lang: Optional[str] = None,
    ):
        _set_lang(lang)
        if _model is None:
            return _model_error()

        filtered = _movie_list
        if year_from is not None or year_to is not None:
            filtered = [
                m for m in filtered
                if _should_include_year(m, year_from, year_to)
            ]

        total = len(filtered)
        page = filtered[offset: offset + limit]
        result = {
            "movies": [{"name": m, "ru_name": _resolve_ru(m), "year": _year_map.get(m)} for m in page],
            "total": total,
        }
        return result

    @app.get("/api/ru-names")
    def ru_names(
        names: str = Query(..., description="Comma-separated movie names"),
        lang: Optional[str] = None,
    ):
        """Authoritatively resolve Russian display names for a list of movies."""
        _set_lang(lang)
        if _model is None:
            return _model_error()
        out = {}
        for raw in [m.strip() for m in names.split(",") if m.strip()]:
            out[raw] = _resolve_ru(raw)
        return {"names": out}

    @app.get("/api/models")
    def models(lang: Optional[str] = None):
        _set_lang(lang)
        all_models = list_cached_models()
        return {"models": all_models}

    return app