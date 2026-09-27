from ml.monitor_model import ratio


def test_ratio_handles_expected_zero():
    assert ratio(0.2, 0.0) is None


def test_ratio_describes_score_share_change():
    assert ratio(0.20, 0.10) == 2.0
