"use client";

import { useCallback, useEffect, useState } from "react";
import { FlaskConical, ExternalLink } from "lucide-react";
import { ForecastOutlook, type TimingSignal } from "./forecast-outlook";
import { ForecastLeaderboard, type Leaderboard } from "./forecast-leaderboard";

type Score = { mae_krw: number; direction_accuracy: number | null; samples: number };
type Forecast = {
  status: string; observations: number; minimum_observations?: number; as_of_date: string;
  model: string; current_cost: number; forecast_cost: number; change_percent: number;
  error_band: { lower: number; upper: number }; validation: Record<string, Score>; held_out_test: Record<string, Score>;
  news: { eligible: boolean; training_news_days: number; first_seen_dates: number; validation_news_days: number;
    test_news_days: number; requirements: string; sensitivity_krw: number | null; factor_sensitivities?: Record<string, number> };
  horizon_forecasts?: Record<string, Forecast>;
  recent_costs?: { date: string; cost: number }[];
  forward_selection?: { active: boolean; distinct_outcomes: number; minimum_outcomes: number };
};
type Hint = { id: number; factor: string; currencies: string[]; direction: string; claim_type: string;
  evidence: string; source_title: string; source_url: string; published_at: string | null;
  event?: { actual: number | null; previous: number | null; expected: number | null; unit: string | null;
    change_basis_points: number | null; surprise: string | null; attribution: string } | null };
type Data = { status: string; created_at: string | null; stale: boolean; forecast: Forecast | null;
  hints: Hint[]; recent_factor_count: number; selected_horizon: number; outlook?: Record<string, TimingSignal>;
  leaderboard?: Leaderboard;
  scorecard?: { distinct_outcomes: number; minimum_outcomes: number; window: number;
    candidates: Record<string, { samples: number; mae_krw: number; baseline_mae_krw: number }>;
    recent: { forecast_run_id: number; issued_at: string; target_date: string; model: string;
      actual_cost: number; prediction: number | null; absolute_error: number | null }[] } };
type Job = { id: number; job_type: string; state: string; available_at: string | null; error: string | null };

const models: Record<string, string> = { no_change: "No-change baseline", ridge: "Ridge regression", boosted_trees: "Boosted trees",
  rates_lstm: "Rates-only LSTM", news_lstm: "Rates + news LSTM" };
const channels: Record<string, string> = { interest_rates: "Interest-rate policy", inflation: "Inflation",
  growth: "Economic growth", employment: "Employment", trade: "Trade & tariffs", risk: "Risk & geopolitics" };

function won(value: number) {
  return `₩${new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)}`;
}

async function read(url: string, options?: RequestInit) {
  const response = await fetch(url, { ...options, cache: "no-store", signal: AbortSignal.timeout(15000) });
  const value = await response.json();
  if (!response.ok) throw new Error(typeof value.detail === "string" ? value.detail : "Unable to load forecasts.");
  return value;
}

