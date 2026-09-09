"""
WikiMovieRec — Movie Recommender from Wikipedia Outgoing Links

Two modes:
  TRAIN  — full pipeline (load → preprocess → train embeddings → save model)
  LOAD   — load pre-trained model from disk (0.1 sec) → fast recommendations

Usage:
  # Auto: load if model exists, train if not
  python -m src.main --source imdb

  # Force train (saves model to ./models/)
  python -m src.main --train --source imdb --preset medium

  # Load cached model (fast path for production)
  python -m src.main --load

  # Train with year range + specific preset
  python -m src.main --train --source imdb --year-from 2015 --preset deep

  # List available models
  python -m src.main --list-models
"""
import argparse
import logging
import sys

import numpy as np

from src.config import *
from src.data_loader import load_all
from src.model_cache import load_model, save_model, list_models, PRESETS, DEFAULT_PRESET, MODEL_DIR

def extract_year_from_title(title: str) -> int | None:
    r"""Extract release year from title like 'Titanic (1997 film)' or 'Deadpool (film)'.
    
    Note: Uses r'\(\d{4}' because closing paren may not be right after the year
    (e.g., 'Titanic (1997 film)', not '(1997)').
    Returns the year if found, None otherwise.
    """
    import re
    match = re.search(r'\(\d{4}', title)
    if match:
        yr = int(match.group()[1:5])
        if 1900 <= yr <= 2027:
            return yr
    return None
from src.preprocessor import build_features, merge_with_plots
from src.embedding import set_seeds, build_link_index, build_pairs, EmbeddingModel
from src.classifier import get_classifier, cross_validate
from src.recommender import MovieRecommender

logging.basicConfig(
   level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)


def train(
    work_option: int = WORK_OPTION,
    class_option: int = CLASS_OPTION,
    preset: str = DEFAULT_PRESET,
    meta_source: str = METADATA_SOURCE,
    year_from: int | None = None,
    year_to: int | None = None,
    locale: str | None = None,
    save: bool = True,
) -> tuple:
    """Full training pipeline. Returns (MovieRecommender, embeddings, meta dicts)."""
    from src.i18n import get_locale, lang, set_locale
    set_locale(get_locale(locale))

    preset_cfg = PRESETS[preset]
    emb_size = preset_cfg["embedding_size"]
    epochs = preset_cfg["epochs"]

    yr_label = lang("year_filter",
                    yr_from=year_from or "…", yr_to=year_to or "…")
    log.info("%s (preset=%s, emb=%d, epochs=%d)", yr_label, preset, emb_size, epochs)

    # 1. Load & preprocess
    log.info(lang("loading_data", source=meta_source))
    movies_df, metadata_df = load_all(
        source=meta_source, year_from=year_from, year_to=year_to,
    )
    log.info(lang("preprocessing"))
    movies_df = build_features(movies_df)
    merged_df = merge_with_plots(movies_df, metadata_df)

    year_col = "Year" if "Year" in merged_df.columns else \
               "Release Year" if "Release Year" in merged_df.columns else None
    if year_col and (year_from is not None or year_to is not None):
        import pandas as pd
        years = pd.to_numeric(merged_df[year_col], errors="coerce")
        mask = years.notna()
        if year_from is not None:
            mask &= years >= year_from
        if year_to is not None:
            mask &= years <= year_to
        merged_df = merged_df[mask].copy()
        log.info("Year-filtered training movies: %d", len(merged_df))

    # Clean names: strip (film), (2015 film), etc.
    import re
    merged_df["Name"] = merged_df["Name"].apply(lambda n: re.sub(r'\s*\([^)]*\)\s*$', '', str(n)).strip())
    movies = list(merged_df.to_records(index=False))

    # Build year_map: NDJSON movie name → year from metadata
    year_map = {}
    names_list = merged_df["Name"].values
    if year_col:
        import pandas as pd
        yr = pd.to_numeric(merged_df[year_col], errors="coerce")
        valid = yr.dropna()
        for name_str, y in zip(names_list[yr.notna()], valid):
            year_map[name_str] = int(y)
    log.info("Year map: %d / %d from metadata", len(year_map), len(merged_df))
    # Fix wrong years: use title-parsed year as priority if metadata year is clearly wrong
    fixed_count = 0
    for title in names_list:
        parsed_year = extract_year_from_title(title)
        if parsed_year is not None:
            existing = year_map.get(title)
            # Use parsed year if metadata year is clearly wrong (in future or >10 years off)
            if existing is None or abs(existing - parsed_year) > 5 or existing > 2026:
                year_map[title] = parsed_year
                fixed_count += 1
    log.info("Year map: %d fixed from title parsing, total: %d / %d",
             fixed_count, len(year_map), len(merged_df))
    genre_map = {
        name: genres
        for name, genres in zip(merged_df["Name"], merged_df["GenreTokens"])
        if isinstance(genres, (list, tuple)) and genres
    }
    rating_map = {}
    if "IMDb_Rating" in merged_df.columns:
        import pandas as pd
        ratings = pd.to_numeric(merged_df["IMDb_Rating"], errors="coerce")
        rating_map = {
            name: float(rating)
            for name, rating in zip(merged_df["Name"], ratings)
            if pd.notna(rating)
        }
    log.info("Metadata maps: genres=%d, ratings=%d", len(genre_map), len(rating_map))
    num_movies = len(movies)
    log.info(lang("total_movies", n=num_movies))

    # 2. Link vocabulary
    log.info(lang("building_link_index"))
    movie_to_idx, link_to_idx, top_links = build_link_index(movies, work_option)
    idx_to_movie = {v: k for k, v in movie_to_idx.items()}
    log.info(lang("link_vocab", links=len(top_links), movies=len(movie_to_idx)))

    # 3. Training pairs
    log.info(lang("building_pairs"))
    pairs = build_pairs(movies, work_option, link_to_idx, movie_to_idx)
    log.info(lang("total_pairs", n=len(pairs)))

    # 4. Embeddings
    log.info(lang("training_embeddings", epochs=epochs))
    emb_model = EmbeddingModel(len(top_links), num_movies, emb_size)
    emb_model.train(pairs, epochs=epochs)
    embeddings = emb_model.get_embeddings()
    log.info(lang("embeddings_shape", shape=str(embeddings.shape)))

    # Save model for fast loading later
    if save:
        path = save_model(
            embeddings, movie_to_idx, idx_to_movie,
            year_map=year_map, genre_map=genre_map, rating_map=rating_map,
            preset=preset, source=meta_source,
            year_from=year_from, year_to=year_to,
            epochs=epochs,
            backend=emb_model.backend,
        )
        log.info("Saved to %s", path)

    rec = MovieRecommender(
        embeddings, movie_to_idx, idx_to_movie,
        year_map=year_map, genre_map=genre_map, rating_map=rating_map,
    )
    return rec


