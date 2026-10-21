from decimal import Decimal

import pytest

from app.services.news.relevance import score_article


def test_relevance_scores_currency_and_policy_matches_separately() -> None:
    result = score_article(
        "Fed signals an interest rate cut",
        "The dollar moved as the Federal Reserve discussed monetary policy.",
        "KRW",
    )

    assert result.score == Decimal("70")
    assert "dollar" in result.matched_keywords
    assert "interest rate" in result.policy_keywords
    assert "monetary policy" in result.policy_keywords


def test_relevance_does_not_match_partial_words() -> None:
    result = score_article("The countryside won a prize", None, "KRW")

    assert result.matched_keywords == ()
    assert result.score == Decimal("0")


def test_relevance_rejects_unknown_currency() -> None:
    with pytest.raises(ValueError, match="unsupported target currency"):
        score_article("Currency markets", None, "XYZ")
