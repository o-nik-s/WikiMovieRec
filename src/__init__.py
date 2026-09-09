"""WikiMovieRec — Movie Recommender from Wikipedia Outgoing Links."""
from src.config import *
from src.data_loader import load_ndjson, load_csv, load_imdb, load_metadata, load_all
from src.preprocessor import (
    extract_title, parse_rating1, parse_rating2,
    build_features, merge_with_plots, get_feature_vector,
)
from src.i18n import get_locale, set_locale, lang, _
from src.imdb_loader import ensure_downloaded, load_imdb_metadata
from src.model_cache import load_model, save_model, list_models, PRESETS, DEFAULT_PRESET
from src.embedding import set_seeds, build_link_index, build_pairs, EmbeddingModel
from src.classifier import get_classifier, cross_validate
from src.recommender import MovieRecommender