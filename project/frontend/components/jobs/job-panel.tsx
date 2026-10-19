"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Activity, RefreshCw } from "lucide-react";

type Job = {
  id: number;
  job_type: string;
  state: string;
  attempts: number;
  max_attempts: number;
  error: string | null;
  result: Record<string, number>;
  available_at: string | null;
  updated_at: string;
};
type Transition = { id: number; to_state: string; attempt: number; message: string | null; created_at: string };
type Detail = Job & { history: Transition[] };

const names: Record<string, string> = {
  rates: "Refresh exchange rates",
  news_recent: "Refresh recent news",
  news_history: "Backfill news history",
  analysis: "Reanalyze stored data",
  forecast: "Train local forecasts",
};
const states: Record<string, string> = {
  QUEUED: "Queued", COLLECTING: "Collecting", ANALYZING: "Analyzing",
  EVALUATING_ALERTS: "Checking alerts", COMPLETED: "Completed", FAILED: "Failed",
  EXTRACTING_HINTS: "Extracting news", FORECASTING: "Training & validating",
};
const resultLabels: Record<string, string> = {
  rates: "Rates processed", articles: "Articles processed", snapshots: "Trend points",
  events_created: "New market events", alerts_created: "New alerts",
  news_facts: "New source excerpts", forecasts: "Currency forecasts",
  forecasts_scored: "Forecast outcomes recorded",
};
const filters = { all: "All runs", running: "In progress", failed: "Failed", completed: "Completed" };
type Filter = keyof typeof filters;

function matchesFilter(job: Job, filter: Filter): boolean {
  if (filter === "all") return true;
  if (filter === "running") return !["FAILED", "COMPLETED"].includes(job.state);
  return job.state === filter.toUpperCase();
}

function logMessage(entry: Transition): string {
  const messages: Record<string, string> = {
    "Requested by startup": "Automatically queued when the server started.",
    "Requested by schedule": "Queued by the daily update schedule.",
    "Requested by manual": "Requested from the dashboard.",
    "Requested by cli": "Requested from the command line.",
    "Automatic retry": "Retrying after an earlier attempt failed.",
    "Retry requested by user": "You requested another attempt.",
  };
  if (entry.message) return messages[entry.message] ?? entry.message;
  const descriptions: Record<string, string> = {
    COLLECTING: "Fetching and saving source data.", ANALYZING: "Calculating trends and market events.",
    EVALUATING_ALERTS: "Checking your alert rules against the stored quotes.",
    COMPLETED: "Task finished successfully. The dashboard data is up to date.",
  };
  return descriptions[entry.to_state] ?? "";
}

