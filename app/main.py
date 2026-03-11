import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .curl_parser import parse_curl
from .engine import LoadTestEngine

BASE_DIR = Path(__file__).parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="LoadForge")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.post("/parse-curl")
async def api_parse_curl(payload: dict):
    """Preview endpoint: parse a cURL command and return components."""
    try:
        result = parse_curl(payload.get("curl", ""))
        return {
            "url": result["url"],
            "method": result["method"],
            "headers": result["headers"],
            "has_body": result["raw_body"] is not None,
        }
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    engine: LoadTestEngine | None = None

    try:
        # First message from client is the test configuration
        raw = await websocket.receive_text()
        config_raw = json.loads(raw)

        curl_result = parse_curl(config_raw["curl"])

        config = {
            "url": curl_result["url"],
            "method": curl_result["method"],
            "headers": curl_result["headers"],
            "body": curl_result.get("body"),
            "verify_ssl": curl_result.get("verify_ssl", True),
            "users": int(config_raw.get("users", 10)),
            "ramp_up": float(config_raw.get("ramp_up", 5)),
            "duration": float(config_raw.get("duration", 30)),
        }

        engine = LoadTestEngine(config)

        async def on_update(data: dict):
            try:
                await websocket.send_json(data)
            except Exception:
                engine.stop()

        # Listen for stop signal in parallel with the test run
        async def listen_for_stop():
            try:
                while True:
                    msg = await websocket.receive_text()
                    if json.loads(msg).get("type") == "stop":
                        if engine:
                            engine.stop()
                        return
            except Exception:
                if engine:
                    engine.stop()

        stop_listener = asyncio.create_task(listen_for_stop())

        try:
            await engine.run(on_update)
        finally:
            stop_listener.cancel()
            try:
                await stop_listener
            except asyncio.CancelledError:
                pass

    except WebSocketDisconnect:
        if engine:
            engine.stop()

    except json.JSONDecodeError:
        try:
            await websocket.send_json({"type": "error", "message": "Invalid JSON in config."})
        except Exception:
            pass

    except ValueError as exc:
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass

    except Exception as exc:
        try:
            await websocket.send_json({"type": "error", "message": f"Unexpected error: {exc}"})
        except Exception:
            pass
