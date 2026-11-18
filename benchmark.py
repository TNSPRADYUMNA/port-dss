import json
from pathlib import Path
from statistics import mean

from planner import experiment

if __name__ == "__main__":
    rows = []
    for scenario in ("normal", "surge", "outage"):
        for seed in range(8):
            report = experiment(seed, scenario)
            optimum = report["optimized"]
            assert optimum["objective"] is not None
            rows.append({"scenario":scenario,"seed":seed,"solver":optimum["status"],
                         "optimized":optimum["objective"],"baseline":report["baseline"]["objective"],
                         "bound":optimum["best_bound"]})
        runs = [row for row in rows if row["scenario"] == scenario]
        print(scenario, round(mean(row["baseline"] for row in runs), 2),
              round(mean(row["optimized"] for row in runs), 2))
    Path("results.json").write_text(json.dumps(rows, indent=2)+"\n", encoding="utf-8")
