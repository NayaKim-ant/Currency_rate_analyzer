# Historical data and honest forecast evaluation

Verified import on 2026-10-17: 11,872 KRW-pair records (1,484 observations for each of eight foreign currencies), covering 2021-01-04 through 2026-10-16. The article archive grew from 123 to 2,350 records; the targeted search began on 2024-01-01. Several news windows reached the 100-result cap, so the archive is incomplete. Analysis job 180 and forecast job 181 were queued for refresh. All 72 backend tests passed.

## Explicit archive import

From `project/backend`, the bounded importer expands the archive without increasing every startup's lookback:

```powershell
.\.venv\Scripts\python.exe -m app.workers.backfill_archive --rates-start 2021-01-01 --news-start 2024-01-01 --end 2026-10-16
```

Either start flag can be omitted. `--query` accepts a targeted RSS search; `--news-batch-days` controls windows of 1–90 days (default 30). The default news search targets Korean won, Bank of Korea, and Federal Reserve exchange-rate/inflation/interest-rate coverage. It is not comprehensive coverage of all eight currencies. The daily collectors keep their existing lookbacks.

The command shares the pipeline worker advisory lock and refuses to start while another worker owns it. Rate batches cover at most 365 calendar days, news batches commit separately, and requests are paced by one second. Successful batches survive a later failure. Rerunning upserts existing pair/date and article URL records. Printed counts are processed records, not necessarily newly inserted records. It queues normal analysis and forecast jobs afterward; a running worker must process those jobs.

Rates use the existing Decimal USD-cross conversion for all eight KRW pairs. Returned observations outside a batch's date range are discarded. News uses dated RSS searches, retains title/summary/link, rejects undated/out-of-window results, and deduplicates URLs. It does not retrieve historical article bodies or guarantee the provider exposes every matching story. Windows returning 100 results are flagged as possibly truncated; smaller windows and additional queries may improve coverage. Different URLs for the same story can remain in the article archive; the model additionally deduplicates matching evidence.

News publication time and collection time remain separate. Old articles collected now do not automatically become eligible inputs to a historical backtest. Verified archived vintages would require additional provenance and evaluation support. Today's article text may differ from the version originally published. Similarly, the rate archive contains the provider's currently returned historical values, not independently preserved original release vintages.

## Save a forecast before the outcome

Example: before the next daily quote exists, save a forecast of KRW 1,400 per USD together with its timestamp, source quote date, model/configuration, inputs/version, and target definition. When the source later publishes the next observation at KRW 1,410, record an absolute error of KRW 10. Never replace the original forecast with a new estimate made after observing that result.

Stored forecast runs preserve predictions and model metadata. The subsequent [forward scorecard extension](news-forecasting.md#forward-prediction-scorecard) now matches issued predictions to later outcomes and uses sufficient historical forward evidence to gate future choices. This is separate from the archive importer. Same-day and late predictions are conservatively excluded even if the local database had not yet collected the target quote.

## Keep a final evaluation period untouched

An illustrative split is 2021–2023 for training, 2024 for choosing settings/models, and 2025 for final evaluation. Choose the model before inspecting the 2025 result. If that result guides another change, it has become development data; use a new untouched period or future predictions for independent evaluation. These are example dates, not the current implementation's split. The existing model uses two 20-observation validation blocks and a final 20-observation test block. Repeatedly using its displayed test score to choose changes also compromises that score's independence.

## Economic indicators and publication timing

For USD/KRW, possible features include US minus Korean policy rates, US minus Korean inflation measured on a comparable basis, and US minus Korean bond yields at the same maturity. For example, hypothetical policy rates of 4% and 3% produce a +1 percentage-point difference. Such features describe conditions; they do not imply a fixed exchange-rate direction.

September inflation released on October 15 cannot be used in an October 10 prediction. If it was first reported as 3.0% and revised to 3.2% on November 15, an October prediction must use 3.0%. Store observation period, actual publication timestamp/timezone, vintage/revision availability, value, units, and source separately. On each forecast cutoff, select only versions already public. If only a publication date is known, use a conservative availability cutoff rather than pretending a precise release time is known. Rate reference dates also differ from the time their quotes become available.

Economic-indicator ingestion and vintage-aware macro features are not implemented by this archive command.

## Sources

- [Frankfurter v1 historical and time-series API](https://frankfurter.dev/v1/): compatible with the existing collector; v1 remains available although superseded by v2.
- [Federal Reserve historical materials](https://www.federalreserve.gov/monetarypolicy/fomc_historical.htm): an additional source to investigate for official policy statements. A document's meeting date is not necessarily its public release date; some materials are released later.
- [ALFRED help](https://alfred.stlouisfed.org/help): explains economic-data vintages, revisions, and release dates. This is a candidate source for future macro ingestion, not a dependency of the importer.
