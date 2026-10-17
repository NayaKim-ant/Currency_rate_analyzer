import { connection } from "next/server";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  CalendarDays,
  CircleAlert,
  Newspaper,
  Radio,
  ScrollText,
  FlaskConical,
} from "lucide-react";

import { RateChart, type ChartPoint } from "@/components/charts/rate-chart";
import { AlertPanel } from "@/components/alerts/alert-panel";
import { JobPanel } from "@/components/jobs/job-panel";
import { ForecastPanel } from "@/components/forecasts/forecast-panel";

type RatePointResponse = {
  rate_date: string;
  rate: number | string;
  ma_5: number | string | null;
  ma_20: number | string | null;
  ma_60: number | string | null;
};

type RateSeriesResponse = {
  base_currency: string;
  target_currency: string;
  requested_days: number;
  points: RatePointResponse[];
  trend_state: string;
};

type ArticleResult = {
  article_id: number;
  source: string;
  title: string;
  summary: string | null;
  url: string;
  published_at: string | null;
  relevance_score: number | string;
  matched_keywords: string[];
  policy_keywords: string[];
};

type MarketEventResult = {
  id: number;
  event_type: string;
  title: string;
  description: string | null;
  occurred_at: string;
};

type DashboardProps = {
  searchParams: Promise<{ target_currency?: string; days?: string }>;
};

export const instant = false;

const currencyNames: Record<string, string> = {
  USD: "US dollar",
  AUD: "Australian dollar",
  CAD: "Canadian dollar",
  CHF: "Swiss franc",
  CNY: "Chinese yuan",
  EUR: "Euro",
  GBP: "British pound",
  JPY: "Japanese yen",
};

const homeCurrency = "KRW";

function parseDays(value: string | undefined): number {
  const parsed = Number(value ?? 90);
  return Number.isInteger(parsed) ? Math.max(1, Math.min(parsed, 3650)) : 90;
}

function numericValue(value: number | string | null): number | null {
  if (value === null) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatRate(value: number | string | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "--";
  return new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 4 }).format(Number(value));
}

async function loadRateSeries(targetCurrency: string, days: number): Promise<RateSeriesResponse | null> {
  const backendUrl = process.env.BACKEND_API_URL ?? "http://127.0.0.1:8000";
  const query = new URLSearchParams({ target_currency: targetCurrency, base_currency: homeCurrency, days: String(days), quote_direction: "base_per_target" });
  try {
    const response = await fetch(`${backendUrl}/api/v1/rates?${query}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(2500),
    });
    if (!response.ok) return null;
    return (await response.json()) as RateSeriesResponse;
  } catch {
    return null;
  }
}

async function checkApiHealth(): Promise<boolean> {
  const backendUrl = process.env.BACKEND_API_URL ?? "http://127.0.0.1:8000";
  try {
    const response = await fetch(`${backendUrl}/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(1500),
    });
    return response.ok;
  } catch {
    return false;
  }
}

