"""Joint vessel and truck scheduling in integer minutes."""
import random
from itertools import combinations

from ortools.sat.python import cp_model

BERTHS = {"B1": 220, "B2": 320}
CRANES = {"Q1": (("B1", "B2"), 3), "Q2": (("B2",), 2)}
GATES = {"G1": 8, "G2": 10}
HORIZON = 1680


def workload(seed, scenario):
    rng = random.Random(seed)
    congested = scenario == "surge"
    vessels = [{"id": f"V{i+1:02}", "arrival": rng.randrange(130 if congested else 240),
                "length": rng.choice((180, 210, 260)), "moves": rng.randrange(75, 220)}
               for i in range(8 if congested else 6)]
    trucks = [{"id": f"T{i+1:02}", "vessel": vessel["id"],
               "arrival": vessel["arrival"] + rng.randrange(30, 150)}
              for i, vessel in enumerate(vessels)]
    outages = {"Q1": [(90, 180)]} if scenario == "outage" else {}
    return vessels, trucks, outages


def crane_minutes(vessel, crane):
    rate = CRANES[crane][1]
    return (vessel["moves"] + rate - 1) // rate


def eligible(vessel):
    return [(berth, crane) for berth, max_length in BERTHS.items() for crane, (coverage, _) in CRANES.items()
            if vessel["length"] <= max_length and berth in coverage]


def objective(rows):
    return sum((3 if row["kind"] == "vessel" else 1) * (row["end"] - row["arrival"]) for row in rows)


def solve(vessels, trucks, outages):
    model = cp_model.CpModel()
    resources = {key: [] for key in (*BERTHS, *CRANES, *GATES)}
    for crane, windows in outages.items():
        for lo, hi in windows:
            resources[crane].append(model.new_fixed_size_interval_var(lo, hi-lo, f"outage_{crane}_{lo}"))
    jobs = []
    endings = {}
    for vessel in vessels:
        key, arrival = vessel["id"], vessel["arrival"]
        start = model.new_int_var(arrival, HORIZON, key + "_start")
        end = model.new_int_var(arrival, HORIZON, key + "_end")
        choices = []
        for berth, crane in eligible(vessel):
            flag = model.new_bool_var(f"{key}_{berth}_{crane}")
            interval = model.new_optional_interval_var(start, crane_minutes(vessel, crane), end, flag, key + berth + crane)
            resources[berth].append(interval)
            resources[crane].append(interval)
            choices.append((flag, berth, crane))
        model.add_exactly_one([flag for flag, _, _ in choices])
        endings[key] = end
        jobs.append((vessel, "vessel", start, end, choices))
    for truck in trucks:
        key, arrival = truck["id"], truck["arrival"]
        start = model.new_int_var(arrival, HORIZON, key + "_start")
        end = model.new_int_var(arrival, HORIZON, key + "_end")
        model.add(start >= endings[truck["vessel"]])
        choices = []
        for gate, duration in GATES.items():
            flag = model.new_bool_var(key + gate)
            resources[gate].append(model.new_optional_interval_var(start, duration, end, flag, key + gate))
            choices.append((flag, gate, None))
        model.add_exactly_one([flag for flag, _, _ in choices])
        jobs.append((truck, "truck", start, end, choices))
    for intervals in resources.values():
        model.add_no_overlap(intervals)
    model.minimize(sum((3 if kind == "vessel" else 1) * (end - job["arrival"])
                       for job, kind, _, end, _ in jobs))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 2
    solver.parameters.num_search_workers = 1
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": solver.status_name(status), "rows": [], "objective": None}
    rows = []
    for job, kind, start, end, choices in jobs:
        resource, crane = next((resource, crane) for flag, resource, crane in choices if solver.value(flag))
        rows.append({"id": job["id"], "kind": kind, "resource": resource, "crane": crane,
                     "arrival": job["arrival"], "start": solver.value(start), "end": solver.value(end)})
    assert_feasible(vessels, trucks, outages, rows)
    return {"status": solver.status_name(status), "rows": rows, "objective": objective(rows),
            "best_bound": solver.best_objective_bound}


def baseline(vessels, trucks, outages):
    free = dict.fromkeys((*BERTHS, *CRANES, *GATES), 0)
    finish, rows = {}, []
    for vessel in sorted(vessels, key=lambda row: (row["arrival"], row["id"])):
        options = []
        for berth, crane in eligible(vessel):
            start = max(vessel["arrival"], free[berth], free[crane])
            duration = crane_minutes(vessel, crane)
            for lo, hi in sorted(outages.get(crane, ())):
                if start < hi and start + duration > lo:
                    start = hi
            options.append((start+duration, start, berth, crane))
        end, start, berth, crane = min(options)
        free[berth] = free[crane] = finish[vessel["id"]] = end
        rows.append({"id":vessel["id"],"kind":"vessel","resource":berth,"crane":crane,
                     "arrival":vessel["arrival"],"start":start,"end":end})
    for truck in sorted(trucks, key=lambda row: (max(row["arrival"],finish[row["vessel"]]), row["id"])):
        ready = max(truck["arrival"], finish[truck["vessel"]])
        end, start, gate = min((max(ready, free[g])+d, max(ready, free[g]), g) for g,d in GATES.items())
        free[gate] = end
        rows.append({"id":truck["id"],"kind":"truck","resource":gate,"crane":None,
                     "arrival":truck["arrival"],"start":start,"end":end})
    assert_feasible(vessels, trucks, outages, rows)
    return {"status":"FCFS","rows":rows,"objective":objective(rows)}


def assert_feasible(vessels, trucks, outages, rows):
    jobs = {row["id"]: row for row in rows}
    assert len(rows) == len(jobs) == len(vessels) + len(trucks)
    assert all(0 <= row["start"] < row["end"] <= HORIZON for row in rows)
    for vessel in vessels:
        row = jobs[vessel["id"]]
        assert row["arrival"] == vessel["arrival"] and row["kind"] == "vessel"
        assert (row["resource"],row["crane"]) in eligible(vessel)
        assert row["start"] >= vessel["arrival"] and row["end"]-row["start"] == crane_minutes(vessel, row["crane"])
        assert all(row["end"] <= lo or row["start"] >= hi for lo,hi in outages.get(row["crane"],[]))
    for truck in trucks:
        row = jobs[truck["id"]]
        assert row["arrival"] == truck["arrival"] and row["kind"] == "truck"
        assert row["start"] >= max(truck["arrival"], jobs[truck["vessel"]]["end"])
        assert row["end"]-row["start"] == GATES[row["resource"]]
    for first, second in combinations(rows, 2):
        if first["resource"] == second["resource"] or (first["crane"] and first["crane"] == second["crane"]):
            assert first["end"] <= second["start"] or second["end"] <= first["start"]


def experiment(seed, scenario):
    instance = workload(seed, scenario)
    return {"seed":seed,"scenario":scenario,"optimized":solve(*instance),"baseline":baseline(*instance)}
