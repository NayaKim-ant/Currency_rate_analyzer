import pytest

from app.services.news_facts import extract_candidates


@pytest.mark.parametrize("text,actual,previous,expected,surprise", [
    ("US inflation fell to 3% from 4%, above expectations.", 3, 4, None, "above"),
    ("US inflation rose to 3% from 2%, expected at 2.8%.", 3, 2, 2.8, "above"),
    ("US inflation fell to 2%, versus 3% expected.", 2, None, 3, "below"),
    ("US inflation was reported at 3%, expected 3%.", 3, None, 3, "in_line"),
    ("US inflation was reported at 3%, expected 2%, below expectations.", 3, None, 2, "conflicting"),
    ("한국은행 기준금리 3.0% 동결", 3, None, None, None),
])
def test_structured_actual_previous_expected_and_surprise(text, actual, previous, expected, surprise):
    fact = extract_candidates(text, "")[0]
    assert fact.claim_type == "reported"
    assert fact.event["actual"] == actual
    assert fact.event["previous"] == previous
    assert fact.event["expected"] == expected
    assert fact.event["surprise"] == surprise


@pytest.mark.parametrize("text", [
    "US inflation could fall to 3%.",
    "US inflation is expected to fall to 3%.",
    "US inflation did not fall to 3%.",
    "US inflation fell to 3% while interest rates rose to 5%.",
    "US and Korean inflation fell to 3%.",
    "Inflation fell to 3%.",
    "US inflation rose to 3% in January and to 4% in February.",
    "The Fed held interest rates at 5.25%-5.5%.",
])
def test_does_not_invent_actuals_for_forecasts_negation_or_ambiguous_attribution(text):
    assert all(f.event["actual"] is None for f in extract_candidates(text, ""))


def test_explicit_basis_point_change_is_not_confused_with_level_or_percent_change():
    event = extract_candidates("The Fed raised interest rates by 25 basis points to 5.25%.", "")[0].event
    assert event["actual"] == 5.25 and event["change_basis_points"] == 25
    event = extract_candidates("The Fed cut interest rates by 0.25 percentage points to 5%.", "")[0].event
    assert event["change_basis_points"] == -25
    assert extract_candidates("US inflation fell by 2%.", "")[0].event["actual"] is None
    assert extract_candidates("US inflation fell by 2%.", "")[0].event["change_basis_points"] is None
    range_fact = extract_candidates("The Fed held interest rates at 5.25%-5.5%.", "")[0]
    assert not any(f["assigned"] for f in range_fact.figures)