async function loadApiList<T>(path: string): Promise<T[]> {
  const backendUrl = process.env.BACKEND_API_URL ?? "http://127.0.0.1:8000";
  try {
    const response = await fetch(`${backendUrl}${path}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(3500),
    });
    if (!response.ok) return [];
    return (await response.json()) as T[];
  } catch {
    return [];
  }
}

function formatEventDate(value: string | null | undefined): string {
  if (!value) return "Date unavailable";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Date unavailable";
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(parsed);
}

function formatSignal(value: string): string {
  const labels: Record<string, string> = {
    rapid_rise: "Cost in won falling",
    rapid_fall: "Cost in won rising",
    trend_reversal_up: "Won strengthening signal",
    trend_reversal_down: "Won weakening signal",
  };
  if (labels[value]) return labels[value];
  return value.replaceAll("_", " ");
}

function trendLabel(state: string | undefined): string {
  if (state === "uptrend") return "Cost rising";
  if (state === "downtrend") return "Cost falling";
  if (state === "neutral") return "Neutral";
  return "Insufficient data";
}

export default async function DashboardPage({ searchParams }: DashboardProps) {
  // Live API data and chart libraries must run after a real request arrives.
  // Cache Components can otherwise evaluate their time-dependent code in a prerender.
  await connection();
  const params = await searchParams;
  const requestedCurrency = (params.target_currency ?? "USD").toUpperCase();
  const targetCurrency = Object.hasOwn(currencyNames, requestedCurrency) ? requestedCurrency : "USD";
  const days = parseDays(params.days);
  const [series, apiOnline, articles, events] = await Promise.all([
    loadRateSeries(targetCurrency, days),
    checkApiHealth(),
    loadApiList<ArticleResult>(`/api/v1/articles?base_currency=${homeCurrency}&target_currency=${targetCurrency}&days=${days}&min_score=10&limit=4`),
    loadApiList<MarketEventResult>(`/api/v1/events?base_currency=${homeCurrency}&target_currency=${targetCurrency}&days=${days}&limit=4`),
  ]);
  const latest = series?.points.at(-1);
  const chartPoints: ChartPoint[] = (series?.points ?? []).map((point) => ({
    date: point.rate_date,
    rate: Number(point.rate),
    ma_5: numericValue(point.ma_5),
    ma_20: numericValue(point.ma_20),
    ma_60: numericValue(point.ma_60),
  }));
  const trend = series?.trend_state;
  const trendTone = trend === "downtrend" ? "uptrend" : trend === "uptrend" ? "downtrend" : trend;
  const TrendIcon = trend === "uptrend" ? ArrowUpRight : trend === "downtrend" ? ArrowDownRight : Activity;
  const lastUpdated = latest
    ? new Intl.DateTimeFormat("en", { dateStyle: "medium", timeZone: "UTC" }).format(new Date(`${latest.rate_date}T00:00:00Z`))
    : "Awaiting data";

  return (
    <main className="app-shell">
      <aside className="rail" aria-label="Primary navigation">
        <a className="brand-mark" href="/dashboard" aria-label="Basis home">B</a>
        <nav className="rail-nav">
          <a className="rail-link is-active" href="#rates" aria-label="Markets" title="Markets"><Activity size={19} /></a>
          <a className="rail-link" href="#forecasts" aria-label="Forecast" title="Forecast"><FlaskConical size={19} /></a>
          <a className="rail-link" href="#articles" aria-label="Articles" title="Articles"><Newspaper size={19} /></a>
          <a className="rail-link" href="#events" aria-label="Events" title="Events"><CalendarDays size={19} /></a>
          <a className="rail-link" href="#alerts" aria-label="Alerts" title="Alerts"><CircleAlert size={19} /></a>
          <a className="rail-link" href="#jobs" aria-label="Background logs" title="Background logs"><ScrollText size={19} /></a>
        </nav>
        <span className="rail-status" title="API connection status"><Radio size={17} /></span>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div className="wordmark"><span className="wordmark-icon">B</span><span>basis<span className="wordmark-dot">.</span></span></div>
          <nav className="top-nav" aria-label="Workspace sections">
            <a className="top-nav-link is-current" href="#rates">Markets</a>
            <a className="top-nav-link" href="#forecasts">Forecast</a>
            <a className="top-nav-link" href="#articles">Research</a>
            <a className="top-nav-link" href="#events">Timeline</a>
            <a className="top-nav-link" href="#alerts">Alerts</a>
            <a className="top-nav-link" href="#jobs">Logs</a>
          </nav>
          <div className="connection"><span className={`connection-dot ${apiOnline ? "is-live" : "is-idle"}`} />{apiOnline ? "API connected" : "API offline"}</div>
        </header>

        <div className="content-wrap">
          <section className="page-heading">
            <div>
              <div className="eyebrow">CURRENCY INTELLIGENCE <span> / </span> DAILY BRIEF</div>
              <h1>Market monitor</h1>
              <p className="heading-copy">How many won one unit of foreign currency costs. Lower chart values mean it costs fewer won to exchange.</p>
            </div>
            <form className="query-controls" action="/dashboard" method="get">
              <label className="control-field">
                <span>Price of 1</span>
                <select name="target_currency" defaultValue={targetCurrency}>
                  {Object.entries(currencyNames).map(([code, name]) => <option key={code} value={code}>{code} · {name}</option>)}
                </select>
              </label>
              <label className="control-field period-field">
                <span>Window</span>
                <select name="days" defaultValue={String(days)}>
                  <option value="30">30 days</option>
                  <option value="90">90 days</option>
                  <option value="180">180 days</option>
                  <option value="365">1 year</option>
                </select>
              </label>
              <button className="apply-button" type="submit">Update view</button>
            </form>
          </section>

          <section className="metric-grid" aria-label="Current market summary">
            <article className="metric-panel metric-primary">
              <div className="metric-label">COST OF 1 {targetCurrency} <span>IN KOREAN WON</span></div>
              <div className="metric-value">₩{formatRate(latest?.rate)}<span className="metric-unit"> / 1 {targetCurrency}</span></div>
              <div className="metric-foot">1 {targetCurrency} = ₩{formatRate(latest?.rate)} · {lastUpdated}</div>
            </article>
            <article className="metric-panel">
              <div className="metric-label">TREND STATE</div>
              <div className={`trend-value trend-${trendTone ?? "offline"}`}><TrendIcon size={21} strokeWidth={2.2} />{trendLabel(trend)}</div>
              <div className="metric-foot">Lower cost means fewer won per {targetCurrency}</div>
            </article>
            <article className="metric-panel">
              <div className="metric-label">OBSERVATIONS</div>
              <div className="metric-value">{series?.points.length ?? "--"}<span className="metric-unit"> / {days} days</span></div>
              <div className="metric-foot">Trading-day records available</div>
            </article>
            <article className="metric-panel">
              <div className="metric-label">DATA STATUS</div>
              <div className={`status-value ${series ? "status-ready" : "status-waiting"}`}><span className="status-mark" />{series ? "Rate feed ready" : apiOnline ? "Database unavailable" : "Waiting for API"}</div>
              <div className="metric-foot">PostgreSQL-backed rate feed</div>
            </article>
          </section>

          <section className="analysis-grid" id="rates">
            <article className="panel chart-panel">
              <div className="panel-heading">
                <div><div className="section-kicker">WON PER 1 {targetCurrency}</div><h2>1 {targetCurrency} in Korean won</h2></div>
                <div className="chart-period">Last {days} days <span className="period-dot" /></div>
              </div>
              <div className="chart-legend" aria-label="Chart series">
                <span><i className="legend-rate" /> Rate</span><span><i className="legend-ma5" /> MA 5</span><span><i className="legend-ma20" /> MA 20</span><span><i className="legend-ma60" /> MA 60</span>
              </div>
              {chartPoints.length > 0
                ? <RateChart points={chartPoints} currency={targetCurrency} />
                : <div className="chart-empty"><div className="empty-icon"><Activity size={21} /></div><strong>{series ? "No observations in this window" : apiOnline ? "Rate database is unavailable" : "Rate feed is not connected"}</strong><p>{series ? "Try a wider date window or another currency pair." : apiOnline ? "The API is responding, but PostgreSQL must be available to load rate history." : "Start the FastAPI service and connect PostgreSQL to load rate history."}</p></div>}
            </article>

            <article className="panel averages-panel">
              <div className="panel-heading"><div><div className="section-kicker">MOVING AVERAGES</div><h2>Trend levels</h2></div><Activity size={18} className="panel-icon" /></div>
              <div className="average-list">
                {[{ label: "5 observations", value: latest?.ma_5, tone: "ma-tone-5" }, { label: "20 observations", value: latest?.ma_20, tone: "ma-tone-20" }, { label: "60 observations", value: latest?.ma_60, tone: "ma-tone-60" }].map((item) => (
                  <div className="average-row" key={item.label}><div className="average-name"><i className={item.tone} />{item.label}</div><strong>₩{formatRate(item.value)}</strong></div>
                ))}
              </div>
              <div className="trend-note"><TrendIcon size={16} /><span>{trendLabel(trend)}<small>KRW per 1 {targetCurrency} · {latest ? `As of ${latest.rate_date}` : "60 observations needed for MA60"}</small></span></div>
            </article>
          </section>

          <ForecastPanel key={targetCurrency} currency={targetCurrency} />

          <section className="lower-grid">
            <article className="panel feed-panel" id="articles">
              <div className="panel-heading"><div><div className="section-kicker">RESEARCH FEED</div><h2>Relevant coverage</h2></div><span className="small-count">{articles.length} ARTICLES</span></div>
              {articles.length > 0 ? <div className="article-list">{articles.map((article) => (
                <a className="article-row" href={article.url} key={article.article_id} target="_blank" rel="noreferrer">
                  <div className="article-row-top"><span>{article.source} · {formatEventDate(article.published_at)}</span><strong>{Math.round(Number(article.relevance_score))}<small>%</small></strong></div>
                  <h3>{article.title}</h3>
                  <p>{article.summary || "Article body was unavailable; showing the feed summary."}</p>
                  <div className="keyword-list">{article.matched_keywords.slice(0, 4).map((keyword) => <span key={keyword}>{keyword}</span>)}</div>
                </a>
              ))}</div> : <div className="module-empty"><Newspaper size={18} /><span>{apiOnline ? "No relevant articles are stored for this period yet." : "Article feed is unavailable while the API is offline."}</span></div>}
            </article>
            <article className="panel feed-panel" id="events">
              <div className="panel-heading"><div><div className="section-kicker">EVENT TIMELINE</div><h2>Market events</h2></div><span className="small-count">{events.length} EVENTS</span></div>
              {events.length > 0 ? <div className="timeline-list">{events.map((event) => (
                <div className="timeline-row" key={event.id}><span className="timeline-mark" /><div><div className="timeline-meta">{formatEventDate(event.occurred_at)} · {formatSignal(event.event_type)}</div><strong>{event.title}</strong><p>{event.description}</p></div></div>
              ))}</div> : <div className="module-empty"><CalendarDays size={18} /><span>{apiOnline ? "No market events have been recorded for this period." : "Event timeline is unavailable while the API is offline."}</span></div>}
            </article>
            <AlertPanel key={targetCurrency} currency={targetCurrency} currentCost={latest?.rate ?? null} />
          </section>
          <JobPanel />
          <footer className="page-footer"><span>KRW exchange reference · Bank fees affect the final amount.</span><span>Signals describe observed patterns, not future rates.</span></footer>
        </div>
      </section>
    </main>
  );
}
