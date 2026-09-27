import pandas as pd
import pytest

from ml.prepare_training_data import (
    MODEL_FEATURES,
    convert_types,
    validate_leakage_boundary,
)


def example_frame() -> pd.DataFrame:
    values = {column: ["1"] for column in MODEL_FEATURES}
    values.update(
        {
            "prediction_anchor_date": ["2026-01-01"],
            "target_inspection_date": ["2026-02-01"],
            "target_is_bc": ["1"],
            "previous_inspection_had_critical_violation": ["true"],
            "historical_grades_consistent": ["false"],
        }
    )
    return pd.DataFrame(values)


def test_type_conversion_and_leakage_validation_accept_past_only_row():
    frame = convert_types(example_frame())
    validate_leakage_boundary(frame)
    assert frame.loc[0, "previous_inspection_had_critical_violation"] == 1.0
    assert frame.loc[0, "historical_grades_consistent"] == 0.0


def test_leakage_validation_rejects_non_future_target_date():
    frame = example_frame()
    frame["target_inspection_date"] = "2026-01-01"
    with pytest.raises(ValueError, match="future information"):
        validate_leakage_boundary(convert_types(frame))
