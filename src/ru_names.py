"""Russian ↔ English movie title mapping for fuzzy search.

Uses:
  1. ru_names_imdb.json (IMDb akas, 4000+ films) — auto-generated
  2. Built-in fallback RU→EN (~100 films) — manually curated
"""
import os
import json

_HERE = os.path.dirname(__file__)
_IMDB_MAP_PATH = os.path.join(_HERE, "ru_names_imdb.json")

# Load IMDb-based map (EN → RU, auto-generated from title.akas)
_IMDB_EN_TO_RU: dict[str, str] = {}
if os.path.exists(_IMDB_MAP_PATH):
    with open(_IMDB_MAP_PATH, "r", encoding="utf-8") as f:
        _IMDB_EN_TO_RU = json.load(f)

# Hand-curated fallback (RU → EN)
_FALLBACK_RU_TO_EN: dict[str, str] = {
    "король говорит": "The King's Speech (film)",
    "титаник": "Titanic (1997 film)",
    "аватар": "Avatar (2009 film)",
    "мстители": "The Avengers (2012 film)",
    "эндгейм": "Avengers: Endgame",
    "мстители конец игры": "Avengers: Endgame",
    "бесконечность": "Avengers: Infinity War",
    "железный человек": "Iron Man (2008 film)",
    "чёрная вдова": "Black Widow (2021 film)",
    "флэш": "The Flash (2023 film)",
    "человек-паук": "Spider-Man (2002 film)",
    "чёрная пантера": "Black Panther (2018 film)",
    "стражи галактики": "Guardians of the Galaxy (film)",
    "капитан марвел": "Captain Marvel (2019 film)",
    "тёмный рыцарь": "The Dark Knight (2008 film)",
    "дэдпул": "Deadpool (film)",
    "мерзавец на миллион": "Deadpool (film)",
    "тёмный рыцарь восстаёт": "The Dark Knight Rises (2010 film)",
    "халк": "The Incredible Hulk (2008 film)",
    "тор": "Thor (2011 film)",
    "отряд самоубийц": "Suicide Squad (film)",
    "джокер": "Joker (2019 film)",
    "властелин колец": "The Lord of the Rings (film series)",
    "хоббит": "The Hobbit (film series)",
    "матрица": "The Matrix (1999 film)",
    "интерстеллар": "Interstellar (film)",
    "начало": "Inception (2010 film)",
    "гладиатор": "Gladiator (2000 film)",
    "побег из шоушенка": "The Shawshank Redemption (1994 film)",
    "богемская рапсодия": "Bohemian Rhapsody (2018 film)",
    "джон уик": "John Wick (2014 film)",
    "миссия невыполнима": "Mission: Impossible (1996 film)",
    "прибытие": "Arrival (2016 film)",
    "бегущий по лезвию 2049": "Blade Runner 2049 (2017 film)",
    "парк юрского периода": "Jurassic Park (1993 film)",
    "мир юрского периода": "Jurassic World (2015 film)",
    "тихоокеанский рубеж": "Pacific Rim (2013 film)",
    "терминатор": "The Terminator (1984 film)",
    "терминатор 2": "Terminator 2: Judgment Day (1991 film)",
    "пираты карибского моря": "Pirates of the Caribbean (film series)",
    "холодное сердце": "Frozen (2013 film)",
    "красавица и чудовище": "Beauty and the Beast (1991 film)",
    "оно": "It (2017 film)",
    "доктор стрэнж": "Doctor Strange (2016 film)",
    "пятый элемент": "The Fifth Element",
    "мстители: эпоха альтрона": "Avengers: Age of Ultron (2015 film)",
    "кэрол": "Carol (2015 film)",
    "скаут": "The Boy in the Striped Pajamas (2008 film)",
    "джентльмены": "The Gentlemen (2019 film)",
    "одни в дома": "Home Alone (film)",
    "список шиндлера": "Schindler's List",
    "крёстный отец": "The Godfather (1972 film)",
    "тихий дом": "A Quiet Place (2018 film)",
    "гравитация": "Gravity (2013 film)",
    "алита": "Alita: Battle Angel (2019 film)",
    "акула": "Jaws (film)",
    "хищник": "Predator (1987 film)",
    "красотка": "Pretty Woman (1990 film)",
    "армагеддон": "Armageddon (film)",
    "армагеддон (1998)": "Armageddon (film)",
    "армагеддон (1998 фильм)": "Armageddon (film)",
    "троя": "Troy (film)",
    "троя (2004)": "Troy (film)",
    "троя (2004 фильм)": "Troy (film)",
    "игры разума": "A Beautiful Mind (film)",
    "красивый ум": "A Beautiful Mind (film)",
    "а beautiful mind": "A Beautiful Mind (film)",
    "a beautiful mind": "A Beautiful Mind (film)",
}