async function request(path: string, body?: object) {
  const response = await fetch(`/api/jobs${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
    signal: AbortSignal.timeout(12000),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to update jobs.");
  return data;
}

function dateLabel(value: string): string {
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false, timeZone: "Asia/Seoul" }).format(new Date(value));
}

export function JobPanel() {
  const router = useRouter();
  const knownStates = useRef<Map<number, string> | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [kind, setKind] = useState("rates");
  const [filter, setFilter] = useState<Filter>("all");
  const [detailId, setDetailId] = useState<number | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const [nextJobs, nextDetail]: [Job[], Detail | null] = await Promise.all([
      request("?limit=20"), detailId === null ? Promise.resolve(null) : request(`/${detailId}`),
    ]);
    setJobs(nextJobs);
    setDetail(nextDetail);
    const newlyCompleted = knownStates.current !== null && nextJobs.some(
      (job) => job.state === "COMPLETED" && knownStates.current?.get(job.id) !== "COMPLETED",
    );
    knownStates.current = new Map(nextJobs.map((job) => [job.id, job.state]));
    if (newlyCompleted) router.refresh();
  }, [detailId, router]);

  useEffect(() => {
    let active = true;
    async function load() {
      try { await refresh(); if (active) setError(""); }
      catch (cause) { if (active) setError(cause instanceof Error ? cause.message : "Cannot load jobs."); }
      finally { if (active) setLoading(false); }
    }
    void load();
    const timer = setInterval(() => { void load(); }, 5000);
    return () => { active = false; clearInterval(timer); };
  }, [refresh]);

  async function submit(path: string, body: object) {
    setBusy(true); setError(""); setNotice("");
    try {
      const job: Job = await request(path, body);
      setFilter("all");
      if (knownStates.current === null) knownStates.current = new Map();
      knownStates.current.set(job.id, job.state);
      setNotice(`Job #${job.id} ${job.state === "QUEUED" ? "queued" : "already pending or running"}.`);
      await refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to queue job."); }
    finally { setBusy(false); }
  }

  return (
    <section className="panel job-panel" id="jobs" aria-label="Background logs">
      <div className="job-header">
        <div><div className="section-kicker">ACTIVITY & RUN HISTORY</div><h2>Background logs</h2></div>
        <form className="job-controls" onSubmit={(event) => { event.preventDefault(); void submit("/collection", { job_type: kind }); }}>
          <label className="control-field"><span>Task</span><select aria-label="Background task" value={kind} onChange={(event) => setKind(event.target.value)} disabled={busy}>
            {Object.entries(names).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
          </select></label>
          <button className="apply-button" type="submit" disabled={busy}><RefreshCw size={13} />{busy ? "Queueing…" : "Run task"}</button>
        </form>
      </div>
      <p className="job-help">Follow data collection, trend analysis, and alert checks. Times are shown in Korea time (KST).</p>
      {error && <p className="alert-feedback is-error" role="alert">{error}</p>}
      {notice && <p className="alert-feedback" role="status">{notice}</p>}
      <div className="job-log-toolbar">
        <div className="job-filters" role="group" aria-label="Filter background logs">{(Object.keys(filters) as Filter[]).map((value) => (
          <button type="button" key={value} aria-pressed={filter === value} onClick={() => setFilter(value)}>
            {filters[value]} <span>{jobs.filter((job) => matchesFilter(job, value)).length}</span>
          </button>
        ))}</div>
        <span className="job-log-caption">Latest 20 runs · Refreshes every 5s</span>
      </div>
      <div className="job-list" aria-busy={loading}>
        {loading ? <p className="job-help">Loading job history…</p> : jobs.length === 0
          ? <p className="job-help">No background tasks recorded yet. Run a task to update your data.</p>
          : jobs.filter((job) => matchesFilter(job, filter)).length === 0
          ? <p className="job-help">No {filters[filter].toLowerCase()} tasks in the latest 20 runs.</p>
          : jobs.filter((job) => matchesFilter(job, filter)).map((job) => {
            const steps = job.job_type === "forecast" ? ["QUEUED", "EXTRACTING_HINTS", "FORECASTING", "COMPLETED"]
              : job.job_type === "analysis" ? ["QUEUED", "ANALYZING", "EVALUATING_ALERTS", "COMPLETED"]
              : ["QUEUED", "COLLECTING", "ANALYZING", "EVALUATING_ALERTS", "COMPLETED"];
            const current = steps.indexOf(job.state);
            return <div className="job-row" key={job.id} data-job-id={job.id}>
              <div className="job-row-heading"><div className="job-title"><span className="job-run-id">RUN #{job.id}</span><h3>{names[job.job_type] ?? job.job_type}</h3></div>
                <span className={`job-state job-state-${job.state.toLowerCase()}`}><Activity size={11} />{states[job.state] ?? job.state}</span>
              </div>
              {(job.state !== "COMPLETED" || detailId === job.id) && <ol className="job-steps" aria-label={`Job ${job.id} stages`}>{steps.map((state, index) => (
                <li key={state} className={index <= current ? "is-reached" : ""} aria-current={state === job.state ? "step" : undefined}>{states[state]}</li>
              ))}</ol>}
              <div className="job-row-footer"><span><time dateTime={job.updated_at}>{dateLabel(job.updated_at)} KST</time> · Attempt {job.attempts} of {job.max_attempts}</span>
                <div className="job-buttons">
                  {job.state === "FAILED" && <button type="button" className="alert-text-button" disabled={busy} onClick={() => void submit(`/${job.id}/retry`, {})}>Retry now</button>}
                  <button type="button" className="alert-text-button" onClick={() => setDetailId(detailId === job.id ? null : job.id)} aria-expanded={detailId === job.id} aria-controls={`job-history-${job.id}`}>{detailId === job.id ? "Hide log" : "View log"}</button>
                </div>
              </div>
              {job.error && <p className="job-error">{job.error}</p>}
              {job.state === "FAILED" && job.available_at && <p className="job-help">Automatic retry after {dateLabel(job.available_at)} KST.</p>}
              {job.state === "COMPLETED" && <dl className="job-results">{Object.entries(job.result).map(([key, value]) => (
                <div key={key}><dt>{resultLabels[key] ?? key.replaceAll("_", " ")}</dt><dd>{value.toLocaleString()}</dd></div>
              ))}</dl>}
              {detailId === job.id && (detail?.id === job.id
                ? <ol id={`job-history-${job.id}`} className="job-history" aria-label={`Job ${job.id} transition history`}>{detail.history.map((entry) => <li key={entry.id}>
                  <time dateTime={entry.created_at}>{dateLabel(entry.created_at)} KST</time>
                  <div><div className="job-history-heading"><strong>{states[entry.to_state]}</strong><span>Attempt {entry.attempt}</span></div>
                    <p>{logMessage(entry)}</p></div>
                </li>)}</ol> : <p className="job-help">Loading transitions…</p>)}
            </div>;
          })}
      </div>
    </section>
  );
}
