# Legacy Python and Node workers

[Current project map](README.md)

`project/legacy/` is a separate, earlier one-shot program. It does not power the Next.js dashboard, consume `analysis_jobs`, or share the current backend's durable state machine. Its state variables and transition logs describe progress in memory; the transition helpers do not enforce an allowed-edge registry like the current backend does.

## One-shot execution

```mermaid
flowchart TD
    main["Python process_and_thread.py"]
    ipc["Python IPC server thread"]
    crawler["Python CrawlerWorker thread"]
    analyzer["Python AnalyzerWorker thread"]
    raw[("market_data_raw.json")]
    input[("market_analysis_input.json")]
    node["Node main process"]
    nodeIpc["Node IPC worker thread"]
    saver["Node insight-saver worker thread"]
    output[("market_insights.json")]
    main -->|"start"| ipc
    main -->|"START message"| crawler
    main -->|"START message"| analyzer
    crawler --> raw
    crawler -->|"DATA through Python queue"| analyzer
    analyzer --> input
    analyzer -->|"DATA_PROCESSED acknowledgement"| crawler
    main -->|"spawn"| node
    node --> nodeIpc
    node --> saver
    ipc <-->|"newline-delimited JSON over TCP"| nodeIpc
    main -->|"PROCESS_COMPLETE with file paths"| ipc
    nodeIpc -->|"forward message via Node main"| saver
    input --> saver --> output
    saver -->|"INSIGHTS_SAVED via Node main and IPC"| main
```

The main Python script waits for queue work to finish, sends paths to Node, waits for `INSIGHTS_SAVED`, then explicitly stops Python workers and Node. Large payloads move through JSON files rather than being embedded in the TCP message. Queue `join()` waits for `task_done()` acknowledgements; it does not itself stop a worker thread.

## Python worker progress

```mermaid
stateDiagram-v2
    state "CrawlerWorker" as crawler {
        [*] --> crawlerIdle
        state "IDLE" as crawlerIdle
        state "FETCHING_RATES" as fetchingRates
        state "FETCHING_NEWS" as fetchingNews
        state "SENT" as sent
        state "WAITING" as crawlerWaiting
        state "STOPPED" as crawlerStopped
        crawlerIdle --> fetchingRates: START
        fetchingRates --> fetchingNews: rates fetched
        fetchingNews --> sent: raw data saved and DATA sent
        sent --> crawlerWaiting: DATA_PROCESSED
        crawlerWaiting --> crawlerStopped: STOP
    }
    state "AnalyzerWorker" as analyzer {
        [*] --> analyzerIdle
        state "IDLE" as analyzerIdle
        state "RECEIVING" as receiving
        state "FILTERING" as filtering
        state "SAVING" as saving
        state "WAITING" as analyzerWaiting
        state "STOPPED" as analyzerStopped
        analyzerIdle --> receiving: START
        receiving --> filtering: DATA
        filtering --> saving: relevant articles selected
        saving --> analyzerWaiting: input file saved and acknowledgement sent
        analyzerWaiting --> analyzerStopped: STOP
    }
```

These show the normal one-shot paths. Both workers also have `ERROR` states and handle `STOP` messages outside this happy path. The crawler fetches rates and news; the analyzer filters article relevance and writes Node's input. The base worker blocks on `Queue.get()`, handles the message, and acknowledges it in `finally`.

## Node worker progress

```mermaid
stateDiagram-v2
    state "IPC worker" as ipcWorker {
        [*] --> connecting
        state "CONNECTING" as connecting
        state "CONNECTED" as connected
        state "RECEIVING" as receiving
        state "ERROR" as ipcError
        state "STOPPED" as ipcStopped
        connecting --> connected: socket connect
        connected --> receiving: socket data
        receiving --> connected: messages forwarded
        connected --> connected: SEND
        connected --> ipcError: socket error
        connected --> ipcStopped: CLOSE
    }
    state "Insight saver" as insightSaver {
        [*] --> saverIdle
        state "IDLE" as saverIdle
        state "READING" as reading
        state "ANALYZING" as analyzing
        state "SAVING" as saving
        state "WAITING" as waiting
        state "ERROR" as saveError
        state "STOPPED" as saverStopped
        saverIdle --> reading: BUILD_INSIGHTS
        reading --> analyzing: file read
        analyzing --> saving: insight calculation complete
        saving --> waiting: file saved and INSIGHTS_SAVED sent
        reading --> saveError: save workflow throws
        analyzing --> saveError: save workflow throws
        saving --> saveError: save workflow throws
        waiting --> saverStopped: STOP
    }
```

Node's main process routes IPC messages to the saver and routes save acknowledgements back to Python. The saver computes a five-day moving-average comparison and article-based summaries, writes the output, then waits. Its `STOP` handler can run whenever a stop message is received; it is not restricted to `WAITING`. IPC errors can likewise occur during socket use beyond the simplified connected-state edge shown here.

Unlike current PostgreSQL jobs, these progress states have no persisted attempts, automatic retry schedule, claim tokens, or crash recovery. Refer to [job-states.md](job-states.md) for those current guarantees.

Sources: [Python orchestration](../../project/legacy/process_and_thread.py), [Python worker states and handlers](../../project/legacy/thread_worker.py), [messages](../../project/legacy/thread_messages.py), [Python IPC](../../project/legacy/ipc_handler.py), [Node workers](../../project/legacy/node_process.js). Earlier detailed prototype documentation remains in [architecture.md](../architecture.md) and [data-flow.md](../data-flow.md).
