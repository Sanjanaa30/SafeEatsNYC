import numpy as np

from ml.calibration import PlattCalibratedModel
from ml.retrain_and_score import readable_feature


def test_logit_conversion_is_finite_at_probability_edges():
    values = PlattCalibratedModel.logits(np.array([0.0, 0.5, 1.0]))
    assert np.isfinite(values).all()


def test_readable_feature_removes_pipeline_prefixes():
    assert readable_feature("numeric__previous_score") == "previous score"
