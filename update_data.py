"""Standalone IMDb data update script.

Usage:
    python update_data.py              # download + report stats
    python update_data.py --force      # re-download all files
    python update_data.py --check      # print status only, no download
    python update_data.py --retrain    # download + train all model presets
    python update_data.py --train medium  # download + train one preset
    python update_data.py --no-download --train medium  # train only (no download)

Schedule (recommended):
    Daily (03:00):  python update_data.py           # download fresh IMDb data
    Weekly Monday:  python update_data.py --train medium
    Monthly 1st:    python update_data.py --retrain

Cron examples:
    0 3 * * * cd /path/to/WikiMovieRec && .venv/bin/python update_data.py
    0 2 * * 1 cd /path/to/WikiMovieRec && .venv/bin/python update_data.py --train medium
    0 1 1 * * cd /path/to/WikiMovieRec && .venv/bin/python update_data.py --retrain
"""
import argparse
import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)


def do_download(force: bool = False):
    """Download fresh IMDb datasets, replacing files atomically."""
    from src.config import IMDB_DATA_DIR
    from src.imdb_loader import ensure_downloaded, IMDB_FILES

    os.makedirs(IMDB_DATA_DIR, exist_ok=True)

    paths = ensure_downloaded(refresh=True)
    return paths


def do_stats(year_from: int | None = None, year_to: int | None = None):
    """Print basic stats on downloaded IMDb files."""
    from src.config import IMDB_DATA_DIR, IMDB_MIN_VOTES
    from src.imdb_loader import load_imdb_metadata, load_title_basics

    basics_path = os.path.join(IMDB_DATA_DIR, "title.basics.tsv.gz")
    if not os.path.exists(basics_path):
        log.warning("IMDb data not found. Run without --check to download.")
        return

    # Quick stats from basics only (fast)
    df = load_title_basics(basics_path)
    total = len(df)
    if "Year" in df.columns:
        import pandas as pd
        df["Year"] = pd.to_numeric(df["Year"], errors="coerce")
        valid_years = df["Year"].dropna().astype(int)
        year_min = valid_years.min() if len(valid_years) else "N/A"
        year_max = valid_years.max() if len(valid_years) else "N/A"
    else:
        year_min = "N/A"
        year_max = "N/A"

    print(f"\n=== IMDb title.basics ===")
    print(f"  Movies (titleType='movie'): {total:,}")
    print(f"  Year range: {year_min} – {year_max}")

    # Full metadata stats (slower, but informative)
    log.info("Loading full IMDb metadata (this may take a moment)...")
    start = time.time()
    meta = load_imdb_metadata(
        min_year=year_from,
        max_year=year_to,
        min_votes=IMDB_MIN_VOTES,
    )
    elapsed = time.time() - start

    print(f"\n=== IMDb metadata (votes>={IMDB_MIN_VOTES}) ===")
    yr_from_label = year_from or "…"
    yr_to_label = year_to or "∞"
    print(f"  Total movies: {len(meta):,}")
    print(f"  Year range: {yr_from_label} – {yr_to_label}")
    print(f"  Genres present: {meta['Genre'].notna().sum():,}")
    print(f"  Directors present: {meta['Director'].notna().sum():,}")
    print(f"  Ratings present: {meta['IMDb_Rating'].notna().sum():,}")
    print(f"  Load time: {elapsed:.1f}s")

    if "Year" in meta.columns:
        import pandas as pd
        yr = pd.to_numeric(meta["Year"], errors="coerce").dropna().astype(int)
        print(f"  Actual year range: {yr.min()} – {yr.max()}")

    # File sizes
    from src.config import IMDB_DATA_DIR
    sizes = []
    for fname in os.listdir(IMDB_DATA_DIR):
        fpath = os.path.join(IMDB_DATA_DIR, fname)
        sz = os.path.getsize(fpath) / 1024 / 1024
        sizes.append(f"  {fname}: {sz:.1f} MB")
    print(f"\n=== Files ({IMDB_DATA_DIR}) ===")
    print("\n".join(sizes))


def do_train(presets: list[str] | None = None, source: str = "imdb"):
    """Train specified presets (or all) and save models."""
    from src.main import train as do_train_impl
    from src.model_cache import PRESETS, list_models, DEFAULT_PRESET
    from src.i18n import set_locale
    set_locale("en")

    if presets is None:
        presets = list(PRESETS.keys())
    else:
        presets = [p for p in presets if p in PRESETS]
        if not presets:
            log.error("No valid presets. Available: %s", list(PRESETS.keys()))
            return

    if not os.path.isdir("models"):
        os.makedirs("models", exist_ok=True)

    failed = []
    for preset in presets:
        log.info("=" * 50)
        log.info("Training model: preset=%s, source=%s", preset, source)
        try:
            rec = do_train_impl(
                preset=preset,
                meta_source=source,
                locale="en",
                save=True,
            )
            log.info("OK: %s — %d movies", preset, len(rec.movie_to_idx))
        except Exception as e:
            log.error("FAILED %s: %s", preset, e)
            failed.append(preset)

    if failed:
        raise RuntimeError(f"Model training failed for preset(s): {', '.join(failed)}")

    print("\n=== Trained models ===")
    models = list_models()
    for m in models:
        print(f"  {m['file']:45s}  {m['preset']:6s}  "
              f"{m['num_movies']:>6} movies  {m['embedding_size']:>3}d  "
              f"{m['file_size_mb']:>6.1f} MB")


def _notify_retrain_done():
    """Print message suggesting API restart after retraining."""
    log.info("Model retraining complete.")
    log.info("Restart API server to load new models (~100ms):")
    log.info("  kill -HUP <uvicorn-pid>   (Linux, graceful)")
    log.info("  systemctl restart wikimovierec   (if systemd service)")


def main():
    parser = argparse.ArgumentParser(description="Update IMDb datasets for WikiMovieRec")
    parser.add_argument("--force", action="store_true", help="Re-download all files")
    parser.add_argument("--check", action="store_true", help="Print status only")
    parser.add_argument("--no-download", action="store_true", help="Skip download (use existing data)")
    parser.add_argument("--skip-stats", action="store_true", help="Skip stats report")
    parser.add_argument("--retrain", action="store_true",
                        help="Download + retrain all model presets")
    parser.add_argument("--train", nargs="*", default=None, metavar="PRESET",
                        help="Train specified preset(s), e.g. --train medium. Default: medium")
    parser.add_argument("--year-from", type=int, default=None,
                        help="Minimum year filter (inclusive)")
    parser.add_argument("--year-to", type=int, default=None,
                        help="Maximum year filter (inclusive)")
    args = parser.parse_args()

    if args.check:
        do_stats(year_from=args.year_from, year_to=args.year_to)
        return

    if not args.no_download:
        log.info("Starting IMDb data update...")
        start = time.time()
        do_download(force=args.force)
        download_time = time.time() - start
        log.info("Download completed in %.1fs", download_time)

    if not args.skip_stats:
        do_stats(year_from=args.year_from, year_to=args.year_to)

    if args.retrain:
        log.info("Retraining all presets...")
        do_train(source="imdb")
        _notify_retrain_done()
    elif args.train is not None:
        presets = args.train if args.train else [DEFAULT_PRESET]
        log.info("Training preset(s): %s", presets)
        do_train(presets=presets, source="imdb")
        _notify_retrain_done()
    else:
        print("\nDone. IMDb data is ready for the pipeline.")
        print("Use --retrain to train all models, or --train medium for a single preset.")


if __name__ == "__main__":
    main()