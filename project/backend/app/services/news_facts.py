"""Local, extractive news signals. Excerpts are claims, not verified truth."""

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.locks import lock_market_writes
from app.models.forecasts import NewsFact
from app.models.market import Article
from app.services.economic_events import economic_event

VERSION = "local-events-v3"
FACTORS = {
    "interest_rates": r"\b(?:interest rates?|rate cuts?|rate hikes?|monetary policy|policy rates?|(?:hikes?|cuts?|raises?|lowers?)\s+(?:its\s+)?rates?)\b|기준금리|금리",
    "inflation": r"\b(?:inflation|consumer prices?|CPI|PCE)\b|물가|인플레이션",
    "growth": r"\b(?:GDP|economic growth|recession|economic contraction)\b|경제성장|국내총생산",
    "employment": r"\b(?:unemployment|payrolls?|employment|jobless)\b|고용|실업률",
    "trade": r"\b(?:tariffs?|trade deficit|trade surplus|exports?|imports?)\b|관세|수출|수입",
    "risk": r"\b(?:geopolitical|war|conflict|risk aversion|safe haven|oil prices?)\b|지정학|전쟁|유가",
}
ENTITIES = {
    "USD": r"\b(?:Federal Reserve|(?-i:Fed|FED)|U\.S\.?|United States|US dollar|American|(?-i:US))\b|연준|미국",
    "KRW": r"\b(?:Bank of Korea|South Korea|Korean|BOK)\b|한국은행|한국",
    "EUR": r"\b(?:European Central Bank|ECB|eurozone|euro area|euro)\b|유럽중앙은행",
    "JPY": r"\b(?:Bank of Japan|BOJ|Japan|Japanese|yen)\b|일본은행|일본",
    "GBP": r"\b(?:Bank of England|BOE|British|Britain|United Kingdom|sterling)\b|영란은행|영국",
    "CNY": r"\b(?:PBOC|People.s Bank of China|China|Chinese|yuan|renminbi)\b|중국",
    "AUD": r"\b(?:RBA|Reserve Bank of Australia|Australia|Australian)\b|호주",
    "CAD": r"\b(?:Bank of Canada|Canada|Canadian)\b|캐나다",
    "CHF": r"\b(?:Swiss National Bank|Switzerland|Swiss|SNB)\b|스위스",
}
UP = r"\b(?:raised?|hiked?|increased?|rose|rises?|rising|accelerated?|higher)\b|인상|상승"
DOWN = r"\b(?:cuts?|lowered?|decreased?|fell|falls?|falling|slowed?|lower)\b|인하|하락"
FORWARD = r"\b(?:expects?|expected|forecast\w*|could|might|(?-i:may)|will|likely|project\w*|predict\w*)\b|전망|예상"
OBSERVED = r"\b(?:announced|reported|released|held|kept|left|unchanged)\b|발표|동결"
FIGURE = re.compile(r"(?<!\w)(-?\d+(?:\.\d+)?)\s*(%|percent(?:age points?)?|basis points?|bps)\b|(?<!\w)(-?\d+(?:\.\d+)?)\s*(%)", re.I)


@dataclass(frozen=True)
class Candidate:
    factor: str
    currencies: list[str]
    direction: str
    claim_type: str
    figures: list[dict]
    evidence: str
    event: dict = field(default_factory=dict)


def extract_candidates(title: str, content: str) -> list[Candidate]:
    # Preserve exact source excerpts. A decimal point is not a sentence boundary.
    snippets = [title] + re.split(r"(?<=[.!?])\s+|[;\n]+", content)
    results = []
    seen = set()
    for snippet in snippets:
        snippet = snippet.strip()
        if not snippet or len(snippet) > 1500:
            continue
        currencies = sorted(currency for currency, pattern in ENTITIES.items() if re.search(pattern, snippet, re.I))
        direction_text = re.sub(r"\b(?:higher|lower)\s+than\s+(?:expected|(?:market\s+)?expectations?)\b", "", snippet, flags=re.I)
        up, down = bool(re.search(UP, direction_text, re.I)), bool(re.search(DOWN, direction_text, re.I))
        negated = bool(re.search(r"\b(?:not|never|no longer)\b|않", snippet, re.I))
        direction = "unspecified" if up == down or negated else "increase" if up else "decrease"
        if re.search(r"\b(?:unchanged|held steady|kept steady)\b|동결", snippet, re.I):
            direction = "unchanged"
        figures = []
        for match in FIGURE.finditer(snippet):
            figures.append({"text": match.group(0), "value": float(match.group(1) or match.group(3)),
                            "unit": match.group(2) or match.group(4)})
        classification_text = snippet
        if re.search(r"\b(?:fell|rose|raised|reported|released|held|kept|came|recorded)\b|발표|기록", snippet, re.I):
            classification_text = re.sub(r"\b(?:expected|forecast)\s+(?:at\s+)?-?\d+(?:\.\d+)?\s*%|-?\d+(?:\.\d+)?\s*%\s+(?:was\s+)?(?:expected|forecast)\b|예상치", "", snippet, flags=re.I)
        claim = "forward_looking" if re.search(FORWARD, classification_text, re.I) else (
            "reported" if figures or up or down or re.search(OBSERVED, snippet, re.I) else "commentary"
        )
        for factor, pattern in FACTORS.items():
            if re.search(pattern, snippet, re.I) and (factor, snippet.casefold()) not in seen:
                seen.add((factor, snippet.casefold()))
                # Several economic variables in one sentence cannot safely share a direction.
                matched_factors = sum(bool(re.search(p, snippet, re.I)) for p in FACTORS.values())
                assigned = matched_factors == 1 and len(currencies) == 1
                event_direction = direction if assigned else "unspecified"
                event = economic_event(snippet, factor, currencies, claim, event_direction, matched_factors != 1)
                results.append(Candidate(factor, currencies, event_direction,
                    claim, [dict(figure, assigned=assigned and event["attribution"] != "ambiguous") for figure in figures], snippet, event))
    return results


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def extract_news_facts(session: Session, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    lock_market_writes(session)
    rows = list(session.scalars(select(NewsFact)))
    existing = {(row.article_id, row.evidence_hash) for row in rows}
    count = 0
    for article in session.scalars(select(Article)):
        candidates = extract_candidates(article.title, article.content or article.summary or "")
        active = {}
        for row in rows:
            if row.article_id == article.id and row.superseded_at is None:
                value = Candidate(row.factor, row.currencies, row.direction, row.claim_type, row.figures, row.evidence, row.event or {})
                active[hashlib.sha256(json.dumps(asdict(value), sort_keys=True).encode()).hexdigest()] = row
        current = set()
        for candidate in candidates:
            digest = hashlib.sha256(json.dumps(asdict(candidate), sort_keys=True).encode()).hexdigest()
            current.add(digest)
            if digest in active:
                continue
            key = (article.id, digest)
            if key in existing:
                # An older excerpt reappeared after a revision: keep both vintages.
                digest = hashlib.sha256((digest + as_utc(now).isoformat()).encode()).hexdigest()
                key = (article.id, digest)
            existing.add(key)
            timestamps = [as_utc(now), as_utc(article.fetched_at)]
            if article.published_at:
                timestamps.append(as_utc(article.published_at))
            session.add(NewsFact(article_id=article.id, evidence_hash=digest, **asdict(candidate),
                                 source_title=article.title, source_url=article.url, published_at=article.published_at,
                                 available_at=max(timestamps), extractor_version=VERSION))
            count += 1
        for digest, row in active.items():
            if digest not in current:
                row.superseded_at = as_utc(now)
    session.commit()
    return count
