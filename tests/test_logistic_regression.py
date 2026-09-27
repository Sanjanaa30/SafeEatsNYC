import numpy as np
import pandas as pd
from sklearn.metrics import precision_score

from ml.train_logistic_regression import risk_categories, select_risk_thresholds
from ml.tune_calibrate_logistic import date_folds


def test_risk_categories_respect_both_thresholds():
    categories = risk_categories(np.array([0.05, 0.20, 0.70]), 0.10, 0.50)
    assert categories.tolist() == ["LOW", "MODERATE", "HIGH"]


def test_selected_thresholds_are_ordered_and_bounded():
    labels = np.array([0, 0, 0, 1, 1, 1])
    probabilities = np.array([0.02, 0.10, 0.25, 0.30, 0.60, 0.90])
    moderate, high = select_risk_thresholds(labels, probabilities)
    assert 0 <= moderate < high <= 1


def test_high_threshold_uses_precision_floor_when_supported():
    labels = np.array([0, 0, 0, 0, 1, 0, 1, 1])
    probabilities = np.array([0.05, 0.10, 0.20, 0.55, 0.60, 0.65, 0.70, 0.90])
    _, high = select_risk_thresholds(labels, probabilities)
    predictions = (probabilities >= high).astype("int8")
    assert precision_score(labels, predictions) >= 0.35


def test_date_folds_never_mix_the_same_date_across_time():
    dates = pd.Series(pd.to_datetime([f"2026-01-{day:02d}" for day in range(1, 16)]))
    for train_mask, validation_mask in date_folds(dates, splits=3):
        assert dates[train_mask].max() < dates[validation_mask].min()
