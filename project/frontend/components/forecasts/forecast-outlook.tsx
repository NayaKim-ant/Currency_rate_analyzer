"use client";

import { useState } from "react";
import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export type OutlookEstimate = {
  status: string; current_cost: number; forecast_cost: number; model: string; change_percent: number;
  error_band: { lower: number; upper: number }; as_of_date: string;
};
export type TimingSignal = { signal: string; title: string; reason: string; estimated_date: string; date_is_estimate: boolean };
type Props = { currency: string; horizon: number; onHorizon: (horizon: number) => void;
  estimates: Record<string, OutlookEstimate>; selected: OutlookEstimate; signals: Record<string, TimingSignal>;
  history: { date: string; cost: number }[] };
const horizons = [1, 3, 5, 10];
const format = (value: number) => new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value);
const won = (value: number) => `₩${format(value)}`;
function day(value: string) {
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

export function ForecastOutlook({ currency, horizon, onHorizon, estimates, selected, signals, history }: Props) {
  const [amountInput, setAmount] = useState("1000");
  const [markupInput, setMarkup] = useState("0");
  const amount = Number(amountInput);
  const markup = Number(markupInput);
  const valid = amountInput !== "" && markupInput !== "" && Number.isFinite(amount) && amount > 0 && amount <= 1e9 && Number.isFinite(markup) && markup >= 0 && markup <= 100;
  const multiplier = 1 + markup / 100;
  const current = selected.current_cost;
  const signal = signals[String(horizon)];
  const isBaseline = selected.model === "no_change";
  const move = selected.forecast_cost - current;
  const timestamp = (date: string) => Date.parse(`${date}T00:00:00Z`);
  const observations: { x: number; actual?: number; estimate?: number; band?: [number, number] }[] = history.map(p => ({ x: timestamp(p.date), actual: p.cost }));
  const last = observations.at(-1);
  if (last) { last.estimate = current; last.band = [current, current]; }
  for (const h of horizons) {
    const estimate = estimates[String(h)];
    if (estimate?.status === "experimental") observations.push({
      x: signals[String(h)] ? timestamp(signals[String(h)].estimated_date) : timestamp(selected.as_of_date) + h*86400000,
      estimate: estimate.forecast_cost, band: [estimate.error_band.lower, estimate.error_band.upper],
    });
  }
  return <div className="forecast-outlook">
    <div className={`outlook-verdict is-${signal?.signal ?? "no_edge"}`} aria-live="polite">
      <span className="section-kicker">BUY {currency} WITH KOREAN WON</span>
      <h3>{signal?.title ?? "No clear timing signal yet"}</h3>
      <p>{signal?.reason ?? "Refresh the multi-day models to compare buying now with waiting."}</p>
    </div>
    <div className="outlook-period-row"><span>Compare buying now with waiting</span>
      <div className="outlook-periods" role="group" aria-label="Forecast horizon">
        {horizons.map(h => <button key={h} type="button" aria-pressed={horizon === h}
          disabled={!estimates[String(h)] || estimates[String(h)].status !== "experimental"} onClick={() => onHorizon(h)}>
          {h} {h === 1 ? "day" : "days"}</button>)}
      </div>
    </div>
    <p className="outlook-date">Trading days after the source quote on {selected.as_of_date}.
      {signal && <> Selected horizon: approximately <strong>{day(signal.estimated_date)}</strong>.</>} Weekends are skipped; holidays can shift dates.</p>
    <div className="outlook-price-cards">
      <div><span>Latest reference · 1 {currency}</span><strong>{won(current)}</strong><small>Buying-price starting point</small></div>
      <div className="is-estimate"><span>In {horizon} trading {horizon === 1 ? "day" : "days"} · 1 {currency}</span>
        <strong>{won(selected.forecast_cost)}</strong><small>{isBaseline ? "Baseline: no supported directional move" : `${won(Math.abs(move))} ${move < 0 ? "cheaper" : "more expensive"} than now (${selected.change_percent > 0 ? "+" : ""}${selected.change_percent.toFixed(2)}%)`}</small></div>
      <div><span>Historical error range</span><strong>{won(selected.error_band.lower)} – {won(selected.error_band.upper)}</strong><small>Not a guaranteed range or a calibrated probability</small></div>
    </div>
    <div className="outlook-chart-heading"><h3>What buying could cost</h3><span>KRW per 1 {currency} · lower is cheaper</span></div>
    <div className="outlook-chart" role="img" aria-label={`Observed won costs and 1, 3, 5 and 10 trading-day forecasts for ${currency}, with historical error ranges. Estimates are also listed in the table below.`}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={observations} margin={{ top: 12, right: 8, bottom: 4, left: 4 }}>
          <CartesianGrid vertical={false} stroke="#e4eae5" strokeDasharray="3 4" />
          <XAxis dataKey="x" type="number" domain={["dataMin", "dataMax"]} scale="time"
            tickFormatter={v => day(new Date(Number(v)).toISOString().slice(0, 10))}
            tick={{ fontSize: 10, fill: "#66746c" }} minTickGap={22} axisLine={false} tickLine={false} />
          <YAxis domain={["auto", "auto"]} orientation="right" width={78} tickFormatter={v => won(Number(v))} tick={{ fontSize: 10, fill: "#66746c" }} axisLine={false} tickLine={false} />
          <Tooltip labelFormatter={v => day(new Date(Number(v)).toISOString().slice(0, 10))}
            formatter={(value, name) => [Array.isArray(value) ? `${won(Number(value[0]))} – ${won(Number(value[1]))}` : won(Number(value)), name]}
            contentStyle={{ border: "1px solid #dbe3dd", borderRadius: 8, fontSize: 12 }} />
          <ReferenceLine y={current} stroke="#8b9890" strokeDasharray="3 5" />
          {signal && <ReferenceLine x={timestamp(signal.estimated_date)} stroke="#4469a3" strokeDasharray="2 4" />}
          <Area dataKey="band" name="Historical error range" fill="#4469a3" fillOpacity={.12} stroke="none" connectNulls={false} isAnimationActive={false} />
          <Line dataKey="actual" name="Observed quote" stroke="#137a62" strokeWidth={2.5} dot={false} isAnimationActive={false} />
          <Line dataKey="estimate" name="Forecast estimate" stroke="#4469a3" strokeWidth={2.5} strokeDasharray="5 4" dot={{ r: 4 }} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
    <div className="outlook-legend"><span><i />Observed</span><span><i />Forecast</span><span><i />Historical error range</span></div>
    <p className="forecast-note">The dashed line connects separate horizon estimates; it does not predict every intervening day. Range widths come from each horizon’s past errors. A flat baseline does not mean prices cannot move.</p>
    <div className="outlook-calculator">
      <div><h3>Your exchange amount</h3><p>Estimate the total won needed to buy {currency}.</p></div>
      <label>Amount to buy ({currency})<input type="number" min="0.01" max="1000000000" step="any" value={amountInput} onChange={e => setAmount(e.target.value)} /></label>
      <label>Estimated bank markup (%)<input type="number" min="0" max="100" step="0.1" value={markupInput} onChange={e => setMarkup(e.target.value)} /></label>
    </div>
    {valid ? <div className="outlook-total" aria-live="polite">
      <div><span>Buy now · estimated total</span><strong>{won(current * amount * multiplier)}</strong></div>
      <div><span>Wait {horizon} trading {horizon === 1 ? "day" : "days"} · estimated total</span><strong>{won(selected.forecast_cost * amount * multiplier)}</strong></div>
      <p>{isBaseline ? "The baseline gives no expected timing savings." : `Waiting is modeled to cost ${won(Math.abs(move) * amount * multiplier)} ${move < 0 ? "less" : "more"}.`}
        {signal?.signal === "no_edge" || signal?.signal === "outdated" ? " This is not a supported timing advantage." : " This is a model estimate, not a locked bank offer."}</p>
    </div> : <p className="forecast-note" role="alert">Enter a positive amount up to 1 billion and a markup between 0% and 100%.</p>}
    <p className="forecast-note">The same markup is assumed now and later. At 0%, fees are excluded. Fixed fees, bank spreads that change, and your bank’s actual offer can change the comparison. The timing signal does not account for when you need the money.</p>
    <details className="forecast-validation"><summary>Compare all forecast horizons</summary>
      <div className="forecast-table-wrap"><table><thead><tr><th>After source quote</th><th>Approx. date</th><th>Won per 1 {currency}</th><th>Change</th></tr></thead>
        <tbody>{horizons.map(h => { const e = estimates[String(h)]; return e?.status === "experimental" ? <tr key={h}>
          <th>{h} trading {h === 1 ? "day" : "days"}</th><td>{signals[String(h)]?.estimated_date ?? "—"}</td><td>{won(e.forecast_cost)}</td>
          <td>{e.model === "no_change" ? "No direction signal" : `${e.change_percent > 0 ? "+" : ""}${e.change_percent.toFixed(2)}%`}</td></tr> : null; })}</tbody></table></div>
    </details>
  </div>;
}
