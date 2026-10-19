"""Explicit, bounded historical imports; ordinary daily lookbacks stay unchanged."""

import argparse
import json
import time
from datetime import date, timedelta

from app.db.session import SessionLocal
from app.services.collection import fetch_rate_history, store_rate_history
from app.services.job_runner import worker_guard
from app.services.jobs import enqueue_job
from app.services.news import fetch_news_articles, store_news_articles
from app.services.news_facts import extract_news_facts

ARCHIVE_QUERY = '("Korean won" OR "Bank of Korea" OR "Federal Reserve") ("exchange rate" OR inflation OR "interest rates")'


def windows(start: date, end: date, days: int):
    if end < start or days < 1:
        raise ValueError("Invalid date range or batch size")
    while start <= end:
        stop = min(start + timedelta(days=days - 1), end)
        yield start, stop
        start = stop + timedelta(days=1)


def filter_news(items, start, end, seen):
    accepted = []
    for article, content in items:
        # A dated search is only a suggestion to the provider, not proof.
        if article.published_at is None or not start <= article.published_at.date() <= end:
            continue
        if article.url in seen:
            continue
        seen.add(article.url)
        accepted.append((article, content))
    return accepted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rates-start", type=date.fromisoformat)
    parser.add_argument("--news-start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--query", default=ARCHIVE_QUERY)
    parser.add_argument("--news-batch-days", type=int, default=30)
    args = parser.parse_args()
    if not (args.rates_start or args.news_start):
        parser.error("Provide --rates-start and/or --news-start")
    if args.end > date.today() or not 1 <= args.news_batch_days <= 90:
        parser.error("End must not be in the future; news batches must be 1–90 days")
    if any(start and start > args.end for start in (args.rates_start, args.news_start)):
        parser.error("Start must not follow end")
    # Coordinate with the existing worker before writing any archive data.
    with worker_guard(SessionLocal) as acquired:
        if not acquired:
            raise SystemExit("A pipeline worker is busy. Retry this command when Background logs are idle.")
        if args.rates_start:
            for start, end in windows(args.rates_start, args.end, 365):
                records = [row for row in fetch_rate_history(start, end) if start <= row["rate_date"] <= end]
                with SessionLocal() as session:
                    count = store_rate_history(session, records)
                print(json.dumps({"type": "rates", "start": str(start), "end": str(end), "processed": count}), flush=True)
                time.sleep(1)
        if args.news_start:
            seen = set()
            for start, end in windows(args.news_start, args.end, args.news_batch_days):
                items = fetch_news_articles(start_date=start, end_date=end, include_body=False, query=args.query)
                accepted = filter_news(items, start, end, seen)
                with SessionLocal() as session:
                    count = store_news_articles(session, accepted)
                print(json.dumps({"type": "news", "start": str(start), "end": str(end), "returned": len(items),
                                  "processed": count, "possibly_truncated": len(items) >= 100}), flush=True)
                time.sleep(1)
            with SessionLocal() as session:
                print(json.dumps({"new_evidence": extract_news_facts(session)}), flush=True)
        with SessionLocal() as session:
            analysis_id = enqueue_job(session, "analysis", source="cli").id
            forecast_id = enqueue_job(session, "forecast", source="cli").id
        print(json.dumps({"analysis_job": analysis_id, "forecast_job": forecast_id}), flush=True)


if __name__ == "__main__":
    main()