export function ForecastPanel({ currency }: { currency: string }) {
  const [horizon, setHorizon] = useState(5);
  const [data, setData] = useState<Data | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    const [next, jobs]: [Data, Job[]] = await Promise.all([
      read(`/api/forecasts?target_currency=${currency}&horizon=${horizon}`), read("/api/jobs?limit=50"),
    ]);
    return [next, jobs.find((value) => value.job_type === "forecast") ?? null] as const;
  }, [currency, horizon]);
  useEffect(() => {
    let active = true;
    async function refresh() {
      try { const [next, nextJob] = await load(); if (active) { setData(next); setJob(nextJob); setError(""); } }
      catch (cause) { if (active) setError(cause instanceof Error ? cause.message : "Unable to load forecasts."); }
    }
    void refresh();
    const timer = setInterval(() => { void refresh(); }, 10000);
    return () => { active = false; clearInterval(timer); };
  }, [load]);

  async function train() {
    setBusy(true); setError("");
    try {
      setJob(await read("/api/jobs/collection", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_type: "forecast" }) }));
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to queue forecasting."); }
    finally { setBusy(false); }
  }

  const running = job && (!["COMPLETED", "FAILED"].includes(job.state) || job.available_at !== null);
  const root = data?.forecast;
  const estimates = root?.horizon_forecasts ?? (root ? { "1": root } : {});
  const forecast = estimates[String(horizon)];
  const ready = forecast?.status === "experimental";
  const signals = error ? Object.fromEntries(Object.entries(data?.outlook ?? {}).map(([key, value]) => [key, {
    ...value, signal: "outdated", title: "Refresh before deciding",
    reason: "The latest forecast could not be checked. Reconnect the backend before using a timing signal.",
  }])) : data?.outlook ?? {};
  return <section className="panel forecast-panel" id="forecasts" aria-label="Experimental forecast and news factors">
    <div className="job-header"><div><div className="section-kicker">LOCAL RESEARCH · EXPERIMENTAL</div>
      <h2><FlaskConical size={18} /> Buy {currency}: now or later?</h2></div>
      <button type="button" className="apply-button" disabled={busy || Boolean(running)} onClick={() => void train()}>
        {running ? "Forecast job running…" : busy ? "Queueing…" : "Train local models"}
      </button></div>
    <p className="forecast-note">Compare the won cost of buying {currency} now with waiting 1, 3, 5, or 10 trading days. Lower costs mean fewer won to exchange.</p>
    {error && <p role="alert" className="alert-feedback is-error">{error}</p>}
    {job && <p className="forecast-note">Forecast job #{job.id}: {job.state.replaceAll("_", " ").toLowerCase()} · <a href="#jobs">View background log</a>{job.error ? ` · ${job.error}` : ""}</p>}
    {data?.stale && <p className="alert-feedback">New inputs arrived after this run. Updated forecasting is pending or can be queued from this panel.</p>}
    {ready && forecast ? <>
      <ForecastOutlook currency={currency} horizon={horizon} onHorizon={setHorizon}
        estimates={estimates} selected={forecast} signals={signals} history={root?.recent_costs ?? []} />
      {data?.leaderboard && data.selected_horizon === horizon && <ForecastLeaderboard data={data.leaderboard} currency={currency} />}
      <details className="forecast-technical"><summary>Model & data details · {horizon}-day horizon</summary>
      {forecast.model === "no_change" && <p className="forecast-note">The models have not shown enough improvement over keeping the latest price. This estimate stays unchanged; it is not a signal that the market will stay flat.</p>}
      {!forecast.news.eligible && <div className="forecast-coverage"><strong>{horizon > 1 ? "This horizon uses rate history" : "News is not influencing this prediction yet"}</strong>
        <p>{horizon > 1 ? "Multi-day estimates compare a directly trained rates LSTM, ridge regression, boosted trees, and no-change. The news-enhanced LSTM is evaluated for the next quote only." : "We need more news history to test whether it improves predictions. Recent news is shown below for context."}</p>
        <details><summary>See news-history requirements</summary>
          <div className="forecast-history-grid">{[
            { label: "Training days with news", count: forecast.news.training_news_days, total: 30 },
            { label: "Distinct collection dates", count: forecast.news.first_seen_dates, total: 20 },
            { label: "Validation days with news", count: forecast.news.validation_news_days, total: 15 },
            { label: "Test days with news", count: forecast.news.test_news_days, total: 8 },
          ].map(({ label, count, total }) => <div key={label}><span>{label}</span><strong>{count} / {total}</strong>
            <progress aria-label={label} value={count} max={total} /></div>)}</div>
          <p>Articles collected today cannot be used as if we had known them in the past.</p>
        </details></div>}
      {forecast.news.sensitivity_krw !== null && <p className="forecast-note">News-model sensitivity: {won(forecast.news.sensitivity_krw)} compared with masking its news inputs. This is model sensitivity, not a causal price effect.</p>}
      {Object.keys(forecast.news.factor_sensitivities ?? {}).length > 0 && <details className="forecast-validation">
        <summary>News candidate: factor-by-factor sensitivity</summary>
        <p className="forecast-note">Difference in the candidate estimate when each factor is removed from its news inputs. Positive means a higher modeled won cost. These are diagnostic comparisons, not causal effects or verified forecasts.</p>
        <div className="forecast-table-wrap"><table><thead><tr><th>News factor</th><th>Model difference per 1 {currency}</th></tr></thead>
          <tbody>{Object.entries(forecast.news.factor_sensitivities ?? {}).map(([factor, difference]) => <tr key={factor}>
            <th>{channels[factor] ?? factor}</th><td>{difference > 0 ? "+" : ""}{won(difference)}</td></tr>)}</tbody></table></div>
      </details>}
      <details className="forecast-validation"><summary>Model comparison & validation</summary>
        <p className="forecast-note">Two expanding-window blocks select the model. A separate final 20-observation block is scored afterward. Smaller price error is better.</p>
        <p className="forecast-note">Direction match is historical accuracy on this small test sample, not the probability of the next move.</p>
        <div className="forecast-table-wrap"><table><thead><tr><th>Model</th><th>Validation MAE</th><th>Held-out MAE</th><th>Held-out direction match</th></tr></thead>
          <tbody>{Object.entries(forecast.validation).map(([name, score]) => <tr key={name}><th>{models[name]}</th>
            <td>{won(score.mae_krw)}</td><td>{won(forecast.held_out_test[name].mae_krw)}</td>
            <td>{forecast.held_out_test[name].direction_accuracy === null ? "No directional call" : `${Math.round(forecast.held_out_test[name].direction_accuracy! * 100)}%`}</td></tr>)}</tbody></table></div>
      </details>
      </details>
    </> : <p className="forecast-note">{data?.status === "insufficient_data" ? `At least ${forecast?.minimum_observations} daily observations are required.`
      : data ? "Train local models to extract news evidence, run time-ordered evaluation, and save a forecast." : "Loading forecast…"}</p>}
    {data?.scorecard && data.selected_horizon === horizon && <details className="forecast-scorecard"><summary>Prediction vs. actual · {horizon}-day horizon</summary><div>
      <div className="forecast-factors-heading"><h3>Prediction vs. actual</h3>
        <span>{data.scorecard.distinct_outcomes} scored quote dates · current model version</span></div>
      <p className="forecast-note">Predictions are saved before their target quote, then compared with the actual won cost when it arrives. The original predictions stay unchanged.</p>
      <p className="forecast-note">{forecast?.forward_selection?.active
        ? "Recorded forward errors are now part of model selection for new predictions. Each candidate still needs enough matched results and must pass the historical validation checks."
        : `Collecting results: at least ${data.scorecard.minimum_outcomes} distinct scored quote dates are needed before real-world errors can influence model selection. Training repeatedly does not add independent results.`}</p>
      {data.scorecard.recent.length > 0 ? <>
        <div className="forecast-table-wrap"><table><caption>Latest issued predictions and observed outcomes</caption>
          <thead><tr><th>Quote date</th><th>Model used</th><th>Saved prediction</th><th>Actual quote</th><th>Absolute error</th></tr></thead>
          <tbody>{data.scorecard.recent.map((result) => <tr key={result.forecast_run_id}>
            <th>{result.target_date}</th><td>{models[result.model] ?? result.model}</td>
            <td>{result.prediction === null ? "—" : won(result.prediction)}</td><td>{won(result.actual_cost)}</td>
            <td>{result.absolute_error === null ? "—" : won(result.absolute_error)}</td></tr>)}</tbody>
        </table></div>
        <details className="forecast-validation"><summary>Compare real-world model errors</summary>
          <p className="forecast-note">Smaller error is better. Each model is compared with no-change on the same quote dates, over up to {data.scorecard.window} dates. These results guide future choices and are not an untouched final test.</p>
          <div className="forecast-table-wrap"><table><thead><tr><th>Model</th><th>Scored dates</th><th>Average error</th><th>Matched no-change error</th></tr></thead>
            <tbody>{Object.entries(data.scorecard.candidates).map(([name, result]) => <tr key={name}>
              <th>{models[name] ?? name}</th><td>{result.samples}</td><td>{won(result.mae_krw)}</td><td>{won(result.baseline_mae_krw)}</td>
            </tr>)}</tbody></table></div>
        </details>
      </> : <p className="forecast-note">No eligible outcomes yet. Keep the backend running for scheduled collection, or refresh rates after a new daily quote is published.</p>}
      <p className="forecast-note">Late predictions are excluded. Until exact historical publication times are available, a prediction must be saved before the first future quote date begins in UTC to count. Each horizon is scored separately. Daily reference quotes are not bank exchange offers.</p>
    </div></details>}
    <details className="forecast-news"><summary>News context & extracted events ({data?.recent_factor_count ?? 0})</summary>
    <div className="forecast-factors-heading"><h3>Recent news factors</h3><span>{data?.recent_factor_count ?? 0} source excerpts · last 7 days</span></div>
    <p className="forecast-note">News context, not a buy/sell signal. These excerpts are extracted automatically and have not been independently verified.</p>
    <div className="forecast-factors">{data?.hints.map((hint) => <article key={hint.id}>
      <div className="forecast-factor-meta"><strong>{channels[hint.factor] ?? hint.factor}</strong>
        <span>{hint.claim_type === "forward_looking" ? "Forecast / expectation" : hint.claim_type === "reported" ? "Reported claim" : "Commentary"}</span>
        <span>{hint.currencies.join(" / ") || "Currency unclear"}</span></div>
      <blockquote>{hint.evidence}</blockquote>
      {hint.event && <dl className="forecast-event-fields">
        <div><dt>Reported actual</dt><dd>{hint.event.actual === null ? "Unknown" : `${hint.event.actual}%`}</dd></div>
        <div><dt>Previous</dt><dd>{hint.event.previous === null ? "Unknown" : `${hint.event.previous}%`}</dd></div>
        <div><dt>Expected</dt><dd>{hint.event.expected === null ? "Unknown" : `${hint.event.expected}%`}</dd></div>
        <div><dt>Surprise vs. expectation</dt><dd>{hint.event.surprise?.replaceAll("_", " ") ?? "Unknown"}</dd></div>
        {hint.event.change_basis_points !== null && <div><dt>Reported change</dt><dd>{hint.event.change_basis_points > 0 ? "+" : ""}{hint.event.change_basis_points} bp</dd></div>}
        {hint.event.attribution === "ambiguous" && <div><dt>Attribution</dt><dd>Ambiguous; numeric inputs excluded</dd></div>}
      </dl>}
      <a href={hint.source_url} target="_blank" rel="noreferrer" title={hint.source_title}>{hint.source_title === hint.evidence ? "Read source article" : hint.source_title}<ExternalLink size={12} /></a>
      <small>{hint.published_at ? `Published ${hint.published_at.slice(0, 10)}` : "Publication time unknown"}
        {hint.direction !== "unspecified" ? ` · Reported measure: ${hint.direction}` : " · Direction ambiguous or unspecified"}</small>
    </article>)}</div>
    {data && data.hints.length === 0 && <p className="forecast-note">No mapped factor excerpts are stored for this currency in the recent window.</p>}
    </details>
  </section>;
}
