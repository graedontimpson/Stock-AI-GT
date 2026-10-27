"""Logistic regression: the probability that a stock rises over the horizon."""

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from stock_ai.errors import NotEnoughHistoryError
from stock_ai.shapes import Contribution
from stock_ai.signals import FEATURES, LABELS

MIN_TRAINING_ROWS = 500


@dataclass
class TrainedModel:
    scaler: StandardScaler
    classifier: LogisticRegression
    features: list

    @property
    def starting_point(self) -> float:
        """The probability for a stock whose every signal is exactly average."""
        return _sigmoid(self.classifier.intercept_[0])


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def train(training_table: pd.DataFrame, features: list | None = None) -> TrainedModel:
    features = list(features or FEATURES)
    rows = training_table.dropna(subset=["rose"])
    if len(rows) < MIN_TRAINING_ROWS or rows["rose"].nunique() < 2:
        raise NotEnoughHistoryError()
    # Standardizing is worked out from these training rows only.
    scaler = StandardScaler().fit(rows[features].to_numpy())
    classifier = LogisticRegression(max_iter=1000)
    classifier.fit(scaler.transform(rows[features].to_numpy()), rows["rose"].astype(int).to_numpy())
    return TrainedModel(scaler=scaler, classifier=classifier, features=features)


def predict_many(model: TrainedModel, rows: pd.DataFrame) -> np.ndarray:
    return model.classifier.predict_proba(model.scaler.transform(rows[model.features].to_numpy()))[:, 1]


def predict(model: TrainedModel, latest_signals: pd.Series) -> tuple[float, list[Contribution]]:
    """Probability of rising, and how much each signal moved it.

    Each signal's share of the model's score is turned into percentage points so
    that the effects add up exactly to (probability - starting point).
    """
    values = latest_signals[model.features].to_numpy(dtype=float)
    scaled = model.scaler.transform(values.reshape(1, -1))[0]
    pieces = model.classifier.coef_[0] * scaled
    intercept = model.classifier.intercept_[0]
    probability = _sigmoid(intercept + pieces.sum())
    moved = probability - _sigmoid(intercept)
    total = pieces.sum()
    effects = pieces * (moved / total) if total != 0 else np.zeros_like(pieces)

    contributions = [
        Contribution(signal=name, label=LABELS[name], value=float(value), effect=float(effect * 100))
        for name, value, effect in zip(model.features, values, effects)
    ]
    contributions.sort(key=lambda c: abs(c.effect), reverse=True)
    return float(probability), contributions
