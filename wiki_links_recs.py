"""
Система рекомендаций по фильмам, основанная на исходящих ссылках из Википедии.

Переписано из ноутбука "Система рекомендаций по фильмам, основанная на
исходящих ссылках из Википедии.ipynb" в обычный Python-скрипт.

Адаптация под Keras 3 / TF 2.21:
  - keras.layers.merge.Dot  ->  keras.layers.Dot
  - model.fit_generator(...) -> model.fit(...)

Запуск:
    python wiki_links_recs.py [epochs]
по умолчанию epochs = 25 (как в ноутбуке).
"""
import warnings
warnings.filterwarnings("ignore")

import sys
import json
import random
import time
from collections import Counter

import numpy as np
import pandas as pd

from keras.models import Model
from keras.layers import Embedding, Input, Reshape, Dot
from sklearn.svm import SVC, LinearSVC
from sklearn.linear_model import LogisticRegression, SGDClassifier, RidgeClassifier
from sklearn.ensemble import GradientBoostingClassifier, AdaBoostClassifier

# ---------------------------------------------------------------------------
# Параметры (как в ноутбуке)
# ---------------------------------------------------------------------------
rnd_seed = 17
round_est = 4  # точность округления

work_option = 1
work_option_description = {
    1: 'Работа по ссылкам (поле Links), дубликаты ссылок оставляем',
    2: 'Работа по ссылками (поле Links), дубликаты убираем',
    3: 'Работа по описанию (поле Description)',
    4: 'На основании ссылок (поле Links) на фильмы из датасета',
    5: 'На основании ссылок на категории',
}

min_count_links = 10
embedding_size = 100
nn_metric = 'mse'
positive_samples_per_batch = 256
negative_ratio = 16
EPOCHS = int(sys.argv[1]) if len(sys.argv) > 1 else 25

# Профиль пользователя (8 фильмов) — для финальной оценки
PROFILE_MOVIES = [
    'Titanic (1997 film)',
    'The Fifth Element',
    'Gladiator (2000 film)',
    'Armageddon (1998 film)',
    'First Knight',
    'Troy (film)',
    'The Matrix',
    'A Beautiful Mind (film)',
]


# ---------------------------------------------------------------------------
# Часть 1. Анализ и предобработка данных
# ---------------------------------------------------------------------------
def load_data():
    with open('wp_movies_10k.ndjson') as fin:
        movies = [json.loads(l) for l in fin]
    data = pd.DataFrame(movies)
    data.rename(columns={0: "Name", 1: "Description", 2: "Links",
                         3: "Rating1", 4: "Rating2"}, inplace=True)

    TitleSet = frozenset(data.Name)
    data["MovieLinks"] = data.Links.apply(lambda x: [i for i in x if i in TitleSet])
    data["CategoryLinks"] = data.Links.apply(lambda x: [i for i in list(x) if i[:9] == 'Category:'])

    data["Title"] = data["Name"].apply(lambda x: x.split(' (')[0])
    data["Rating1"] = data["Rating1"].apply(
        lambda x: int(x[:-1]) if (isinstance(x, str) and len(x) > 1) else np.nan)
    data["Rating2"] = data["Rating2"].apply(
        lambda x: 100 * float(x.split('/')[0]) / float(x.split('/')[1])
        if (isinstance(x, str) and len(x) > 1) else np.nan)
    data["Rating3"] = data["Rating1"] * data["Rating2"]

    # Объединяем с описанием (plot)
    data2 = pd.read_csv('wiki_movie_plots_deduped.csv')
    data3 = pd.merge(data, data2, how="left", on="Title")
    # Merge может умножить строки (несколько plot на один Title) — оставляем
    # по одному фильму на уникальное имя, чтобы индексы совпали с movie_to_idx.
    data3 = data3.drop_duplicates(subset="Name", keep="first").reset_index(drop=True)
    return data3


def movie_option(movie, x):
    return {1: movie[2], 2: set(movie[2]), 3: movie[1].items(),
            4: movie[5], 5: movie[6]}[x]


def common_link_counts(work_option=1):
    link_counts = Counter()
    for movie in movies:
        link_counts.update(movie_option(movie, work_option))
    return link_counts


# ---------------------------------------------------------------------------
# Часть II. Построение модели выбора ближайших фильмов
# ---------------------------------------------------------------------------
def build_index():
    global movie_to_idx, top_links, link_to_idx, pairs, pairs_set
    link_counts = common_link_counts(work_option)
    movie_to_idx = {movie[0]: idx for idx, movie in enumerate(movies)}
    top_links = [link for link, c in link_counts.items() if c >= min_count_links]
    link_to_idx = {link: idx for idx, link in enumerate(top_links)}

    pairs = []
    for movie in movies:
        pairs.extend((link_to_idx[link], movie_to_idx[movie[0]])
                     for link in movie_option(movie, work_option)
                     if link in link_to_idx)
    pairs_set = set(pairs)
    return len(movie_to_idx), len(top_links), len(pairs_set)


def batchifier(pairs, positive_samples=64, negative_ratio=8):
    batch_size = positive_samples * (1 + negative_ratio)
    batch = np.zeros((batch_size, 3))
    while True:
        for idx, (link_id, movie_id) in enumerate(random.sample(pairs, positive_samples)):
            batch[idx, :] = (link_id, movie_id, 1)
        idx = positive_samples
        while idx < batch_size:
            movie_id = random.randrange(len(movie_to_idx))
            link_id = random.randrange(len(top_links))
            if (link_id, movie_id) not in pairs_set:
                batch[idx, :] = (link_id, movie_id, -1)
                idx += 1
        np.random.shuffle(batch)
        yield {'link': batch[:, 0], 'movie': batch[:, 1]}, batch[:, 2]


