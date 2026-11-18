"""Check Compose, TimescaleDB-backed history, Redis and WebSocket delivery."""
import asyncio
import json

import httpx
from websockets.asyncio.client import connect


async def main():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8080", timeout=15, trust_env=False) as http:
        home = await http.get("/")
        assert home.status_code == 200 and "Port-DSS" in home.text
        async with connect("ws://127.0.0.1:8080/api/events", open_timeout=5) as socket:
            assert json.loads(await asyncio.wait_for(socket.recv(), 5))["event"] == "ready"
            response = await http.post("/api/schedule", json={"scenario":"outage","seed":17})
            assert response.status_code == 201
            result = response.json()
            notice = json.loads(await asyncio.wait_for(socket.recv(), 5))
            assert notice == {"event":"schedule","id":result["id"]}
        records = (await http.get("/api/history")).json()
        assert records[0] == result and len(result["optimized"]["rows"]) == 12
        assert result["optimized"]["objective"] <= result["baseline"]["objective"]
    print("Dashboard, TimescaleDB history, and Redis WebSocket event verified.")


if __name__ == "__main__":
    asyncio.run(main())
