"use client";

import { useCallback, useEffect, useState } from "react";
import { FlaskConical, ExternalLink } from "lucide-react";

type Score = { mae_krw: number; direction_accuracy: number | null; samples: number };
type Forecast = {
  status: string; observations: number; minimum_observations?: number; as_of_date: string;
  model: string; current_cost: number; forecast_cost: number; change_percent: number;
  error_band: { lower: number; upper: number }; validation: Record<string, Score>; held_out_test: Record<string, Score>;
  news: { eligible: boolean; training_news_days: number; first_seen_dates: number; validation_news_days: number;
    test_news_days: number; requirements: string; sensitivity_krw: number | null; factor_sensitivities?: Record<string, number> };
};
type Hint = { id: number; factor: string; currencies: string[]; direction: string; claim_type: string;
  evidence: string; source_title: string; source_url: string; published_at: string | null };
type Data = { status: string; created_at: string | null; stale: boolean; forecast: Forecast | null;
  hints: Hint[]; recent_factor_count: number };
type Job = { id: number; job_type: string; state: string; available_at: string | null; error: string | null };

const models: Record<string, string> = { no_change: "No-change baseline", rates_lstm: "Rates-only LSTM", news_lstm: "Rates + news LSTM" };
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
  const [data, setData] = useState<Data | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    const [next, jobs]: [Data, Job[]] = await Promise.all([
      read(`/api/forecasts?target_currency=${currency}`), read("/api/jobs?limit=50"),
    ]);
    setData(next);
    setJob(jobs.find((value) => value.job_type === "forecast") ?? null);
  }, [currency]);
  useEffect(() => {
    let active = true;
    async function refresh() {
      try { await load(); if (active) setError(""); }
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
  const forecast = data?.forecast;
  const ready = forecast?.status === "experimental";
  return <section className="panel forecast-panel" id="forecasts" aria-label="Experimental forecast and news factors">
    <div className="job-header"><div><div className="section-kicker">LOCAL RESEARCH · EXPERIMENTAL</div>
      <h2><FlaskConical size={18} /> Exchange-rate prediction</h2></div>
      <button type="button" className="apply-button" disabled={busy || Boolean(running)} onClick={() => void train()}>
        {running ? "Forecast job running…" : busy ? "Queueing…" : "Train local models"}
      </button></div>
    <p className="forecast-note">Estimated cost of buying 1 {currency} at the next available daily quote after the latest stored quote. Usually the next trading day; weekends and holidays can be skipped. Lower means you would need fewer won.</p>
    {error && <p role="alert" className="alert-feedback is-error">{error}</p>}
    {job && <p className="forecast-note">Forecast job #{job.id}: {job.state.replaceAll("_", " ").toLowerCase()} · <a href="#jobs">View background log</a>{job.error ? ` · ${job.error}` : ""}</p>}
    {data?.stale && <p className="alert-feedback">New inputs arrived after this run. Updated forecasting is pending or can be queued from this panel.</p>}
    {ready && forecast ? <>
      <div className="forecast-summary">
        <div><span>Next trading-day estimate · 1 {currency}</span><strong>{won(forecast.forecast_cost)}</strong>
          <small>Latest quote: {won(forecast.current_cost)} · {forecast.as_of_date}</small>
          <span className="forecast-change">{forecast.model === "no_change" ? "No reliable direction signal" : `${forecast.change_percent > 0 ? "+" : ""}${forecast.change_percent.toFixed(2)}% vs. latest quote`}</span></div>
        <div><span>Typical historical error range</span><strong>{won(forecast.error_band.lower)} – {won(forecast.error_band.upper)}</strong>
          <small>Based on past model errors. The next quote can fall outside this range.</small></div>
        <div><span>What this estimate uses</span><strong>{forecast.model === "news_lstm" ? "Rates + news" : forecast.model === "rates_lstm" ? "Rate history" : "Latest quote"}</strong>
          <small>{forecast.observations} daily observations · quote {forecast.as_of_date}</small></div>
      </div>
      {forecast.model === "no_change" && <p className="forecast-note">The models have not shown enough improvement over keeping the latest price. This estimate stays unchanged; it is not a signal that the market will stay flat.</p>}
      {!forecast.news.eligible && <div className="forecast-coverage"><strong>News is not influencing this prediction yet</strong>
        <p>We need more news history to test whether it improves predictions. Recent news is shown below for context.</p>
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
    </> : <p className="forecast-note">{data?.status === "insufficient_data" ? `At least ${forecast?.minimum_observations} daily observations are required.`
      : data ? "Train local models to extract news evidence, run time-ordered evaluation, and save a forecast." : "Loading forecast…"}</p>}
    <div className="forecast-factors-heading"><h3>Recent news factors</h3><span>{data?.recent_factor_count ?? 0} source excerpts · last 7 days</span></div>
    <p className="forecast-note">News context, not a buy/sell signal. These excerpts are extracted automatically and have not been independently verified.</p>
    <div className="forecast-factors">{data?.hints.map((hint) => <article key={hint.id}>
      <div className="forecast-factor-meta"><strong>{channels[hint.factor] ?? hint.factor}</strong>
        <span>{hint.claim_type === "forward_looking" ? "Forecast / expectation" : hint.claim_type === "reported" ? "Reported claim" : "Commentary"}</span>
        <span>{hint.currencies.join(" / ") || "Currency unclear"}</span></div>
      <blockquote>{hint.evidence}</blockquote>
      <a href={hint.source_url} target="_blank" rel="noreferrer" title={hint.source_title}>{hint.source_title === hint.evidence ? "Read source article" : hint.source_title}<ExternalLink size={12} /></a>
      <small>{hint.published_at ? `Published ${hint.published_at.slice(0, 10)}` : "Publication time unknown"}
        {hint.direction !== "unspecified" ? ` · Reported measure: ${hint.direction}` : " · Direction ambiguous or unspecified"}</small>
    </article>)}</div>
    {data && data.hints.length === 0 && <p className="forecast-note">No mapped factor excerpts are stored for this currency in the recent window.</p>}
  </section>;
}
