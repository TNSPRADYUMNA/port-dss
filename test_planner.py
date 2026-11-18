import pytest
from planner import experiment


@pytest.mark.parametrize("scenario", ["normal","surge","outage"])
def test_feasible_and_improves_fixture(scenario):
    result = experiment(17, scenario)
    assert result["optimized"]["objective"] <= result["baseline"]["objective"]
    assert result["optimized"]["best_bound"] <= result["optimized"]["objective"]
