import re
from dataclasses import dataclass
from decimal import Decimal

CURRENCY_TERMS = {
    "USD": ("us dollar", "u.s. dollar", "american dollar", "greenback"),
    "AUD": ("australian dollar", "aussie dollar"),
    "CAD": ("canadian dollar",),
    "CHF": ("swiss franc",),
    "CNY": ("chinese yuan", "renminbi", "yuan"),
    "EUR": ("euro", "european currency"),
    "GBP": ("british pound", "sterling", "pound sterling"),
    "JPY": ("japanese yen", "yen"),
    "KRW": ("south korean won", "korean won", "korean currency"),
}

GENERAL_TERMS = {
    "exchange rate": (3, "general"),
    "forex": (3, "general"),
    "currency": (2, "general"),
    "foreign exchange": (3, "general"),
    "dollar": (2, "general"),
    "central bank": (3, "policy"),
    "interest rate": (3, "policy"),
    "rate hike": (3, "policy"),
    "rate cut": (3, "policy"),
    "monetary policy": (3, "policy"),
    "inflation": (2, "policy"),
    "Federal Reserve": (3, "policy"),
    "European Central Bank": (3, "policy"),
    "Bank of Japan": (3, "policy"),
}


@dataclass(frozen=True)
class RelevanceResult:
    score: Decimal
    matched_keywords: tuple[str, ...]
    policy_keywords: tuple[str, ...]


def score_article(title: str, content: str | None, target_currency: str) -> RelevanceResult:
    currency = target_currency.upper()
    if currency not in CURRENCY_TERMS:
        raise ValueError(f"unsupported target currency: {currency}")

    normalized_text = re.sub(r"\s+", " ", f"{title} {content or ''}".casefold())
    matched: list[str] = []
    policy: list[str] = []
    weight_total = 0

    weighted_terms = dict(GENERAL_TERMS)
    weighted_terms.update({term: (2, "currency") for term in CURRENCY_TERMS[currency]})
    for term, (weight, category) in weighted_terms.items():
        pattern = rf"(?<!\w){re.escape(term.casefold())}(?!\w)"
        if re.search(pattern, normalized_text):
            matched.append(term)
            weight_total += weight
            if category == "policy":
                policy.append(term)

    score = min(Decimal("100"), Decimal(weight_total * 5))
    return RelevanceResult(
        score=score,
        matched_keywords=tuple(sorted(matched)),
        policy_keywords=tuple(sorted(policy)),
    )
