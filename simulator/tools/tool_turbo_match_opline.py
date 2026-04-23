"""
tool_turbo_match_opline.py

Very simple steady-state turbo-match helper.
See docstring in source for details.
"""
from __future__ import annotations

import argparse
import copy
import csv
from pathlib import Path
from typing import List

import numpy as np

from ..core import EngineSimulator
from .. import io

R_AIR = 287.0
P_REF = 1.0e5
T_REF = 298.0


def _boost_schedule_rpm(N_rpm: float) -> float:
    pts = [
        (1500.0, 1.40),
        (2000.0, 1.80),
        (2500.0, 2.10),
        (3000.0, 2.35),
        (3500.0, 2.55),
        (4000.0, 2.70),
        (4500.0, 2.70),
        (5000.0, 2.60),
        (5500.0, 2.45),
        (6000.0, 2.30),
    ]

    if N_rpm <= pts[0][0]:
        return pts[0][1]
    if N_rpm >= pts[-1][0]:
        return pts[-1][1]

    for (N0, PR0), (N1, PR1) in zip(pts[:-1], pts[1:]):
        if N0 <= N_rpm <= N1:
            t = (N_rpm - N0) / (N1 - N0)
            return PR0 + t * (PR1 - PR0)
    return pts[-1][1]


def _estimate_mass_flows(
    sim: EngineSimulator,
    speed_rpm: float,
    pr_comp: float,
    p_amb_bar: float,
    T_int_K: float,
    vol_eff: float,
    afr: float,
):
    geom = sim.geometry
    op = sim.operating

    Vd_cyl = geom.displacement_volume()
    n_cyl = max(int(op.num_cylinders), 1)
    Vd_total = Vd_cyl * n_cyl

    p1_Pa = p_amb_bar * 1.0e5
    p2_Pa = pr_comp * p1_Pa

    stroke = (op.stroke_type or "four-stroke").lower()
    if "two" in stroke or "2-" in stroke:
        k_rev = 60.0
    else:
        k_rev = 120.0

    rho_int = p2_Pa / (R_AIR * T_int_K)
    m_dot_air = rho_int * vol_eff * Vd_total * (speed_rpm / k_rev)

    m_corr_comp = m_dot_air * np.sqrt(T_int_K / T_REF) / (p1_Pa / P_REF)

    m_dot_fuel = m_dot_air / afr
    m_dot_exh = m_dot_air + m_dot_fuel

    T3_K = 1050.0
    pr_turb = 1.0 + 0.8 * (pr_comp - 1.0)
    p4_Pa = p1_Pa
    p3_Pa = pr_turb * p4_Pa

    m_corr_turb = m_dot_exh * np.sqrt(T3_K / T_REF) / (p3_Pa / P_REF)
    KG_S_TO_LB_MIN = 2.20462 * 60.0
    m_corr_turb_lb_min = m_corr_turb * KG_S_TO_LB_MIN

    return (
        m_dot_air,
        m_corr_comp,
        pr_turb,
        m_dot_exh,
        m_corr_turb_lb_min,
    )


def run_match(
    config_path: Path,
    out_csv: Path,
    p_amb_bar: float,
    N_list: List[float],
) -> None:
    base_cfg = io.load_json(config_path)

    sim0 = EngineSimulator.from_dict(base_cfg)
    op0 = sim0.operating

    T_int_K = float(getattr(op0, "intake_temperature_K", 300.0))
    afr = float(getattr(op0, "air_fuel_ratio", 14.7))

    rows = []

    for N in N_list:
        cfg = copy.deepcopy(base_cfg)
        op_cfg = cfg.setdefault("operating", {})
        op_cfg["engine_speed_rpm"] = float(N)

        pr_comp = _boost_schedule_rpm(N)
        op_cfg["intake_pressure_Pa"] = float(p_amb_bar * 1.0e5 * pr_comp)

        sim = EngineSimulator.from_dict(cfg)
        result = sim.run(cycles=1)
        res_dict = result.to_dict()

        vol_eff = float(res_dict.get("volumetric_efficiency", 0.9))

        (
            m_dot_air,
            m_corr_comp,
            pr_turb,
            m_dot_exh,
            m_corr_turb_lb_min,
        ) = _estimate_mass_flows(
            sim=sim,
            speed_rpm=N,
            pr_comp=pr_comp,
            p_amb_bar=p_amb_bar,
            T_int_K=T_int_K,
            vol_eff=vol_eff,
            afr=afr,
        )

        row = {
            "speed_rpm": float(N),
            "p_amb_bar": float(p_amb_bar),
            "pr_comp": float(pr_comp),
            "pint_bar": float(pr_comp * p_amb_bar),
            "m_dot_air_kg_per_s": float(m_dot_air),
            "m_dot_corr_kg_per_s": float(m_corr_comp),
            "pr_turb": float(pr_turb),
            "m_dot_exh_kg_per_s": float(m_dot_exh),
            "m_corr_lb_per_min": float(m_corr_turb_lb_min),
            "bmep_bar": float(res_dict.get("bmep_bar", 0.0)),
            "brake_torque_Nm": float(res_dict.get("brake_torque_Nm_total", res_dict.get("brake_torque_Nm", 0.0))),
            "brake_power_kW": float(res_dict.get("brake_power_kW_total", res_dict.get("brake_power_kW", 0.0))),
            "bsfc_g_per_kWh": float(res_dict.get("bsfc_g_per_kWh", 0.0)),
            "brake_thermal_efficiency": float(res_dict.get("brake_thermal_efficiency", 0.0)),
        }
        rows.append(row)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate a simple turbo-match operating line CSV.",
    )
    p.add_argument(
        "--config",
        type=str,
        required=True,
        help="Engine configuration JSON (simulator/in/*.json)",
    )
    p.add_argument(
        "--out",
        type=str,
        default="simulator/out/turbo_match_opline.csv",
        help="Output CSV path (default: simulator/out/turbo_match_opline.csv)",
    )
    p.add_argument(
        "--p-amb-bar",
        type=float,
        default=1.013,
        help="Ambient pressure [bar abs] (default: 1.013)",
    )
    p.add_argument(
        "--N-min",
        type=float,
        default=1500.0,
        help="Minimum engine speed [rpm] (default: 1500)",
    )
    p.add_argument(
        "--N-max",
        type=float,
        default=6000.0,
        help="Maximum engine speed [rpm] (default: 6000)",
    )
    p.add_argument(
        "--N-step",
        type=float,
        default=500.0,
        help="Speed step [rpm] (default: 500)",
    )
    return p.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = Path(args.config)
    out_csv = Path(args.out)
    if not config_path.exists():
        raise SystemExit(f"Config file not found: {config_path}")

    N_vals = np.arange(args.N_min, args.N_max + 0.1, args.N_step, dtype=float)
    run_match(config_path, out_csv, args.p_amb_bar, list(N_vals))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
