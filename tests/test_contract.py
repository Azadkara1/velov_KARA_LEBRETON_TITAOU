import pandas as pd
import pandera.errors
import pytest

from velov.contract import validate_gold


def _gold() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "station_id": [1, 1],
            "timestamp": pd.to_datetime(["2026-06-01T06:00Z", "2026-06-01T07:00Z"]),
            "capacity": [20, 20],
            "bikes_available": [8, 5],
            "temperature": [21.0, 22.0],
            "is_raining": [False, True],
            "bikes_next_hour": [5, 6],
        }
    )


def test_valid_gold_passes():
    assert len(validate_gold(_gold())) == 2


def test_more_bikes_than_capacity_is_rejected():
    df = _gold()
    df.loc[0, "bikes_next_hour"] = 25
    with pytest.raises(pandera.errors.SchemaErrors):
        validate_gold(df)


def test_missing_column_is_rejected():
    with pytest.raises(pandera.errors.SchemaErrors):
        validate_gold(_gold().drop(columns=["temperature"]))


def test_naive_timestamp_is_rejected():
    df = _gold()
    df["timestamp"] = df["timestamp"].dt.tz_localize(None)
    with pytest.raises(pandera.errors.SchemaErrors):
        validate_gold(df)


def test_duplicate_key_is_rejected():
    df = pd.concat([_gold(), _gold().iloc[[0]]], ignore_index=True)
    with pytest.raises(pandera.errors.SchemaErrors):
        validate_gold(df)
