"use client";

import { useState } from "react";
import styles from "./forecast-leaderboard.module.css";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

type Row = { model: string; selected: boolean; status: string; validation_rank: number | null;
  forward_rank: number | null; validation_mae: number | null; validation_samples: number;
  validation_gain_percent: number | null; held_out_mae: number | null; forward_mae: number | null;
  forward_samples: number; forward_gain_percent: number | null; forecast_cost: number | null };
export type Leaderboard = { horizon: number; selected_model: string | null; validation_leaders: string[];
  forward_leaders: string[]; forward_ready: boolean; matched_dates: number; minimum_outcomes: number;
  window: number; configuration_version: string | null; rows: Row[];
  history: { date: string; samples: number; mae: Record<string, number> }[]; note: string };

const names: Record<string, string> = { no_change: "No-change baseline", ridge: "Ridge regression",
  boosted_trees: "Boosted trees", rates_lstm: "Rates LSTM", news_lstm: "Rates + news LSTM" };
const colors: Record<string, string> = { no_change: "#7b8981", ridge: "#84954e", boosted_trees: "#dc7548", rates_lstm: "#4469a3", news_lstm: "#137a62" };
const statuses: Record<string, string> = { baseline: "Reference model", needs_training: "Needs retraining",
  news_history: "Needs more news history", not_supported: "News model: 1-day only",
  validation_gate: "Not enough improvement", collecting: "Collecting forward results",
  forward_gate: "Not enough live improvement", eligible: "Passes comparison gates",
  news_comparison_gate: "Does not clear all news-model gates" };
const won = (value: number | null) => value === null ? "—" : `₩${new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: Math.abs(value) < 1 ? 4 : 2 }).format(value)}`;
const label = (model: string | null) => model ? names[model] ?? model : "Awaiting results";

