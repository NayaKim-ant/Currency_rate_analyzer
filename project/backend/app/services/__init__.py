"""Domain service subpackages and high-level facades."""

from app.services.alerts.engine import evaluate_alert_rules
from app.services.forecasting.outlook import filter_news_hints, timing_signal
from app.services.forecasting.scorecard import settle_forecasts
from app.services.news.collector import fetch_news_history, store_news_articles
from app.services.news.facts import extract_news_facts
from app.services.news.relevance import score_article
from app.services.pipeline.runner import drain_jobs
from app.services.pipeline.scheduler import create_scheduler
from app.services.pipeline.state_machine import claim_job, enqueue_job
from app.services.rates.analyzer import analyze_market
from app.services.rates.collector import collect_recent_rates
from app.services.rates.signals import detect_price_signals, detect_trend_reversals
from app.services.rates.trends import build_rate_points, classify_trend, moving_average

__all__ = [
    "analyze_market",
    "build_rate_points",
    "claim_job",
    "classify_trend",
    "collect_recent_rates",
    "create_scheduler",
    "detect_price_signals",
    "detect_trend_reversals",
    "drain_jobs",
    "enqueue_job",
    "evaluate_alert_rules",
    "extract_news_facts",
    "fetch_news_history",
    "filter_news_hints",
    "moving_average",
    "score_article",
    "settle_forecasts",
    "store_news_articles",
    "timing_signal",
]
