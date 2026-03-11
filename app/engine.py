import asyncio
import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import httpx


@dataclass
class Result:
    timestamp: float        # seconds since test start
    response_time_ms: float
    status_code: Optional[int]
    success: bool
    error: Optional[str] = None


class LoadTestEngine:
    def __init__(self, config: Dict[str, Any]):
        self.url: str = config["url"]
        self.method: str = config["method"]
        self.headers: Dict[str, str] = config.get("headers", {})
        self.body: Any = config.get("body")
        self.verify_ssl: bool = config.get("verify_ssl", True)

        self.users: int = max(1, int(config["users"]))
        self.ramp_up: float = max(0.0, float(config["ramp_up"]))
        self.duration: float = max(1.0, float(config["duration"]))
        self.timeout: float = float(config.get("timeout", 30))

        self.results: List[Result] = []
        self.start_time: float = 0.0
        self._stop_event = asyncio.Event()

    def stop(self):
        self._stop_event.set()

    # ------------------------------------------------------------------ #
    #  Single worker: keeps sending requests until duration / stop        #
    # ------------------------------------------------------------------ #
    async def _worker(self):
        limits = httpx.Limits(max_connections=1, max_keepalive_connections=1)
        timeout_cfg = httpx.Timeout(self.timeout)

        async with httpx.AsyncClient(
            timeout=timeout_cfg,
            limits=limits,
            verify=self.verify_ssl,
            follow_redirects=True,
        ) as client:
            while not self._stop_event.is_set():
                elapsed = time.time() - self.start_time
                if elapsed >= self.duration:
                    break

                req_start = time.time()
                try:
                    if isinstance(self.body, dict) or isinstance(self.body, list):
                        resp = await client.request(
                            self.method, self.url, headers=self.headers, json=self.body
                        )
                    elif self.body:
                        resp = await client.request(
                            self.method, self.url, headers=self.headers,
                            content=self.body.encode("utf-8"),
                        )
                    else:
                        resp = await client.request(
                            self.method, self.url, headers=self.headers
                        )

                    req_end = time.time()
                    result = Result(
                        timestamp=req_start - self.start_time,
                        response_time_ms=(req_end - req_start) * 1000,
                        status_code=resp.status_code,
                        success=200 <= resp.status_code < 400,
                    )

                except httpx.TimeoutException:
                    req_end = time.time()
                    result = Result(
                        timestamp=req_start - self.start_time,
                        response_time_ms=(req_end - req_start) * 1000,
                        status_code=None,
                        success=False,
                        error="Timeout",
                    )
                except Exception as exc:
                    req_end = time.time()
                    result = Result(
                        timestamp=req_start - self.start_time,
                        response_time_ms=(req_end - req_start) * 1000,
                        status_code=None,
                        success=False,
                        error=type(exc).__name__,
                    )

                self.results.append(result)

    # ------------------------------------------------------------------ #
    #  Stats helpers                                                       #
    # ------------------------------------------------------------------ #
    def _snapshot_stats(self, snapshot: List[Result]) -> Dict[str, Any]:
        if not snapshot:
            return {
                "total": 0, "successful": 0, "failed": 0,
                "success_rate": 0, "avg_rt": 0, "p95_rt": 0,
                "p99_rt": 0, "min_rt": 0, "max_rt": 0,
            }

        rts = [r.response_time_ms for r in snapshot]
        successful = sum(1 for r in snapshot if r.success)
        sorted_rts = sorted(rts)
        n = len(sorted_rts)

        return {
            "total": len(snapshot),
            "successful": successful,
            "failed": len(snapshot) - successful,
            "success_rate": round(successful / len(snapshot) * 100, 1),
            "avg_rt": round(statistics.mean(rts), 1),
            "p95_rt": round(sorted_rts[min(int(n * 0.95), n - 1)], 1),
            "p99_rt": round(sorted_rts[min(int(n * 0.99), n - 1)], 1),
            "min_rt": round(sorted_rts[0], 1),
            "max_rt": round(sorted_rts[-1], 1),
        }

    def _rps_in_window(self, snapshot: List[Result], elapsed: float, window: float = 3.0) -> float:
        cutoff = elapsed - window
        recent = sum(1 for r in snapshot if r.timestamp >= cutoff)
        return round(recent / min(window, max(elapsed, 0.01)), 1)

    # ------------------------------------------------------------------ #
    #  Main run loop                                                       #
    # ------------------------------------------------------------------ #
    async def run(self, on_update: Callable[[Dict], Any]):
        self.start_time = time.time()
        worker_tasks: List[asyncio.Task] = []

        ramp_interval = (self.ramp_up / self.users) if self.ramp_up > 0 else 0

        # -- Gradually spawn workers
        async def ramp_workers():
            for _ in range(self.users):
                if self._stop_event.is_set():
                    break
                if time.time() - self.start_time >= self.duration:
                    break
                worker_tasks.append(asyncio.create_task(self._worker()))
                if ramp_interval > 0:
                    await asyncio.sleep(ramp_interval)

        # -- Send live stats every 500 ms
        async def stream_stats():
            last_count = 0
            last_ts = time.time()

            while not self._stop_event.is_set():
                await asyncio.sleep(0.5)
                elapsed = time.time() - self.start_time
                snapshot = list(self.results)

                # RPS over last 3-second window
                rps = self._rps_in_window(snapshot, elapsed)

                stats = self._snapshot_stats(snapshot)
                active = sum(1 for t in worker_tasks if not t.done())

                # Recent data points for scatter (last 1 s)
                timeline = [
                    {"t": round(r.timestamp, 2), "rt": round(r.response_time_ms, 1), "ok": r.success}
                    for r in snapshot if r.timestamp > elapsed - 1.0
                ]

                await on_update({
                    "type": "update",
                    "elapsed": round(elapsed, 1),
                    "progress": round(min(elapsed / self.duration * 100, 100), 1),
                    "active_users": active,
                    "rps": rps,
                    "timeline": timeline,
                    **stats,
                })

        # -- Kill workers after duration
        async def enforce_duration():
            await asyncio.sleep(self.duration)
            self._stop_event.set()

        await asyncio.gather(
            ramp_workers(),
            stream_stats(),
            enforce_duration(),
            return_exceptions=True,
        )

        # Clean up workers
        for t in worker_tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*worker_tasks, return_exceptions=True)

        # Final stats
        final = list(self.results)
        stats = self._snapshot_stats(final)
        elapsed = time.time() - self.start_time

        await on_update({
            "type": "complete",
            "elapsed": round(elapsed, 1),
            "progress": 100,
            "active_users": 0,
            "rps": self._rps_in_window(final, elapsed),
            **stats,
        })
