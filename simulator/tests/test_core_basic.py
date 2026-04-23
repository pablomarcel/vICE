
from __future__ import annotations
from pathlib import Path
from simulator.core import EngineSimulator
from simulator import io


def test_engine_simulator_runs_single_cycle() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg_path = root / "in" / "sample_si_engine.json"
    cfg = io.load_json(cfg_path)
    sim = EngineSimulator.from_dict(cfg)
    result = sim.run(cycles=1)
    assert len(result.crank_deg) == len(result.pressure_Pa) == len(result.volume_m3)
    assert min(result.crank_deg) < max(result.crank_deg)
    assert max(result.pressure_Pa) > result.pressure_Pa[0]
    assert 0.0 <= min(result.mass_fraction_burned) <= max(result.mass_fraction_burned) <= 1.0
