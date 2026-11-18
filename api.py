"""Port schedules over REST, SQL history, and Redis-backed WebSocket updates."""
import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

import redis
import redis.asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

from planner import experiment

engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///port.db"), pool_pre_ping=True)
REDIS = os.getenv("REDIS_URL")
CHANNEL = "port-dss:schedules"


@asynccontextmanager
async def lifespan(app):
    with engine.begin() as db:
        db.execute(text("CREATE TABLE IF NOT EXISTS schedules (at TIMESTAMPTZ NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(at,id))"))
        if os.getenv("TIMESCALE") == "1":
            db.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
            db.execute(text("SELECT create_hypertable('schedules','at',if_not_exists=>TRUE)"))
    yield


app = FastAPI(title="Port-DSS", lifespan=lifespan)


class Workload(BaseModel):
    seed: int = Field(default=17, ge=0, le=100000)
    scenario: Literal["normal", "surge", "outage"] = "normal"


@app.get("/api/health")
def health():
    with engine.connect() as db:
        db.execute(text("SELECT 1"))
    if REDIS:
        with redis.Redis.from_url(REDIS, socket_timeout=2) as client:
            client.ping()
    return {"status": "ok"}


@app.get("/api/history")
def history():
    with engine.connect() as db:
        rows = db.execute(text("SELECT payload FROM schedules ORDER BY at DESC,id LIMIT 20")).scalars()
        return [json.loads(row) for row in rows]


@app.post("/api/schedule", status_code=201)
def schedule(work: Workload):
    result = experiment(work.seed, work.scenario)
    now = datetime.now(timezone.utc)
    payload = {"id": uuid4().hex, "created_at":now.isoformat(), **result}
    with engine.begin() as db:
        db.execute(text("INSERT INTO schedules VALUES (:at,:id,:payload)"),
                   {"at":now,"id":payload["id"],"payload":json.dumps(payload)})
    if REDIS:
        try:
            with redis.Redis.from_url(REDIS, socket_timeout=2) as client:
                client.publish(CHANNEL, payload["id"])
        except redis.RedisError:
            # The committed schedule remains available from history.
            return {**payload, "notification": "unavailable"}
    return payload


@app.websocket("/api/events")
async def events(ws: WebSocket):
    await ws.accept()
    try:
        if REDIS:
            async with redis.asyncio.Redis.from_url(REDIS) as client, client.pubsub() as subscription:
                await subscription.subscribe(CHANNEL)
                confirmation = await subscription.get_message(timeout=2)
                if not confirmation or confirmation["type"] != "subscribe":
                    await ws.close(code=1011)
                    return
                await ws.send_json({"event":"ready"})
                while True:
                    notice = await subscription.get_message(ignore_subscribe_messages=True, timeout=1)
                    if notice:
                        await ws.send_json({"event":"schedule","id":notice["data"].decode()})
                    else:
                        try:
                            await asyncio.wait_for(ws.receive_text(), timeout=.1)
                        except asyncio.TimeoutError:
                            continue
        else:
            from starlette.concurrency import run_in_threadpool
            previous = None
            while True:
                recent = await run_in_threadpool(history)
                if recent and recent[0]["id"] != previous:
                    previous = recent[0]["id"]
                    await ws.send_json({"event":"schedule","id":previous})
                try:
                    await asyncio.wait_for(ws.receive_text(), timeout=1)
                except asyncio.TimeoutError:
                    continue
    except WebSocketDisconnect:
        return
    except redis.RedisError:
        await ws.close(code=1011)


dist = Path(__file__).with_name("web") / "dist"
if dist.is_dir():
    app.mount("/", StaticFiles(directory=dist, html=True))
