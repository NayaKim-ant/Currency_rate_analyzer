"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Bell, Check, Pause, Play, Trash2 } from "lucide-react";

type AlertRule = {
  id: number;
  target_currency: string;
  alert_type: string;
  threshold: string | number;
  enabled: boolean;
};

type AlertOccurrence = {
  id: number;
  message: string;
  fired_at: string;
};

async function alertRequest(path: string, options?: RequestInit) {
  const response = await fetch(`/api/alerts${path}`, {
    ...options,
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    signal: AbortSignal.timeout(18000),
  });
  if (response.status === 204) return null;
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(typeof detail === "string" ? detail : Array.isArray(detail)
      ? detail.map((item: { msg: string }) => item.msg).join(". ") : "Unable to update alerts.");
  }
  return data;
}

function won(value: string | number): string {
  return `₩${new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 }).format(Number(value))}`;
}

function ruleLabel(rule: AlertRule): string {
  const comparison = rule.alert_type === "won_cost_at_or_below" ? "≤"
    : rule.alert_type === "won_cost_at_or_above" ? "≥" : null;
  return comparison ? `1 ${rule.target_currency} ${comparison} ${won(rule.threshold)}`
    : `${rule.alert_type.replaceAll("_", " ")} · ${rule.threshold}`;
}

export function AlertPanel({ currency, currentCost }: { currency: string; currentCost: string | number | null }) {
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [occurrences, setOccurrences] = useState<AlertOccurrence[]>([]);
  const [condition, setCondition] = useState("won_cost_at_or_below");
  const [threshold, setThreshold] = useState(currentCost ? Number(currentCost).toFixed(2) : "");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const refresh = useCallback(async () => {
    const query = new URLSearchParams({ base_currency: "KRW", target_currency: currency });
    const [nextRules, nextOccurrences] = await Promise.all([
      alertRequest(`/rules?${query}`), alertRequest(`?${query}&limit=10`),
    ]);
    setRules(nextRules);
    setOccurrences(nextOccurrences);
  }, [currency]);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        await refresh();
        if (active) setError("");
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : "Unable to load alerts.");
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    const interval = setInterval(() => { void load(); }, 30000);
    return () => { active = false; clearInterval(interval); };
  }, [refresh]);

  async function mutate(path: string, options: RequestInit, success: string) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await alertRequest(path, options);
      setMessage(success);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to update alerts.");
    } finally {
      setBusy(false);
    }
  }

  async function createRule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await mutate("/rules", {
      method: "POST",
      body: JSON.stringify({ base_currency: "KRW", target_currency: currency,
        alert_type: condition, threshold, lookback_days: 1 }),
    }, "Alert saved and checked against the latest quote.");
  }

  return (
    <article className="panel feed-panel alert-panel" id="alerts">
      <div className="panel-heading">
        <div><div className="section-kicker">PRICE ALERTS</div><h2>{currency} price alerts</h2></div>
        <Bell size={18} className="panel-icon" />
      </div>
      <p className="alert-help">Notify me here when 1 {currency} costs:</p>
      <form className="alert-form" onSubmit={createRule}>
        <label className="control-field">
          <span>Condition</span>
          <select aria-label="Alert condition" value={condition} onChange={(event) => setCondition(event.target.value)} disabled={busy}>
            <option value="won_cost_at_or_below">At or below</option>
            <option value="won_cost_at_or_above">At or above</option>
          </select>
        </label>
        <label className="control-field">
          <span>Won per 1 {currency}</span>
          <input aria-label={`Won price target for 1 ${currency}`} type="number" min="0.01" max="9999999" step="0.01"
            required placeholder="1300" value={threshold} onChange={(event) => setThreshold(event.target.value)} disabled={busy} />
        </label>
        <button className="apply-button" type="submit" disabled={busy}>{busy ? "Saving…" : "Add alert"}</button>
      </form>
      {error && <p className="alert-feedback is-error" role="alert">{error}</p>}
      {message && <p className="alert-feedback" role="status"><Check size={13} />{message}</p>}
      <div className="alert-rules" aria-label="Saved alert rules" aria-busy={loading || busy}>
        {loading ? <p className="alert-help">Loading alerts…</p> : rules.length === 0
          ? <p className="alert-help">No price targets set for {currency} yet.</p>
          : rules.map((rule) => (
            <div className="alert-rule" key={rule.id}>
              <div><strong>{ruleLabel(rule)}</strong><small>{rule.enabled ? "Active" : "Paused"}</small></div>
              <div className="alert-actions">
                <button type="button" disabled={busy} title={rule.enabled ? "Pause alert" : "Resume alert"}
                  aria-label={`${rule.enabled ? "Pause" : "Resume"} ${ruleLabel(rule)}`}
                  onClick={() => void mutate(`/rules/${rule.id}`, { method: "PATCH", body: JSON.stringify({ enabled: !rule.enabled }) }, rule.enabled ? "Alert paused." : "Alert resumed and checked.")}>
                  {rule.enabled ? <Pause size={14} /> : <Play size={14} />}
                </button>
                <button type="button" disabled={busy} title="Delete alert" aria-label={`Delete ${ruleLabel(rule)}`}
                  onClick={() => void mutate(`/rules/${rule.id}`, { method: "DELETE" }, "Rule deleted. Past notifications are kept.")}><Trash2 size={14} /></button>
              </div>
            </div>
          ))}
      </div>
      <div className="alert-history-heading"><h3>Triggered alerts</h3>
        <button type="button" className="alert-text-button" disabled={busy || loading}
          onClick={() => void mutate("/evaluate", { method: "POST", body: "{}" }, "Checked the latest stored quotes.")}>Check now</button>
      </div>
      {occurrences.length > 0 ? <div className="timeline-list">{occurrences.map((occurrence) => (
        <div className="timeline-row alert-row" key={occurrence.id}><Bell size={15} /><div>
          <div className="timeline-meta">Quote: {occurrence.fired_at.slice(0, 10)}</div>
          <strong>{occurrence.message}</strong>
        </div></div>
      ))}</div> : <p className="alert-help">No matching quotes recorded yet.</p>}
      <p className="alert-footnote">Uses daily reference quotes. Checked on rate updates and when you save or resume a rule. One notification per matching quote date. This panel refreshes every 30 seconds.</p>
    </article>
  );
}
