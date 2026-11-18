# Port-DSS

Generate a terminal schedule and compare it with first-come, first-served dispatch. The live dashboard shows vessel berthing, crane occupation, truck gates, job times, and saved runs.

## Run the stack

```sh
docker compose up -d --build --wait
```

Open `http://127.0.0.1:8080`. Choose normal operations, a vessel arrival surge, or a crane outage. Change the seed to generate a different workload in that scenario. Select the CP-SAT or FCFS plan to compare timelines. Use `docker compose down` to stop the stack and retain history.

FastAPI stores each run in a PostgreSQL 16 TimescaleDB hypertable. A Redis 7 Pub/Sub notification follows the SQL commit. The API relays notifications over WebSockets, and the React 18, TypeScript and Tailwind dashboard reloads the saved history. History remains available during a notification outage, and the browser reloads history after reconnecting. The included SQLite mode polls history for local notification testing.

## Optimization

CP-SAT chooses one compatible berth and crane for each vessel and one gate for each truck. It blocks overlapping assignments on every resource, respects vessel length and crane coverage, excludes crane downtime, and releases an associated truck only after vessel service ends. A separate feasibility checker verifies both CP-SAT and FCFS schedules. Each vessel holds one crane throughout service. The objective weights elapsed time from arrival to completion by 3 for each vessel and 1 for each truck.

The FCFS baseline visits vessels in arrival order and assigns the compatible pair that finishes earliest. Trucks enter its gate queue in cargo-ready order. Each scenario runs both policies on the same seeded instance. Lower objective cost is better.

| Scenario | Mean FCFS cost | Mean CP-SAT cost | Reduction |
| --- | ---: | ---: | ---: |
| Normal | 1,470.12 | 1,330.50 | 9.5% |
| Arrival surge | 3,144.88 | 2,478.38 | 21.2% |
| Crane outage | 1,992.88 | 1,741.00 | 12.6% |

There were eight seeds per scenario. CP-SAT proved optimality on 19 of 24 instances and returned feasible incumbents on the other five within the two-second solver cap. The report records solver status and bounds so the latter runs stay distinguishable. These are synthetic, small terminal workloads. The model omits crane crossing distance, yard capacity, weather and shift changes. [Per-instance results](results.json)

## Verify and develop

```sh
python -m pip install -r requirements.txt
python -m pytest -q
python benchmark.py
pnpm --dir web install --frozen-lockfile
pnpm --dir web run build
python -m uvicorn api:app --host 127.0.0.1 --port 8080
```

Run `python smoke.py` against the Compose stack to verify HTML delivery, schedule creation, post-commit Redis-to-WebSocket notification and persisted history. The API reference is at `/docs`. The defaults are for local development.

## Reference

[Yashwanth Hudumula's Port-DSS](https://github.com/YashwanthHudumula/port-dss) is the public project used as a feature and architecture reference. This implementation has its own scheduling model, experiments and application code.
