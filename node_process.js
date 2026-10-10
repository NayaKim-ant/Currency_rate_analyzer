const fs = require("fs");
const net = require("net");
const path = require("path");
const { Worker, isMainThread, parentPort, workerData } = require("worker_threads");

// 상태 전이를 검사하는 state machine 엔진이 아니라, 현재 상태와 원인 이벤트를 관찰용 로그로 남긴다.
function transition(workerName, currentState, nextState, event, detail = "") {
  console.log(`[${workerName}] 상태 전이: ${currentState} -> ${nextState} | 원인 이벤트: ${event}${detail ? ` | ${detail}` : ""}`);
  return nextState;
}

function movingAverage(values, windowSize = 5) {
  // 휴일/주말을 제외한 관측치 배열의 마지막 N개 값에 대한 단순 평균이다.
  const recent = values.slice(-windowSize);
  return recent.reduce((sum, value) => sum + value, 0) / recent.length;
}

function cleanHtml(value) {
  return value
    .replace(/<[^>]*>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/\s+/g, " ")
    .trim();
}

function extractRelevantContent(article) {
  // RSS 설명이 제목과 매체명만 반복하는 경우 본문으로 오인하지 않는다.
  const headline = cleanHtml(article.title);
  const description = cleanHtml(article.description);
  const withoutHeadline = description
    .replace(headline, "")
    .replace(/\s+/g, " ")
    .trim();

  if (
    !withoutHeadline
    || withoutHeadline.length < 120
    || !/[.!?。！？]/.test(withoutHeadline)
  ) {
    return "관련 본문 없음 (뉴스 RSS가 제목만 제공)";
  }
  return withoutHeadline.slice(0, 500);
}

function buildInsight(input) {
  const rateDates = input.rates.map((entry) => entry.date);
  const latest = input.rates.at(-1);
  const previous = input.rates.at(-2) || latest;
  const currencies = {};

  // 환율은 USD 기준이다. 예를 들어 EUR 값은 1 USD당 EUR 수량을 뜻한다.
  for (const [currency, name] of Object.entries(input.currency_names)) {
    const values = input.rates
      .map((entry) => entry.rates[currency])
      .filter((value) => typeof value === "number");
    if (values.length === 0) continue;

    const latestValue = latest.rates[currency];
    const previousValue = previous.rates[currency] ?? latestValue;
    const average = movingAverage(values);
    const changePercent = ((latestValue - previousValue) / previousValue) * 100;
    const averageGapPercent = ((latestValue - average) / average) * 100;
    // 추이는 하루 변화율이 아니라 최근 5개 관측치 평균과 최신값의 차이로 판정한다.
    const trend = averageGapPercent > 0.15 ? "상승 추이" : averageGapPercent < -0.15 ? "하락 추이" : "이동평균 부근의 보합 추이";

    currencies[currency] = {
      name,
      latest_rate: Number(latestValue.toFixed(6)),
      latest_date: latest.date,
      five_day_moving_average: Number(average.toFixed(6)),
      change_from_previous_day_percent: Number(changePercent.toFixed(3)),
      gap_from_moving_average_percent: Number(averageGapPercent.toFixed(3)),
      trend,
    };
  }

  // 키워드 일치는 원인 후보이지, 환율 변동의 인과관계를 검증한 결과는 아니다.
  const articles = input.articles.map((article) => {
    const headline = cleanHtml(article.title);
    const relevantContent = extractRelevantContent(article);
    const text = `${headline} ${relevantContent}`;
    const reasonTerms = ["inflation", "interest", "central bank", "rate", "dollar", "euro", "yen", "yuan", "won", "currency"];
    const matchedReasons = reasonTerms.filter((term) => text.toLowerCase().includes(term));
    return {
      headline,
      relevant_content: relevantContent,
      published: article.published,
      link: article.link,
      matched_reasons: matchedReasons,
      matched_keywords: article.matched_keywords,
    };
  });

  return {
    generated_at: new Date().toISOString(),
    source_period: { start: rateDates[0], end: rateDates.at(-1) },
    methodology: "5일 단순 이동평균과 최신 환율을 비교해 일시적 등락보다 추이를 판단",
    currencies,
    relevant_articles: articles,
    reason_summary: articles.length > 0
      ? "관련 기사에서 반복된 통화·금리·인플레이션·중앙은행 키워드를 변화 이유 후보로 추출"
      : "수집 기간에 선별된 관련 기사가 없어 환율 이동평균 추이만 표시",
  };
}

