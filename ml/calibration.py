"""Reusable probability-calibration helpers for saved SafeEats models."""

from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression


class PlattCalibratedModel:
    """Apply an out-of-fold sigmoid calibration map to a fitted classifier."""

    def __init__(self, base_model, calibrator: LogisticRegression):
        self.base_model = base_model
        self.calibrator = calibrator

    @staticmethod
    def logits(probabilities: np.ndarray) -> np.ndarray:
        clipped = np.clip(probabilities, 1e-6, 1 - 1e-6)
        return np.log(clipped / (1 - clipped)).reshape(-1, 1)

    def predict_proba(self, features) -> np.ndarray:
        raw = self.base_model.predict_proba(features)[:, 1]
        calibrated = self.calibrator.predict_proba(self.logits(raw))[:, 1]
        return np.column_stack([1 - calibrated, calibrated])