def movie_embedding_model(embedding_size=100):
    link = Input(name='link', shape=(1,))
    link_embedding = Embedding(name='link_embedding',
                               input_dim=len(top_links),
                               output_dim=embedding_size)(link)
    movie = Input(name='movie', shape=(1,))
    movie_embedding = Embedding(name='movie_embedding',
                                input_dim=len(movie_to_idx),
                                output_dim=embedding_size)(movie)
    dot = Dot(name='dot_product', normalize=True, axes=2)([link_embedding, movie_embedding])
    merged = Reshape((1,))(dot)
    model = Model(inputs=[link, movie], outputs=merged)
    model.compile(optimizer='nadam', loss=nn_metric)
    return model


def train_model(epochs):
    random.seed(rnd_seed)
    model = movie_embedding_model(embedding_size)
    steps_per_epoch = len(pairs) // positive_samples_per_batch
    t0 = time.time()
    model.fit(batchifier(pairs, positive_samples=positive_samples_per_batch,
                         negative_ratio=negative_ratio),
              epochs=epochs,
              steps_per_epoch=steps_per_epoch,
              verbose=2)
    print(f"Training done in {(time.time() - t0) / 60:.1f} min")
    # Сохраняем модель, чтобы прогресс не терялся при прерывании процесса
    try:
        model.save('wiki_links_model.keras')
        print('Model saved to wiki_links_model.keras')
    except Exception as e:
        print('Model save failed:', e)
    return model


def get_normalized_movies(model):
    movie = model.get_layer('movie_embedding')
    movie_weights = movie.get_weights()[0]
    movie_lengths = np.linalg.norm(movie_weights, axis=1)
    normalized_movies = (movie_weights.T / movie_lengths).T
    return normalized_movies


def similar_movies(movie, count=10, prnt=True):
    dists = np.dot(normalized_movies, normalized_movies[movie_to_idx[movie]])
    closest = np.argsort(dists)[-count:]
    closest_movies = []
    for c in reversed(closest):
        closest_movies.append([movies[c][0], round(1 - dists[c], round_est)])
        if prnt:
            print(c, '- ', movies[c][0], ' ---', round(1 - dists[c], round_est))
    return closest_movies


def movie_choise(best_movie, basic=1e7):
    """Взвешенный случайный выбор из похожих (вес = basic**(1 - dist))."""
    summ = 0
    movie_list = similar_movies(best_movie, 10000, False)
    for movie in movie_list[1:]:
        add = basic ** (1 - movie[1])
        summ += add
        movie.append(round(summ, 4))
    rnd = random.random() * movie_list[-1][-1]
    for movie in movie_list:
        if movie[-1] > rnd:
            break
    return movie[0]


# ---------------------------------------------------------------------------
# Часть III. Рекомендательная система набора фильмов
# ---------------------------------------------------------------------------
def set_based_recommend(good_set, n_best=20):
    """Классификатор (LinearSVC) на 'хороших' (профиль) и 'плохих' (худшие по рейтингу).

    Ранжирует все фильмы по decision_function.
    """
    count_raiting_movies = 10
    rating = "Rating3"
    sort_films = data[data[rating] > 0].sort_values(rating, ascending=False)
    worst_movies_set = list(sort_films[-count_raiting_movies:].Name.values)

    X = np.asarray([normalized_movies[movie_to_idx[movie]] for movie in good_set + worst_movies_set])
    y = np.asarray([1 for _ in good_set] + [0 for _ in worst_movies_set])

    clf = LinearSVC(random_state=rnd_seed)
    clf.fit(X, y)

    estimated = clf.decision_function(normalized_movies)
    best = np.argsort(estimated)
    print('Хорошие фильмы (профиль):', good_set, sep='\n')
    print('Плохие фильмы:', worst_movies_set, sep='\n')
    print('\nЛучшие фильмы по профилю:')
    top = []
    for c in reversed(best[-n_best:]):
        name = movies[c][0]
        print(c, name, round(estimated[c], round_est))
        top.append((name, round(estimated[c], round_est)))
    return top


def main():
    global data, movies, normalized_movies
    print("=== Часть 1. Загрузка данных ===")
    data = load_data()
    movies = list(data.to_numpy())
    print("movies:", len(movies))

    print("\n=== Часть II. Индексация ссылок ===")
    n_movies, n_links, n_pairs = build_index()
    print(f"movie_to_idx: {n_movies}, top_links: {n_links}, pairs: {n_pairs}")

    print(f"\n=== Часть II. Обучение embedding-модели (epochs={EPOCHS}) ===")
    model = train_model(EPOCHS)
    normalized_movies = get_normalized_movies(model)

    print("\n=== Проверка similar_movies ===")
    for m in ['Titanic (1997 film)', 'Gladiator (2000 film)', 'The Matrix']:
        print(f"\n--- similar to {m} ---")
        similar_movies(m, 10)

    print("\n=== Часть III. Рекомендация по профилю (8 фильмов) ===")
    top = set_based_recommend(PROFILE_MOVIES, n_best=20)
    print("\n=== ИТОГ: топ-20 по профилю ===")
    for i, (name, score) in enumerate(top, 1):
        print(f"{i:2d}. {name}  ({score})")


if __name__ == '__main__':
    main()
