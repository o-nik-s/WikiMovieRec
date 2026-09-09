import numpy as np
import random
from src.config import RANDOM_SEED


class MovieRecommender:
    """Recommendation engine based on wiki-link embeddings.

    Supports optional metadata (year_map, genre_map, rating_map) for post-hoc filtering.
    """

    def __init__(
        self,
        embeddings: np.ndarray,
        movie_to_idx: dict,
        idx_to_movie: dict,
        year_map: dict[str, int] | None = None,
        genre_map: dict[str, list] | None = None,
        rating_map: dict[str, float] | None = None,
    ):
        self.embeddings = embeddings
        self.movie_to_idx = movie_to_idx
        self.idx_to_movie = idx_to_movie
        self.year_map = year_map or {}
        self.genre_map = genre_map or {}
        self.rating_map = rating_map or {}
        random.seed(RANDOM_SEED)

    def similar_movies(
        self,
        movie_name: str,
        top_k: int = 10,
        year_from: int | None = None,
        year_to: int | None = None,
        genres: list[str] | None = None,
        min_rating: float | None = None,
    ) -> list:
        """Return top_k most similar films by cosine distance.

        Args:
            movie_name:  query movie title.
            top_k:       how many results.
            year_from:   optional inclusive min year filter.
            year_to:     optional inclusive max year filter.
            genres:      list of genres to filter by (OR - any match).
            min_rating:  minimum IMDb rating (0-10).
        """
        if movie_name not in self.movie_to_idx:
            raise KeyError(f"Movie not found: {movie_name}")
        idx = self.movie_to_idx[movie_name]
        vec = self.embeddings[idx]
        distances = np.dot(self.embeddings, vec)
        ranked = np.argsort(distances)[::-1]
        result = []
        for c in ranked:
            name = self.idx_to_movie[c]
            if name == movie_name:
                continue
            # Filter by year
            if year_from is not None or year_to is not None:
                year = self.year_map.get(name)
                if year is None:
                    continue
                if year_from is not None and year < year_from:
                    continue
                if year_to is not None and year > year_to:
                    continue
            # Filter by genres (OR logic - any genre matches)
            if genres:
                movie_genres = self.genre_map.get(name, [])
                if not any(g.lower() in [gg.lower() for gg in genres] for g in movie_genres):
                    continue
            # Filter by min rating
            if min_rating is not None:
                movie_rating = self.rating_map.get(name)
                if movie_rating is None or movie_rating < min_rating:
                    continue
            sim = float(round(distances[c], 4))
            result.append((name, sim))
            if len(result) >= top_k:
                break
        return result

    def recommend(
        self,
        movie_name: str,
        top_k: int = 10,
        basic: float = 1e7,
        year_from: int | None = None,
        year_to: int | None = None,
        genres: list[str] | None = None,
        min_rating: float | None = None,
    ) -> str | None:
        """Weighted random recommendation."""
        similar = self.similar_movies(
            movie_name, top_k,
            year_from=year_from, year_to=year_to,
            genres=genres, min_rating=min_rating,
        )
        if not similar:
            return None
        weights = []
        cumulative = 0
        for name, dist in similar:
            w = basic ** (1 - dist)
            cumulative += w
            weights.append((name, cumulative))
        threshold = random.random() * cumulative
        for name, cum in weights:
            if cum >= threshold:
                return name
        return similar[-1][0]

    def recommend_batch(
        self,
        movie_name: str,
        top_k: int = 10,
        basic: float = 1e7,
        num: int = 5,
        year_from: int | None = None,
        year_to: int | None = None,
        genres: list[str] | None = None,
        min_rating: float | None = None,
    ) -> list:
        """Return num recommendations."""
        return [
            self.recommend(movie_name, top_k, basic,
                           year_from=year_from, year_to=year_to,
                           genres=genres, min_rating=min_rating)
            for _ in range(num)
        ]

    def format_recommendation(
        self,
        movie_name: str,
        top_k: int = 10,
        year_from: int | None = None,
        year_to: int | None = None,
        genres: list[str] | None = None,
        min_rating: float | None = None,
    ) -> str:
        """Format recommendation sentence in current locale."""
        from src.i18n import lang
        similar = self.similar_movies(
            movie_name, top_k,
            year_from=year_from, year_to=year_to,
            genres=genres, min_rating=min_rating,
        )
        if not similar:
            return lang("no_rec", movie=movie_name)
        rec = self.recommend(
            movie_name, top_k,
            year_from=year_from, year_to=year_to,
            genres=genres, min_rating=min_rating,
        )
        if rec is None:
            return lang("no_rec", movie=movie_name)
        return lang("if_you_like", movie=movie_name, rec=rec)