def load(
    preset: str | None = None,
    source: str | None = None,
    locale: str | None = None,
) -> MovieRecommender | None:
    """Load a cached model. Fast path — no training."""
    from src.i18n import get_locale, lang, set_locale
    set_locale(get_locale(locale))

    rec, meta = load_model(
        preset=preset, source=source,
    )
    if rec is None:
        log.warning("No model found. Use --train first.")
        return None
    return rec


def demo(rec: MovieRecommender):
    """Print similarity demo."""
    from src.i18n import lang
    print(f"\n{lang('demo_header')}")
    for movie in ["Deadpool (film)", "The Revenant (2015 film)", "Suicide Squad (film)"]:
        if movie in rec.movie_to_idx:
            print(f"\n{lang('similar_to', movie=movie)}")
            for name, dist in rec.similar_movies(movie, top_k=5):
                print(f"  {name}  ({lang('distance')}: {dist})")
    # Format demo
    if "Deadpool (film)" in rec.movie_to_idx:
        print(f"\n{rec.format_recommendation('Deadpool (film)')}")


def main():
    parser = argparse.ArgumentParser(description="WikiMovieRec pipeline")

    # Mode
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--train", action="store_true",
                      help="Train model from scratch (slow)")
    mode.add_argument("--load", action="store_true",
                      help="Load cached model (fast, requires prior --train)")
    mode.add_argument("--list-models", action="store_true",
                      help="List available cached models")

    # Config
    parser.add_argument("--source", choices=["csv", "imdb"],
                        default=METADATA_SOURCE)
    parser.add_argument("--preset", choices=list(PRESETS.keys()),
                        default=DEFAULT_PRESET,
                        help="Model size: fast (32d), medium (100d), deep (200d)")
    parser.add_argument("--work-option", type=int, default=WORK_OPTION)
    parser.add_argument("--no-save", action="store_true",
                        help="Don't save model after training")
    parser.add_argument("--year-from", type=int, default=None)
    parser.add_argument("--year-to", type=int, default=None)
    parser.add_argument("--lang", "--locale", choices=["en", "ru"],
                        default=None)
    args = parser.parse_args()

    # List models
    if args.list_models:
        models = list_models()
        if not models:
            print(f"No models in {MODEL_DIR}/. Train first with --train.")
            return
        print(f"\nModels in {MODEL_DIR}/:")
        for m in models:
            yr = f"{m['year_from'] or '…'} – {m['year_to'] or '…'}"
            print(f"  {m['file']:45s}  {m['preset']:6s}  "
                  f"{m['num_movies']:>6} movies  {m['embedding_size']:>3}d  "
                  f"{m['file_size_mb']:>6.1f} MB  {m['train_date'][:10]}  {yr}")
        return

    # Auto mode: load if exists, train if not
    if not args.train and not args.load:
        rec, meta = load_model(source=args.source)
        if rec is not None:
            log.info("Auto-loaded cached model")
            demo(rec)
            return
        log.info("No cached model found — training from scratch")
        args.train = True

    if args.train:
        rec = train(
            work_option=args.work_option,
            preset=args.preset,
            meta_source=args.source,
            year_from=args.year_from,
            year_to=args.year_to,
            locale=args.lang,
            save=not args.no_save,
        )
        demo(rec)
        return

    if args.load:
        rec = load(
            preset=args.preset,
            source=args.source,
            locale=args.lang,
        )
        if rec:
            demo(rec)


if __name__ == "__main__":
    main()