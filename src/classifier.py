import numpy as np
from sklearn.linear_model import LogisticRegression, RidgeClassifier, SGDClassifier
from sklearn.svm import SVC, LinearSVC
from sklearn.ensemble import (
    GradientBoostingClassifier, AdaBoostClassifier,
    RandomForestClassifier, VotingClassifier,
)
from sklearn.model_selection import cross_val_score
from src.config import CLASS_OPTION_DESCRIPTION


def get_classifier(name: str, random_state: int = 42):
    """Return a sklearn classifier by name."""
    classifiers = {
        "SVC": lambda: SVC(random_state=random_state),
        "LinearSVC": lambda: LinearSVC(random_state=random_state),
        "LogisticRegression": lambda: LogisticRegression(
            random_state=random_state, max_iter=1000
        ),
        "SGDClassifier": lambda: SGDClassifier(random_state=random_state),
        "RidgeClassifier": lambda: RidgeClassifier(random_state=random_state),
        "GradientBoostingClassifier": lambda: GradientBoostingClassifier(
            random_state=random_state
        ),
        "AdaBoostClassifier": lambda: AdaBoostClassifier(random_state=random_state),
        "RandomForestClassifier": lambda: RandomForestClassifier(
            random_state=random_state
        ),
    }
    if name not in classifiers:
        raise ValueError(f"Unknown classifier: {name}. Available: {list(classifiers.keys())}")
    return classifiers[name]()


def cross_validate(clf, X: np.ndarray, y: np.ndarray, cv: int = 3) -> dict:
    """Run cross-validation and return metrics."""
    from sklearn.metrics import make_scorer, accuracy_score, f1_score
    scores = cross_val_score(clf, X, y, cv=cv, scoring="accuracy")
    f1_scores = cross_val_score(clf, X, y, cv=cv, scoring="f1")
    return {
        "accuracy_mean": scores.mean(),
        "accuracy_std": scores.std(),
        "f1_mean": f1_scores.mean(),
        "f1_std": f1_scores.std(),
    }