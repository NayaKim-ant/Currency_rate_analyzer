export default function DashboardLoading() {
  return <main className="content-wrap" aria-busy="true" aria-label="Loading market dashboard">
    <p className="section-kicker">BASIS · MARKET MONITOR</p>
    <h1>Loading market dashboard…</h1>
    <p className="heading-copy" role="status">Fetching the latest stored rates and research.</p>
  </main>;
}
