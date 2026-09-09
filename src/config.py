RANDOM_SEED = 17
ROUND_EST = 4
WORK_OPTION = 1
WORK_OPTION_DESCRIPTION = {
    1: "All outgoing Wikipedia links (with duplicates) + Genre + Director",
    2: "Unique outgoing Wikipedia links + Genre + Director",
    3: "Description / infobox fields + Genre + Director",
    4: "Links to other films in dataset + Genre + Director",
    5: "Links to Wikipedia categories + Genre + Director",
}
CLASS_OPTION = 2
CLASS_OPTION_DESCRIPTION = {
    1: "SVC",
    2: "LinearSVC",
    3: "LogisticRegression",
    4: "SGDClassifier",
    5: "RidgeClassifier",
    6: "GradientBoostingClassifier",
    7: "AdaBoostClassifier",
}
# Embedding
EMBEDDING_SIZE = 100
EPOCHS = 25
POSITIVE_SAMPLES_PER_BATCH = 256
NEGATIVE_RATIO = 16
MIN_COUNT_LINKS = 10
# Recommendation
BEST_MOVIES = [
    "Harry Potter (film series)",
    "Titanic (1997 film)",
    "Avatar (2009 film)",
    "Gladiator (2000 film)",
    "The Lord of the Rings (film series)",
    "Sherlock Holmes (2010 film)",
    "Gone with the Wind (film)",
    "The Social Network",
    "The Wizard of Oz (1939 film)",
    "The Adventures of Robin Hood",
]
COUNT_RATING_MOVIES = 10
RATING_COLUMN = "Rating3"
# Data
NDJSON_PATH = "wp_movies_10k.ndjson"
CSV_PATH = "wiki_movie_plots_deduped.csv"
# Metadata source: "csv" (wikimovies plots) or "imdb" (IMDb datasets)
METADATA_SOURCE = "csv"
# IMDb
IMDB_BASE_URL = "https://datasets.imdbws.com"
IMDB_DATA_DIR = "data/imdb"
IMDB_MIN_VOTES = 1000
# Year range filter (None = no limit on that end)
YEAR_FROM = None
YEAR_TO = None
# Language: "en" or "ru" — auto-detect from locale if None
LANGUAGE = None