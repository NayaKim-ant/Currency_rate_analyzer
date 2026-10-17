# Frontend

Next.js App Router 기반 dashboard 영역이다. 화면은 FastAPI를 통해서만 backend 데이터에 접근한다.

The dashboard shows the won cost of one unit of the selected foreign currency, defaulting to USD: `1 USD = ... KRW`. The main rate, chart, tooltips, and moving averages all use KRW per foreign unit. Lower values mean fewer won are needed to buy that currency. Trend labels describe cost rising or falling; lower-cost trends are green. These are reference rates; bank fees affect the final exchanged amount.

Under **Price alerts**, choose **At or below** or **At or above**, enter the won cost of one selected foreign unit, and select **Add alert**. Rules can be paused, resumed, or deleted. **Check now** evaluates the latest stored quotes. Triggered notifications stay in history after their rule is deleted. The panel refreshes every 30 seconds and uses daily reference quotes; the backend must run to collect new quotes and evaluate rules.

## 구조

The **Background logs** panel starts background jobs and displays the persisted pipeline stages, attempts, errors, automatic retry times, and transition history. **Retry now** requeues failed work. Status refreshes every five seconds; completed jobs refresh the dashboard's rates/news data. These controls call FastAPI through the same-origin `/api/jobs` proxy. See [job state machine](../../docs/job-state-machine.md).

```text
frontend/
  app/                  Next.js route와 page/layout
    dashboard/          시장 분석 dashboard
  components/
    charts/             환율 및 이동평균 시각화
    layout/             공통 화면 구성 요소
  lib/api/              FastAPI client와 응답 타입
  public/               정적 리소스
  tests/                frontend 테스트
```

Next.js App Router 앱이 생성돼 있다. dashboard는 FastAPI의 환율, 기사 관련도, 이벤트, alert API를 읽는다. backend 코드는 frontend 안에 두지 않는다.

## 로컬 실행

```powershell
npm install
npm run dev
```

기본 주소는 `http://localhost:3000`이다. Next.js 서버 환경 변수 `BACKEND_API_URL`로 FastAPI 주소를 바꿀 수 있으며, 기본값은 `http://127.0.0.1:8000`이다.

Background logs sit below the alerts row. Use the Logs link in the header or the log icon in the sidebar/bottom navigation to jump there. Filter the latest 20 runs by All runs, In progress, Failed, or Completed. View log expands a timestamped step-by-step history; completed runs show readable result counts. Desktop and phone layouts were checked in a real browser.

## Forecast

Use Forecast in the navigation to see the next daily won-price estimate, model comparison, news coverage, and linked source excerpts. Train local models queues a backend job. A no-change fallback is shown when candidates lack validation support. See [forecasting guide](../../docs/news-forecasting.md).
