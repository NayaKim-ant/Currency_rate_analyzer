const fs = require("fs");
const net = require("net");
const path = require("path");
const { Worker, isMainThread, parentPort, workerData } = require("worker_threads");

function transition(workerName, currentState, nextState, event, detail = "") {
  console.log(`[${workerName}] 상태 전이: ${currentState} -> ${nextState} | 원인 이벤트: ${event}${detail ? ` | ${detail}` : ""}`);
  return nextState;
}

function movingAverage(values, windowSize = 5) {
  const recent = values.slice(-windowSize);
  return recent.reduce((sum, value) => sum + value, 0) / recent.length;
}

function buildInsight(input) {
  const rateDates = input.rates.map((entry) => entry.date);
  const latest = input.rates.at(-1);
  const previous = input.rates.at(-2) || latest;
  const currencies = {};

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

  const articles = input.articles.map((article) => {
    const text = `${article.title} ${article.description}`;
    const reasonTerms = ["inflation", "interest", "central bank", "rate", "dollar", "euro", "yen", "yuan", "won", "currency"];
    const matchedReasons = reasonTerms.filter((term) => text.toLowerCase().includes(term));
    return {
      headline: article.title,
      relevant_content: article.description.replace(/<[^>]*>/g, "").slice(0, 500),
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
  if (workerData.role === "ipc-handler") {
    let state = "CONNECTING";
    const socket = net.createConnection({ host: "127.0.0.1", port: workerData.port });
    let buffer = "";
    socket.setEncoding("utf8");
    socket.on("connect", () => {
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
  let processState = "STARTING";
  const port = Number(process.argv[2]);
  const defaultOutputPath = path.join(__dirname, "market_insights.json");
  const ipcHandler = new Worker(__filename, { workerData: { role: "ipc-handler", port } });
  const insightSaver = new Worker(__filename, { workerData: { role: "insight-saver" } });
  processState = transition("Node 프로세스", processState, "RUNNING", "PROCESS_START");

  ipcHandler.on("message", (message) => {
    if (message.type === "IPC_CONNECTED") {
      console.log("Node IPC 핸들러: Python 연결 완료");
    } else if (message.type === "IPC_MESSAGE") {
      if (message.message.type === "PROCESS_COMPLETE") {
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
      ipcHandler.postMessage({ type: "SEND", message });
    } else if (message.type === "SAVE_ERROR") {
      processState = transition("Node 프로세스", processState, "ERROR", "SAVE_ERROR", message.error);
      ipcHandler.postMessage({ type: "SEND", message: { type: "NODE_ERROR", error: message.error } });
    }
  });
}
