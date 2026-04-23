from __future__ import annotations
from dataclasses import dataclass
from typing import List
from .core import EngineSimulator
from . import io


@dataclass
class SweepResult:
    label: str
    outfile: str


def sweep_intake_pressure(
    base_config_path: str, pressures_Pa: List[float], out_prefix: str
) -> List[SweepResult]:
    """Simple design sweep over intake pressure.

    For each intake pressure value, we run one cycle and write out a result JSON.
    """
    cfg = io.load_json(base_config_path)
    results: List[SweepResult] = []
    for p_intake in pressures_Pa:
        cfg_mod = dict(cfg)
        cfg_mod.setdefault("operating", {})["intake_pressure_Pa"] = p_intake
        sim = EngineSimulator.from_dict(cfg_mod)
        sim_result = sim.run(cycles=1)
        outfile = f"{out_prefix}_pint_{int(p_intake/100.0):04d}.json"
        io.save_json(outfile, sim_result.to_dict())
        results.append(SweepResult(label=f"{p_intake/1000.0:.1f} kPa", outfile=outfile))
    return results


def sweep_speed_full_load(
    base_config_path: str, speeds_rpm: List[float], out_prefix: str
) -> List[SweepResult]:
    """Full-load style speed sweep (virtual dyno).

    We keep the thermodynamic setup fixed (AFR, pressure-rise factor, etc.)
    and vary engine speed. Because the core model is 0-D, "full load" here
    simply means WOT-style fixed inputs; brake power scales with speed.

    Each point writes a JSON result and returns a simple label/outfile pair.
    """
    cfg = io.load_json(base_config_path)
    results: List[SweepResult] = []
    for N in speeds_rpm:
        cfg_mod = dict(cfg)
        cfg_mod.setdefault("operating", {})["engine_speed_rpm"] = N
        sim = EngineSimulator.from_dict(cfg_mod)
        sim_result = sim.run(cycles=1)
        outfile = f"{out_prefix}_N_{int(N):05d}.json"
        io.save_json(outfile, sim_result.to_dict())
        results.append(SweepResult(label=f"{N:.0f} rpm", outfile=outfile))
    return results


def sweep_speed_motored(
    base_config_path: str, speeds_rpm: List[float], out_prefix: str
) -> List[SweepResult]:
    """Motored sweep vs speed (virtual motoring test).

    We set pressure_rise_factor=0 and combustion_efficiency=0 so the
    cycle is pure compression/expansion + pumping. That mimics dyno
    motoring tests used to derive friction / pumping maps.
    """
    cfg = io.load_json(base_config_path)
    results: List[SweepResult] = []
    for N in speeds_rpm:
        cfg_mod = dict(cfg)
        op = cfg_mod.setdefault("operating", {})
        op["engine_speed_rpm"] = N
        op["pressure_rise_factor"] = 0.0
        op["combustion_efficiency"] = 0.0
        sim = EngineSimulator.from_dict(cfg_mod)
        sim_result = sim.run(cycles=1)
        outfile = f"{out_prefix}_motored_N_{int(N):05d}.json"
        io.save_json(outfile, sim_result.to_dict())
        results.append(SweepResult(label=f"motored {N:.0f} rpm", outfile=outfile))
    return results
