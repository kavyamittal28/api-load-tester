# LoadForge — API Load Testing Tool

A browser-based API load testing tool with a Postman-like UI and live performance charts.

Paste a cURL command, set virtual users and duration, and watch real-time metrics stream in.

---

## Features

- **cURL-based input** — paste any cURL command directly, no manual URL/header entry
- **Ramp-up support** — gradually increase load like JMeter (configurable ramp-up period)
- **Live charts** — response time, throughput, and virtual users update every 500ms
- **Real-time stats** — total requests, success rate, avg/P95 response time, req/s
- **WebSocket streaming** — results stream from server to browser as they happen
- **Stop mid-test** — stop the test at any point and keep the results

---

## Tech Stack

- **Backend**: Python, FastAPI, WebSockets, httpx (async HTTP)
- **Frontend**: Vanilla JS, Chart.js
- **Concurrency**: asyncio with configurable virtual users and ramp-up

---

## Installation

```bash
git clone https://github.com/kavyamittal28/api-load-tester.git
cd api-load-tester

python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

## Usage

```bash
python3 -m uvicorn app.main:app --reload --port 800
```

Open **http://localhost:8000** in your browser.

---

## How to Use

1. Paste a cURL command into the input field
2. Set **Virtual Users** (concurrent workers), **Ramp-up** (seconds to reach full load), and **Duration**
3. Click **Run Test**
4. Watch live charts and metrics update in real time

**Example cURL:**
```bash
curl https://api.example.com/endpoint \
  -H 'Authorization: Bearer your_token' \
  -H 'Accept: application/json'
```

---

## Live Results

| Metric | Description |
|--------|-------------|
| Total Requests | Requests sent so far |
| Req / Second | Current throughput (3s rolling window) |
| Success Rate | % of 2xx responses |
| Avg Response | Mean response time in ms |
| P95 Response | 95th percentile response time |

**Charts:**
- Response Time — avg and P95 over time
- Throughput — requests per second over time
- Virtual Users — shows the ramp-up curve

---

## Project Structure

```
api-load-tester/
├── app/
│   ├── curl_parser.py   # Parses cURL commands into request config
│   ├── engine.py        # Async load test engine (ramp-up + duration)
│   └── main.py          # FastAPI server + WebSocket endpoint
├── static/
│   └── index.html       # Frontend UI (Chart.js, vanilla JS)
├── run.py               # Start the server
└── requirements.txt
```
