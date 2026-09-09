import json
import re
import logging

import pandas as pd

import src.config as cfg
from src.config import NDJSON_PATH, CSV_PATH

log = logging.getLogger(__name__)


def _clean_name(name: str) -> str:
    """Strip (film), (2015 film), etc. from movie names."""
    return re.sub(r'\s*\([^)]*\)\s*$', '', str(name)).strip()
import logging

import pandas as pd

import src.config as cfg
from src.config import NDJSON_PATH, CSV_PATH

log = logging.getLogger(__name__)


def load_ndjson(path: str = NDJSON_PATH) -> pd.DataFrame:
    """Load wp_movies_10k.ndjson into a DataFrame."""
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rec = json.loads(line)
                if isinstance(rec, list):
                    if len(rec) != 5:
                        raise ValueError(
                            f"Expected 5 fields in NDJSON record, got {len(rec)}"
                        )
                    rec = dict(zip(
                        ["Name", "Description", "Links", "Rating1", "Rating2"],
                        rec,
                    ))
                if not isinstance(rec, dict):
                    raise ValueError("NDJSON record must be an object or 5-item array")
                rec["Name"] = str(rec.get("Name", "")).strip()
                records.append(rec)
    df = pd.DataFrame(records, columns=[
        "Name", "Description", "Links", "Rating1", "Rating2"
    ])
    return df


def load_csv(path: str = CSV_PATH) -> pd.DataFrame:
    """Load wiki_movie_plots_deduped.csv."""
    return pd.read_csv(path)


def load_imdb(
    year_from: int | None = None,
    year_to: int | None = None,
    min_votes: int | None = None,
) -> pd.DataFrame:
    """Load IMDb metadata (download if missing).

    Args:
        year_from: inclusive min year (None = no lower bound).
        year_to:   inclusive max year (None = no upper bound).
        min_votes: min IMDb votes filter.

    Returns DataFrame: Title, Year, Genre, Director, IMDb_Rating, IMDb_Votes
    """
    if min_votes is None:
        min_votes = cfg.IMDB_MIN_VOTES
    from src.imdb_loader import load_imdb_metadata
    return load_imdb_metadata(
        min_year=year_from, max_year=year_to, min_votes=min_votes
    )


def load_metadata(
    source: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
) -> pd.DataFrame:
    """Load metadata, optionally filtering by year range."""
    if source is None:
        source = cfg.METADATA_SOURCE

    if source == "imdb":
        log.info("Loading IMDb metadata")
        df = load_imdb(year_from=year_from, year_to=year_to)
    else:
        log.info("Loading CSV metadata (wiki plots)")
        df = load_csv()
        # CSV has "Release Year" column; filter in-memory
        if year_from is not None or year_to is not None:
            yr = pd.to_numeric(df.get("Release Year"), errors="coerce")
            mask = pd.Series(True, index=df.index)
            if year_from is not None:
                mask &= yr >= year_from
            if year_to is not None:
                mask &= yr <= year_to
            df = df[mask].copy()

    return df


def load_all(
    source: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
) -> tuple:
    """Load NDJSON movies + metadata and return (movies_df, metadata_df)."""
    movies_df = load_ndjson()
    metadata_df = load_metadata(source, year_from=year_from, year_to=year_to)
    return movies_df, metadata_df