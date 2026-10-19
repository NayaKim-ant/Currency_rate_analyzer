from datetime import date, datetime, timezone

import pytest

from app.services.news import NewsArticleData
from app.workers.backfill_archive import filter_news, windows


def test_archive_windows_cover_leap_day_once_and_validate():
    assert list(windows(date(2024, 2, 28), date(2024, 3, 2), 2)) == [
        (date(2024, 2, 28), date(2024, 2, 29)), (date(2024, 3, 1), date(2024, 3, 2))]
    with pytest.raises(ValueError):
        list(windows(date(2024, 3, 2), date(2024, 2, 28), 2))


def test_archive_rejects_out_of_window_undated_and_duplicate_articles():
    def item(day, url):
        return NewsArticleData("Policy update", "", url,
                               datetime(2024, 1, day, tzinfo=timezone.utc) if day else None), ""
    seen = set()
    accepted = filter_news([item(1, "early"), item(2, "valid"), item(2, "valid"),
                            item(4, "late"), item(None, "undated")], date(2024, 1, 2), date(2024, 1, 3), seen)
    assert [article.url for article, _ in accepted] == ["valid"]
    assert filter_news([item(2, "valid")], date(2024, 1, 2), date(2024, 1, 3), seen) == []
