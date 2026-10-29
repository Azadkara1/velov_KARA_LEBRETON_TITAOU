"""Règle de promotion challenger -> champion : une condition violée = refus, et la raison est dite."""

import pytest

from velov.registry import DEFAULT_MARGIN, DEFAULT_PEAK_TOLERANCE, decide


def metrics(mae=1.30, baseline=1.88, peak=1.40):
    return {"mae_model": mae, "mae_baseline_persistence": baseline, "mae_model_peak_hours": peak}


CHAMPION = metrics(mae=1.34, peak=1.42)


def test_first_model_is_promoted_if_it_beats_baseline():
    assert decide(metrics(), champion=None).promote


def test_first_model_is_refused_if_worse_than_baseline():
    d = decide(metrics(mae=2.0), champion=None)
    assert not d.promote
    assert d.reasons[0].startswith("1.")


def test_clearly_better_challenger_is_promoted():
    d = decide(metrics(mae=1.34 - DEFAULT_MARGIN - 0.01, peak=1.40), CHAMPION)
    assert d.promote and d.reasons == []


def test_gain_below_margin_is_refused_as_noise():
    d = decide(metrics(mae=1.34 - DEFAULT_MARGIN / 2), CHAMPION)
    assert not d.promote
    assert any(r.startswith("2.") for r in d.reasons)


def test_gain_exactly_at_margin_is_promoted():
    assert decide(metrics(mae=1.34 - DEFAULT_MARGIN), CHAMPION).promote


def test_better_average_but_worse_at_peak_is_refused():
    d = decide(metrics(mae=1.20, peak=1.42 + DEFAULT_PEAK_TOLERANCE + 0.01), CHAMPION)
    assert not d.promote
    assert [r[0] for r in d.reasons] == ["3"]


def test_all_failures_are_reported_together():
    d = decide(metrics(mae=2.0, peak=9.0), CHAMPION)
    assert [r[0] for r in d.reasons] == ["1", "2", "3"]


@pytest.mark.parametrize("margin", [0.0, 0.5])
def test_margin_is_configurable(margin):
    d = decide(metrics(mae=1.33), CHAMPION, margin=margin)
    assert d.promote == (margin == 0.0)
