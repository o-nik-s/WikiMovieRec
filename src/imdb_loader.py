"""Load and cache IMDb non-commercial datasets.

Download TSV.gz files from datasets.imdbws.com and expose as a single
metadata DataFrame compatible with merge_with_plots().
"""
import logging
import os
import tempfile
import csv
import gzip
from urllib.request import urlretrieve

import pandas as pd

from src.config import IMDB_DATA_DIR, IMDB_BASE_URL
from src.data_loader import _clean_name

log = logging.getLogger(__name__)

IMDB_FILES = {
    "title_basics": "title.basics.tsv.gz",
    "title_ratings": "title.ratings.tsv.gz",
    "title_crew": "title.crew.tsv.gz",
}

_PD_READ_KW = dict(sep="\t", compression="gzip", dtype=str,
                   keep_default_na=False, na_values=["\\N"])


def _download_file(name: str, dest_path: str, refresh: bool = False) -> str:
    if os.path.exists(dest_path) and not refresh:
        size = os.path.getsize(dest_path) / 1024 / 1024
        log.info("Already exists: %s (%.1f MB)", os.path.basename(dest_path), size)
        return dest_path
    url = f"{IMDB_BASE_URL}/{IMDB_FILES[name]}"
    log.info("Downloading %s …", IMDB_FILES[name])
    fd, temp_path = tempfile.mkstemp(
        prefix=f".{os.path.basename(dest_path)}.", suffix=".tmp",
        dir=os.path.dirname(dest_path) or ".",
    )
    os.close(fd)
    try:
        urlretrieve(url, temp_path)
        os.replace(temp_path, dest_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    log.info("Saved to %s", dest_path)
    return dest_path


def ensure_downloaded(refresh: bool = False) -> dict:
    """Download missing IMDb files. Returns {name: local_path}."""
    os.makedirs(IMDB_DATA_DIR, exist_ok=True)
    paths = {}
    for name, fname in IMDB_FILES.items():
        paths[name] = os.path.join(IMDB_DATA_DIR, fname)
        _download_file(name, paths[name], refresh=refresh)
    return paths


def _read_tsv(path: str, usecols: list[str] | None = None) -> pd.DataFrame:
    """Read a gzipped TSV file into a DataFrame."""
    kw = dict(_PD_READ_KW)
    if usecols:
        kw["usecols"] = usecols
    return pd.read_csv(path, **kw)


def load_title_basics(path: str | None = None) -> pd.DataFrame:
    """Load title.basics, filter to movies only (streaming, low memory)."""
    if path is None:
        path = os.path.join(IMDB_DATA_DIR, "title.basics.tsv.gz")
    log.info("Reading title.basics …")
    rows = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            if row.get("titleType") != "movie":
                continue
            title = _clean_name(row.get("primaryTitle", ""))
            year = row.get("startYear", "")
            genres = row.get("genres", "")
            rows.append({
                "tconst": row["tconst"],
                "Title": title,
                "Year": year if year.isdigit() else None,
                "genres": genres if genres and genres != r"\N" else None,
            })
    df = pd.DataFrame(rows)
    df["Title"] = df["Title"].replace("", pd.NA)
    return df[["tconst", "Title", "Year", "genres"]]


def load_title_ratings(path: str | None = None, only_tconst: set[str] | None = None) -> pd.DataFrame:
    """Load title.ratings (streaming, low memory)."""
    if path is None:
        path = os.path.join(IMDB_DATA_DIR, "title.ratings.tsv.gz")
    log.info("Reading title.ratings …")
    rows = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            if only_tconst is not None and row.get("tconst") not in only_tconst:
                continue
            rows.append({
                "tconst": row["tconst"],
                "IMDb_Rating": row.get("averageRating", ""),
                "IMDb_Votes": row.get("numVotes", ""),
            })
    df = pd.DataFrame(rows)
    return df.rename(columns={
        "averageRating": "IMDb_Rating",
        "numVotes": "IMDb_Votes",
    })[["tconst", "IMDb_Rating", "IMDb_Votes"]]


def load_title_crew(path: str | None = None, only_tconst: set[str] | None = None) -> pd.DataFrame:
    """Load title.crew — directors column (streaming, low memory)."""
    if path is None:
        path = os.path.join(IMDB_DATA_DIR, "title.crew.tsv.gz")
    log.info("Reading title.crew …")
    rows = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            if only_tconst is not None and row.get("tconst") not in only_tconst:
                continue
            rows.append({
                "tconst": row["tconst"],
                "directors": row.get("directors", ""),
            })
    df = pd.DataFrame(rows)
    return df[["tconst", "directors"]]


def load_imdb_metadata(
    min_year: int | None = None,
    max_year: int | None = None,
    min_votes: int = 1000,
) -> pd.DataFrame:
    """Load, merge and return IMDb metadata DataFrame.

    Columns returned (compatible with merge_with_plots):
      Title, Year, Genre, Director, IMDb_Rating, IMDb_Votes

    Args:
        min_year:  inclusive lower year bound (None = no limit).
        max_year:  inclusive upper year bound (None = no limit).
        min_votes: filter out movies with fewer votes.
    """
    ensure_downloaded()

    basics = load_title_basics()
    basic_ids = set(basics["tconst"].tolist())

    ratings = load_title_ratings(only_tconst=basic_ids)
    ratings["IMDb_Votes"] = pd.to_numeric(ratings["IMDb_Votes"], errors="coerce")
    if min_votes is not None:
        ratings = ratings[ratings["IMDb_Votes"] >= min_votes]

    meta = basics.merge(ratings, on="tconst", how="left")

    if "Year" in meta.columns:
        meta["Year"] = pd.to_numeric(meta["Year"], errors="coerce")
        if min_year is not None:
            meta = meta[meta["Year"] >= min_year]
        if max_year is not None:
            meta = meta[meta["Year"] <= max_year]

    kept_ids = set(meta["tconst"].tolist())
    crew = load_title_crew(only_tconst=kept_ids)
    meta = meta.merge(crew, on="tconst", how="left")

    if "genres" in meta.columns:
        meta["Genre"] = meta["genres"].apply(
            lambda g: "/".join(
                x.strip() for x in str(g).strip("()").split(",") if x.strip()
            )
            if pd.notna(g) and g.strip() else pd.NA
        )
        meta = meta.drop(columns=["genres"])
    else:
        meta["Genre"] = pd.NA

    if "directors" in meta.columns:
        meta["Director"] = meta["directors"].apply(
            lambda d: d if pd.notna(d) and str(d).strip() else "Unknown"
        )
        meta = meta.drop(columns=["directors"])
    else:
        meta["Director"] = "Unknown"

    if "Year" in meta.columns:
        meta["Year"] = meta["Year"].apply(
            lambda y: int(float(y)) if pd.notna(y) else pd.NA
        )

    final_cols = ["Title", "Year", "Genre", "Director", "IMDb_Rating", "IMDb_Votes"]
    meta = meta[[c for c in final_cols if c in meta.columns]]

    yr_range = f"{min_year or '…'}–{max_year or '…'}"
    log.info("IMDb metadata: %d movies (year %s, votes >= %d)",
             len(meta), yr_range, min_votes)
    return meta