export function ForecastLeaderboard({ data, currency }: { data: Leaderboard; currency: string }) {
  const [basis, setBasis] = useState<"validation" | "forward">("validation");
  const rankKey = basis === "validation" ? "validation_rank" : "forward_rank";
  const rows = [...data.rows].sort((a, b) => (a[rankKey] ?? Infinity) - (b[rankKey] ?? Infinity));
  const plotted = data.rows.filter(row => row.forward_mae !== null);
  return <section className={styles.root} aria-label={`Model leaderboard for ${currency}, ${data.horizon} trading days`}>
    <div className="leaderboard-heading"><div><span className="section-kicker">MODEL COMPETITION</span>
      <h3>Model leaderboard <span>{currency} · {data.horizon}-day horizon</span></h3></div>
      <span className={`leaderboard-readiness ${data.forward_ready ? "is-ready" : ""}`}>
        {data.matched_dates}/{data.minimum_outcomes} results collected{data.forward_ready ? " · minimum met" : " · warming up"}</span>
    </div>
    <div className="leaderboard-summary">
      <div><span>Current forecast model</span><strong>{label(data.selected_model)}</strong><small>The model behind the estimate above</small></div>
      <div><span>Best on historical data</span><strong>{data.validation_leaders.map(label).join(" / ") || "Awaiting training"}</strong><small>Tested against past exchange rates</small></div>
      <div><span>Best on new predictions{data.matched_dates > 0 && !data.forward_ready ? " · early results" : ""}</span>
        <strong>{data.forward_leaders.map(label).join(" / ") || "Waiting for actual rates"}</strong><small>Scored after the actual rate arrives</small></div>
    </div>
    <div className="leaderboard-controls"><p>Error = average miss in won. Lower is better.</p>
      <div role="group" aria-label="Leaderboard ranking basis">
        <button type="button" aria-pressed={basis === "validation"} onClick={() => setBasis("validation")}>Historical results</button>
        <button type="button" aria-pressed={basis === "forward"} onClick={() => setBasis("forward")}>Live prediction results</button>
      </div>
    </div>
    <div className="forecast-table-wrap leaderboard-table"><table>
      <caption>Average error in KRW per 1 {currency}. All models are compared on the same dates.</caption>
      <thead><tr><th scope="col">Rank / model</th><th scope="col">Historical error</th><th scope="col">Live error</th><th scope="col">Compared with baseline</th><th scope="col">Model status</th></tr></thead>
      <tbody>{rows.map(row => { const gain = basis === "validation" ? row.validation_gain_percent : row.forward_gain_percent;
        return <tr key={row.model} className={row.selected ? "is-selected" : undefined}>
          <th scope="row"><div className="leaderboard-model"><span className="leaderboard-rank">{row[rankKey] === null ? "—" : `#${row[rankKey]}`}</span>
            <div>{label(row.model)}{row.selected && <small className="leaderboard-choice">Current forecast</small>}</div></div></th>
          <td>{won(row.validation_mae)}<small>{row.validation_samples ? `${row.validation_samples} past predictions` : "Not evaluated"}</small></td>
          <td>{won(row.forward_mae)}<small>{row.forward_samples ? `${row.forward_samples} matched results` : "Waiting for actual rates"}</small></td>
          <td><span className={gain === null ? "" : gain > 0 ? "leaderboard-better" : gain < 0 ? "leaderboard-worse" : ""}>
            {gain === null ? "—" : gain === 0 ? "Reference" : `${Math.abs(gain).toFixed(1)}% ${gain > 0 ? "less error" : "more error"}`}</span>
            {gain !== null && <div className="leaderboard-gain-bar" aria-hidden="true"><i style={{ left: gain < 0 ? `${50-Math.min(50, Math.abs(gain)/2)}%` : "50%", width: `${Math.min(50, Math.abs(gain)/2)}%`, background: gain >= 0 ? "#137a62" : "#dc7548" }} /></div>}</td>
          <td><span className="leaderboard-status">{statuses[row.status] ?? row.status}</span></td>
        </tr>; })}</tbody>
    </table></div>
    <p className="forecast-note">Live results need {data.minimum_outcomes} matched outcomes before they can guide model selection. Early rankings may change.</p>
    <details className="forecast-validation"><summary>How models are compared</summary><p className="forecast-note">The baseline assumes the rate stays unchanged. Models must reduce error by more than 2% and pass historical checks. Live comparisons use the same dates, currency, horizon, and model version, up to {data.window} dates. Rankings do not change an already saved forecast.</p></details>
    <details className="forecast-validation"><summary>Forward error over time</summary>
      {data.history.length < 2 ? <p className="forecast-note">The performance chart appears after two matched results. No missing results are filled with zeros.</p> : <>
        <p className="forecast-note">Cumulative average absolute error within the displayed comparison window. This is forward tracking used for future model selection, not an untouched final test.</p>
        <div className="leaderboard-history-chart" role="img" aria-label="Cumulative forward prediction error by model; lower is better">
          <ResponsiveContainer width="100%" height="100%"><LineChart data={data.history} margin={{ top: 12, right: 8, bottom: 4, left: 4 }}>
            <CartesianGrid vertical={false} stroke="#e4eae5" strokeDasharray="3 4" />
            <XAxis dataKey="date" tickFormatter={value => String(value).slice(5)} tick={{ fontSize: 10 }} minTickGap={24} />
            <YAxis tickFormatter={value => won(Number(value))} tick={{ fontSize: 10 }} width={74} />
            <Tooltip formatter={value => won(Number(value))} contentStyle={{ fontSize: 12, borderRadius: 6 }} />
            {plotted.map(row => <Line key={row.model} dataKey={`mae.${row.model}`} name={label(row.model)} stroke={colors[row.model] ?? "#66746c"} strokeWidth={2} dot={false} isAnimationActive={false} />)}
          </LineChart></ResponsiveContainer>
        </div>
        <div className="leaderboard-legend">{plotted.map(row => <span key={row.model}><i style={{ background: colors[row.model] }} />{label(row.model)}</span>)}</div>
      </>}
    </details>
    <details className="forecast-validation"><summary>Held-out diagnostic and model version</summary>
      <p className="forecast-note">Version: {data.configuration_version ?? "not trained"}. Older configurations remain stored and are excluded from this comparison. Held-out errors are shown as diagnostics and are not used to rank or select models.</p>
      <div className="forecast-table-wrap leaderboard-table"><table><thead><tr><th>Model</th><th>Final held-out error</th></tr></thead>
        <tbody>{data.rows.filter(row => row.held_out_mae !== null).map(row => <tr key={row.model}><th>{label(row.model)}</th><td>{won(row.held_out_mae)}</td></tr>)}</tbody>
      </table></div>
    </details>
  </section>;
}