if (!isMainThread) {
  // 이 파일은 메인 프로세스와 두 Worker 스레드가 함께 실행하는 단일 진입점이다.
  if (workerData.role === "ipc-handler") {
    let state = "CONNECTING";
    const socket = net.createConnection({ host: "127.0.0.1", port: workerData.port });
    let buffer = "";
    socket.setEncoding("utf8");
    socket.on("connect", () => { // 연결됐을때 콜백
      state = transition("Node IPC 핸들러", state, "CONNECTED", "IPC_CONNECT");
      parentPort.postMessage({ type: "IPC_CONNECTED" });
    });
    socket.on("data", (chunk) => {
      buffer += chunk;
      let newlineIndex;
      while ((newlineIndex = buffer.indexOf("\n")) !== -1) {
        const rawMessage = buffer.slice(0, newlineIndex);
        buffer = buffer.slice(newlineIndex + 1);
        if (rawMessage) {
          // TCP는 메시지 경계를 보장하지 않으므로 개행 단위로 JSON 프레임을 복원한다.
          state = transition("Node IPC 핸들러", state, "RECEIVING", "IPC_DATA");
          parentPort.postMessage({ type: "IPC_MESSAGE", message: JSON.parse(rawMessage) });
          state = transition("Node IPC 핸들러", state, "CONNECTED", "MESSAGE_RECEIVED");
        }
      }
    });
    socket.on("error", (error) => {
      state = transition("Node IPC 핸들러", state, "ERROR", "IPC_ERROR", error.message);
      parentPort.postMessage({ type: "IPC_ERROR", error: error.message });
    });
    parentPort.on("message", (message) => {
      if (message.type === "SEND") {
        state = transition("Node IPC 핸들러", state, "CONNECTED", "IPC_SEND");
        socket.write(`${JSON.stringify(message.message)}\n`);
      } else if (message.type === "CLOSE") {
        state = transition("Node IPC 핸들러", state, "STOPPED", "STOP");
        socket.end();
      }
    });
  } else if (workerData.role === "insight-saver") {
    let state = "IDLE";
    parentPort.on("message", (message) => {
      if (message.type === "STOP") {
        state = transition("Node 인사이트 저장", state, "STOPPED", "STOP");
        return;
      }
      if (message.type !== "BUILD_INSIGHTS") return;

      try {
        // IPC에는 대용량 본문 대신 파일 경로만 오므로 이 워커가 입력 파일을 직접 읽는다.
        state = transition("Node 인사이트 저장", state, "READING", "BUILD_INSIGHTS");
        const input = JSON.parse(fs.readFileSync(message.inputPath, "utf8"));
        state = transition("Node 인사이트 저장", state, "ANALYZING", "FILE_READ", `환율 ${input.rates.length}일, 기사 ${input.articles.length}개`);
        const insights = buildInsight(input);
        state = transition("Node 인사이트 저장", state, "SAVING", "MOVING_AVERAGE_ANALYZED");
        fs.writeFileSync(message.outputPath, JSON.stringify(insights, null, 2), "utf8");
        state = transition("Node 인사이트 저장", state, "WAITING", "INSIGHTS_SAVED");
        parentPort.postMessage({ type: "INSIGHTS_SAVED", outputPath: message.outputPath, currencies: Object.keys(insights.currencies).length });
      } catch (error) {
        state = transition("Node 인사이트 저장", state, "ERROR", "SAVE_ERROR", error.message);
        parentPort.postMessage({ type: "SAVE_ERROR", error: error.message });
      }
    });
  }
} else {
  // 메인 스레드는 IPC 이벤트를 라우팅하고 두 Worker의 수명 주기를 조정한다.
  let processState = "STARTING";
  const port = Number(process.argv[2]);
  const defaultOutputPath = path.join(__dirname, "market_insights.json");
  const ipcHandler = new Worker(__filename, { workerData: { role: "ipc-handler", port } });
  const insightSaver = new Worker(__filename, { workerData: { role: "insight-saver" } });
  processState = transition("Node 프로세스", processState, "RUNNING", "PROCESS_START");

  ipcHandler.on("message", (message) => {
    if (message.type === "IPC_CONNECTED") {
      console.log("Node IPC 핸들러: Python 연결 완료");
    } else if (message.type === "IPC_MESSAGE") { // Python에서 보낸 메시지(이벤트 종류, 워커용)
      if (message.message.type === "PROCESS_COMPLETE") { // python에서 보낸 payload 내용
        processState = transition("Node 프로세스", processState, "WAITING", "PROCESS_COMPLETE");
        insightSaver.postMessage({ type: "BUILD_INSIGHTS", inputPath: message.message.analysisInputPath, outputPath: message.message.outputPath || defaultOutputPath });
      } else if (message.message.type === "STOP") {
        processState = transition("Node 프로세스", processState, "STOPPING", "STOP");
        insightSaver.postMessage({ type: "STOP" });
        ipcHandler.postMessage({ type: "SEND", message: { type: "NODE_STOPPED" } });
        ipcHandler.postMessage({ type: "CLOSE" });
        setTimeout(() => {
          processState = transition("Node 프로세스", processState, "STOPPED", "WORKERS_TERMINATED");
          ipcHandler.terminate();
          insightSaver.terminate();
        }, 50);
      }
    } else if (message.type === "IPC_ERROR") {
      processState = transition("Node 프로세스", processState, "ERROR", "IPC_ERROR", message.error);
      console.error(`Node IPC 오류: ${message.error}`);
    }
  });

  insightSaver.on("message", (message) => {
    if (message.type === "INSIGHTS_SAVED") {
      processState = transition("Node 프로세스", processState, "WAITING", "INSIGHTS_SAVED");
      console.log(`Node 인사이트 저장: ${message.currencies}개 통화 분석 완료`);
      ipcHandler.postMessage({ type: "SEND", message }); // ipcHandler를 통해 Python으로 전달
    } else if (message.type === "SAVE_ERROR") {
      processState = transition("Node 프로세스", processState, "ERROR", "SAVE_ERROR", message.error);
      ipcHandler.postMessage({ type: "SEND", message: { type: "NODE_ERROR", error: message.error } });
    }
  });
}
