import pandas as pd
import numpy as np


def fmt_title(name: str) -> str:
    """Clean training title: strip (film), (2015 film), year suffixes."""
    import re
    return re.sub(r'\s*\([^)]*\)\s*$', '', name).strip()


def extract_title(name: str) -> str:
    """Extract clean title from 'Name (extra)' format."""
    return name.split(" (")[0].split(" )")[0]


def parse_rating1(val) -> float:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return np.nan
    s = str(val).strip()
    if not s:
        return np.nan
    if "%" in s:
        s = s.replace("%", "")
    try:
        return float(s)
    except ValueError:
        return np.nan


def parse_rating2(val) -> float:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return np.nan
    s = str(val).strip()
    if not s:
        return np.nan
    if "/" in s:
        parts = s.split("/")
        try:
            denominator = float(parts[1])
            return float(parts[0]) / denominator if denominator else np.nan
        except (IndexError, ValueError):
            return np.nan
    try:
        return float(s)
    except ValueError:
        return np.nan


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add Title, MovieLinks, CategoryLinks, normalized ratings to df."""
    df = df.copy()
    # Clean title
    df["Title"] = df["Name"].apply(extract_title)
    # Set of all movie titles for filtering links
    title_set = set(df["Title"])
    # MovieLinks — links that point to other movies in dataset
    df["MovieLinks"] = df["Links"].apply(
        lambda x: [i for i in x if i.split(" (")[0].split(" )")[0] in title_set]
    )
    # CategoryLinks — Wikipedia category links
    df["CategoryLinks"] = df["Links"].apply(
        lambda x: [i for i in x if i.startswith("Category:")]
    )
    # Normalize ratings
    df["Rating1"] = df["Rating1"].apply(parse_rating1)
    df["Rating2"] = df["Rating2"].apply(parse_rating2)
    df["Rating3"] = df["Rating1"] * df["Rating2"]
    return df


def _detect_source(df: pd.DataFrame) -> str:
    """Return 'csv' if wiki plots columns present, else 'imdb'."""
    return "csv" if "Release Year" in df.columns else "imdb"


def _dedup_imdb(plots_df: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate IMDb metadata: keep the entry with highest IMDb_Votes per title-year.

    When multiple IMDb entries share the same title, prefer the one with most votes.
    This avoids picking a 1940s "Titanic" over the 1997 blockbuster.
    """
    import pandas as pd
    # Votes may be string; coerce to numeric
    df = plots_df.copy()
    df["_votes"] = pd.to_numeric(df.get("IMDb_Votes", 0), errors="coerce").fillna(0)
    # Sort by votes descending, keep first per Title
    df = df.sort_values("_votes", ascending=False)
    df = df.drop_duplicates(subset="Title", keep="first")
    df = df.drop(columns=["_votes"])
    return df


def merge_with_plots(movies_df: pd.DataFrame, plots_df: pd.DataFrame) -> pd.DataFrame:
    """Left-join processed movies with metadata (CSV or IMDb) on Title.

    Supports two metadata schemas:
      - CSV (wiki plots):  Release Year, Origin/Ethnicity, Director, Cast, Genre
      - IMDb:             Year, Genre, Director, IMDb_Rating, IMDb_Votes

    Produces uniform token columns: GenreTokens, DirectorTokens, CastTokens,
    OriginTokens, YearTokens — consumed by get_feature_vector().

    Deduplicates both sides on Title before merging to avoid row multiplication.
    For IMDb sources, deduplication prefers the entry with the most IMDb votes.
    """
    source = _detect_source(plots_df)
    if source == "imdb":
        plots_df = _dedup_imdb(plots_df)
    else:
        plots_df = plots_df.drop_duplicates(subset="Title", keep="first")
    movies_df = movies_df.drop_duplicates(subset="Title", keep="first")
    merged = pd.merge(movies_df, plots_df, how="left", on="Title")

    # --- Genre tokens (both sources) ---
    merged["GenreTokens"] = merged.get("Genre", pd.Series()).apply(
        lambda g: [x.strip() for x in str(g).split("/") if x.strip()]
        if pd.notna(g) and str(g).strip() else []
    )

    # --- Director tokens (both sources) ---
    merged["DirectorTokens"] = merged.get("Director", pd.Series()).apply(
        lambda d: [str(d).strip()]
        if pd.notna(d) and str(d).strip() else []
    )

    if source == "csv":
        # Cast tokens: "Leonardo DiCaprio,Tom Hardy" -> list
        merged["CastTokens"] = merged.get("Cast", pd.Series()).apply(
            lambda c: [x.strip() for x in str(c).split(",") if x.strip()]
            if pd.notna(c) and str(c).strip() else []
        )
        # Origin/Ethnicity token
        merged["OriginTokens"] = merged.get("Origin/Ethnicity", pd.Series()).apply(
            lambda o: [str(o).strip()]
            if pd.notna(o) and str(o).strip() else []
        )
        # Release Year token
        merged["YearTokens"] = merged.get("Release Year", pd.Series()).apply(
            lambda y: [f"Decade-{int(float(y)) // 10 * 10}"]
            if pd.notna(y) else []
        )
    else:
        # IMDb source — no Cast / Origin; create empty-list columns
        merged["CastTokens"] = [[] for _ in range(len(merged))]
        merged["OriginTokens"] = [[] for _ in range(len(merged))]
        merged["YearTokens"] = merged.get("Year", pd.Series()).apply(
            lambda y: [f"Decade-{int(float(y)) // 10 * 10}"]
            if pd.notna(y) and str(y).replace(".", "", 1).isdigit() else []
        )
    return merged


def get_feature_vector(movie_row, work_option: int):
    """Return feature tokens for a given work_option.

    movie_row is a numpy row from merged_df.to_records() with fixed columns:
      0: Name, 1: Description, 2: Links, 3: Rating1, 4: Rating2
      5: Title,  6: MovieLinks,  7: CategoryLinks, 8: Rating3
    CSV merged (order depends on merge):
      9: Release Year, 10: Origin/Ethnicity, 11: Director, 12: Cast
      13: Genre, 14: Wiki Page, 15: Plot
      16: GenreTokens, 17: DirectorTokens, 18: CastTokens,
      19: OriginTokens, 20: YearTokens
    """
    # Wiki-link based features
    if work_option == 1:
        feats = list(movie_row[2])  # Links (with duplicates)
    elif work_option == 2:
        feats = list(set(movie_row[2]))  # Unique links
    elif work_option == 3:
        feats = list(movie_row[1].keys()) if isinstance(movie_row[1], dict) else []
    elif work_option == 4:
        feats = list(movie_row[6])  # MovieLinks
    elif work_option == 5:
        feats = list(movie_row[7])  # CategoryLinks
    else:
        raise ValueError(f"Unknown work_option: {work_option}")

    # The original notebook's option 1 uses only outgoing Wikipedia links.
    # Metadata remains available for options that explicitly opt into it.
    if work_option == 1 or len(movie_row) < 21:
        return feats
    csv_tokens = [
        movie_row[16],  # GenreTokens
        movie_row[17],  # DirectorTokens
        movie_row[18],  # CastTokens
        movie_row[19],  # OriginTokens
        movie_row[20],  # YearTokens
    ]
    for tokens in csv_tokens:
        if isinstance(tokens, (list, tuple)):
            feats.extend(tokens)
    return feats