# Build auto RU→EN reverse map from IMDb data
_IMDB_RU_TO_EN: dict[str, str] = {}
for en, ru in _IMDB_EN_TO_RU.items():
    _IMDB_RU_TO_EN[ru.lower()] = en

_IMDB_RU_WORDS = {
    key: set(key.split()) for key in _IMDB_RU_TO_EN
}
_IMDB_FUZZY_ENTRIES = sorted(
    _IMDB_RU_TO_EN.items(), key=lambda item: len(item[0]), reverse=True
)[:3000]

_IMDB_CORE_TO_RU: dict[str, str] = {}
for en, ru in _IMDB_EN_TO_RU.items():
    core = en.lower().split(" (")[0].strip()
    _IMDB_CORE_TO_RU.setdefault(core, ru)


# ── Public functions ──────────────────────────────────────────────────


def get_russian_name(english_title: str) -> str | None:
    """Get Russian name for an English title (from IMDb akas)."""
    return _IMDB_EN_TO_RU.get(english_title) or _IMDB_CORE_TO_RU.get(
        english_title.lower().split(" (")[0].strip()
    )


def resolve_movie(query: str) -> str | None:
    """Resolve a Russian or alias title to its English IMDb title.
    
    Returns the English title if found, None otherwise.
    """
    import unicodedata
    from difflib import SequenceMatcher
    norm = query.strip().lower().replace("–", "-").replace("—", "-")
    words = norm.split()
    
    # 1. Direct fallback map
    if norm in _FALLBACK_RU_TO_EN:
        return _FALLBACK_RU_TO_EN[norm]
    
    # 2. IMDb reverse map (RU → EN)
    if norm in _IMDB_RU_TO_EN:
        return _IMDB_RU_TO_EN[norm]
    
    # 3. Word match in IMDb reverse (require all query words to match)
    if len(words) >= 2:
        best_wm = None
        best_wm_score = 0
        for key, val in _IMDB_RU_TO_EN.items():
            kw = _IMDB_RU_WORDS[key]
            matched = sum(1 for w in words if w in kw)
            if matched >= min(len(words), 2):
                score = matched / len(words)
                if score > best_wm_score or (score == best_wm_score and len(key) > len(best_wm or '')):
                    best_wm_score = score
                    best_wm = val
        if best_wm_score == 1.0:
            return best_wm
    
    # 4. Partial match in fallback (require significant overlap)
    best = None
    best_len = 0
    for key, val in _FALLBACK_RU_TO_EN.items():
        if len(key) >= 4 and key in norm and len(key) > best_len:
            best = val
            best_len = len(key)
    if best and best_len >= len(norm) * 0.5:
        return best
    
    # 5. Partial substring match in IMDb reverse
    best_partial = None
    best_partial_len = 0
    for key, val in _IMDB_RU_TO_EN.items():
        if len(key) >= 6:
            if norm in key or (len(norm) >= 8 and key in norm):
                if len(key) > best_partial_len:
                    best_partial = val
                    best_partial_len = len(key)
    if best_partial and best_partial_len >= len(norm) * 0.7:
        return best_partial
    
    # 6. Fuzzy match against IMDb reverse map
    if len(norm) >= 4:
        best_score = 0
        for key, val in _IMDB_FUZZY_ENTRIES:
            s = SequenceMatcher(None, norm, key.lower()).ratio()
            if s > best_score:
                best_score = s
                if s >= 0.85:
                    return val
    return None


EN_TO_RU = _IMDB_EN_TO_RU