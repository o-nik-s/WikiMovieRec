import random
import numpy as np
from collections import Counter
from src.config import (
    EMBEDDING_SIZE, RANDOM_SEED,
    POSITIVE_SAMPLES_PER_BATCH, NEGATIVE_RATIO, MIN_COUNT_LINKS,
)
from src.preprocessor import get_feature_vector

try:
    from tensorflow.keras.models import Model
    from tensorflow.keras.layers import Embedding, Input, Dot, Reshape
    from tensorflow.keras.optimizers import Nadam
    import tensorflow as tf
    KERAS_AVAILABLE = True
except ImportError:
    KERAS_AVAILABLE = False

import logging

log = logging.getLogger(__name__)


def set_seeds(seed: int = RANDOM_SEED):
    random.seed(seed)
    np.random.seed(seed)
    if KERAS_AVAILABLE:
        tf.random.set_seed(seed)


# ------------------------------------------------------------------
# Vocabulary / pairs
# ------------------------------------------------------------------

def build_link_index(movies: list, work_option: int,
                     min_count: int = MIN_COUNT_LINKS):
    link_counts = Counter()
    for movie in movies:
        link_counts.update(get_feature_vector(movie, work_option))

    movie_to_idx = {movie[0]: idx for idx, movie in enumerate(movies)}
    top_links = [lnk for lnk, c in link_counts.items() if c >= min_count]
    link_to_idx = {lnk: idx for idx, lnk in enumerate(top_links)}
    return movie_to_idx, link_to_idx, top_links


def build_pairs(movies: list, work_option: int,
                link_to_idx: dict, movie_to_idx: dict) -> list:
    pairs = []
    for movie in movies:
        for lnk in get_feature_vector(movie, work_option):
            if lnk in link_to_idx:
                pairs.append((link_to_idx[lnk], movie_to_idx[movie[0]]))
    return pairs


# ------------------------------------------------------------------
# Keras model (when TF is available)
# ------------------------------------------------------------------

class _KerasBatchGen:
    """Stateful infinite generator for Keras model.fit()."""

    def __init__(self, pairs, pairs_set, num_movies, num_links,
                 pos_samples=POSITIVE_SAMPLES_PER_BATCH,
                 neg_ratio=NEGATIVE_RATIO):
        self.pairs = pairs
        self.pairs_set = pairs_set
        self.num_movies = num_movies
        self.num_links = num_links
        self.pos_samples = pos_samples
        self.batch_size = pos_samples * (1 + neg_ratio)

    def __iter__(self):
        while True:
            batch = np.zeros((self.batch_size, 3))
            sampled = random.sample(self.pairs, self.pos_samples)
            for i, (lk, mv) in enumerate(sampled):
                batch[i] = (lk, mv, 1.0)
            i = self.pos_samples
            while i < self.batch_size:
                mv = random.randrange(self.num_movies)
                lk = random.randrange(self.num_links)
                if (lk, mv) not in self.pairs_set:
                    batch[i] = (lk, mv, -1.0)
                    i += 1
            np.random.shuffle(batch)
            yield {"link": batch[:, 0], "movie": batch[:, 1]}, batch[:, 2]


def _create_keras_model(num_links: int, num_movies: int,
                         emb_size: int) -> "Model":
    link_in = Input(name="link", shape=(1,))
    link_emb = Embedding(num_links, emb_size,
                         name="link_embedding")(link_in)
    movie_in = Input(name="movie", shape=(1,))
    movie_emb = Embedding(num_movies, emb_size,
                          name="movie_embedding")(movie_in)
    dot = Dot(normalize=True, axes=2, name="dot_product")(
        [link_emb, movie_emb]
    )
    out = Reshape((1,))(dot)
    model = Model([link_in, movie_in], [out])
    model.compile(optimizer=Nadam(), loss="mse")
    return model


def _extract_keras_embeddings(model: "Model") -> np.ndarray:
    weights = model.get_layer("movie_embedding").get_weights()[0]
    norms = np.linalg.norm(weights, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    return weights / norms


# ------------------------------------------------------------------
# Sklearn fallback — SVD on biadjacency matrix
# ------------------------------------------------------------------

def _train_sklearn_embeddings(pairs: list, num_movies: int,
                               num_links: int,
                               embedding_size: int = EMBEDDING_SIZE,
                               epochs: int = 25) -> np.ndarray:
    """Build embeddings via implicit matrix factorization (SVD).

    Constructs a sparse biadjacency matrix (movies × links), runs
    TruncatedSVD to obtain low-dimensional movie embeddings, then
    normalises them.  The *epochs* parameter is accepted for API
    compatibility but is ignored in this path.
    """
    log.info("TensorFlow not available — falling back to SVD embeddings")
    from scipy.sparse import csr_array
    from sklearn.decomposition import TruncatedSVD

    col, row = zip(*pairs) if pairs else ([], [])
    data = np.ones(len(row))
    biadj = csr_array((data, (row, col)),
                      shape=(num_movies, num_links))
    svd = TruncatedSVD(n_components=min(embedding_size, num_movies - 1, num_links - 1),
                       random_state=RANDOM_SEED)
    movie_vecs = svd.fit_transform(biadj)
    norms = np.linalg.norm(movie_vecs, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    return movie_vecs / norms


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class EmbeddingModel:
    """Unified embedding trainer — Keras or SVD fallback."""

    def __init__(self, num_links: int, num_movies: int,
                 embedding_size: int = EMBEDDING_SIZE):
        self.num_links = num_links
        self.num_movies = num_movies
        self.embedding_size = embedding_size
        self.backend = "keras" if KERAS_AVAILABLE else "sklearn"
        self._model = None
        self._embeddings = None

    def train(self, pairs: list, epochs: int = 25, verbose: int = 1) -> "EmbeddingModel":
        if KERAS_AVAILABLE:
            log.info("Using Keras embedding model")
            self.backend = "keras"
            self._model = _create_keras_model(
                self.num_links, self.num_movies, self.embedding_size
            )
            pairs_set = set(pairs)
            gen = iter(_KerasBatchGen(
                pairs, pairs_set, self.num_movies, self.num_links
            ))
            steps = max(len(pairs) // POSITIVE_SAMPLES_PER_BATCH, 1)
            self._model.fit(gen, epochs=epochs, steps_per_epoch=steps, verbose=verbose)
            self._embeddings = _extract_keras_embeddings(self._model)
        else:
            self.backend = "sklearn"
            self._embeddings = _train_sklearn_embeddings(
                pairs, self.num_movies, self.num_links,
                self.embedding_size, epochs,
            )
        return self

    def get_embeddings(self) -> np.ndarray:
        if self._embeddings is None:
            raise RuntimeError("Call train() before get_embeddings()")
        return self._embeddings