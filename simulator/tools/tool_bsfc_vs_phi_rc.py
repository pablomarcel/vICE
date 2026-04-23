from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List
import csv
import json

import plotly.graph_objects as go

from ..core import EngineSimulator
from ..fuels import get_fuel

ROOT = Path(__file__).resolve().parents[1]
IN_DIR = ROOT / "in"
OUT_DIR = ROOT / "out"


def _load_base_config(name: str = "sample_si_engine.json") -> Dict[str, Any]:
    path = IN_DIR / name
    with path.open("r", encoding="utf-8") as f:
        cfg = json.load(f)
    print(f"[BSFC phi] Loaded base config: {path}")
    return cfg


def main() -> None:
    # Pulkrabek-style BSFC vs equivalence ratio for two compression ratios.
    base_cfg = _load_base_config()

    op0 = base_cfg.get("operating", {})
    fuel_id = op0.get("fuel_id", "gasoline")
    fuel = get_fuel(fuel_id)
    afr_st = fuel.afr_stoich

    rc_values = [8.0, 8.5, 9.0, 9.5, 10.0, 10.5, 11.0, 11.5, 12.0, 12.5, 13.0, 13.5, 14.0, 14.5, 15.0]
    phi_values = [0.8, 0.825, 0.85, 0.875, 0.9, 0.925, 0.95, 0.975, 1.0, 1.025, 1.05, 1.075, 1.1, 1.125, 1.15, 1.175, 1.2]
    speed_rpm = float(op0.get("engine_speed_rpm", 4500.0))

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows: List[List[float]] = []
    series: Dict[float, List[Dict[str, float]]] = {rc: [] for rc in rc_values}

    for rc in rc_values:
        for phi in phi_values:
            cfg = json.loads(json.dumps(base_cfg))
            geom = cfg.setdefault("geometry", {})
            op = cfg.setdefault("operating", {})

            geom["compression_ratio"] = rc
            op["engine_speed_rpm"] = speed_rpm

            afr_act = afr_st / phi
            op["air_fuel_ratio"] = float(afr_act)
            op.setdefault("friction_mode", "passenger")

            sim = EngineSimulator.from_dict(cfg)
            result = sim.run(cycles=1).to_dict()

            bsfc = result.get("bsfc_g_per_kWh")
            if bsfc is None:
                continue

            series[rc].append(
                {
                    "phi": float(phi),
                    "bsfc_g_per_kWh": float(bsfc),
                }
            )
            rows.append([rc, float(phi), float(afr_act), float(bsfc)])

    csv_path = OUT_DIR / "bsfc_vs_phi_rc_table.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["compression_ratio", "phi", "AFR_actual", "bsfc_g_per_kWh"])
        for r in rows:
            w.writerow(r)
    print(f"[BSFC phi] Wrote CSV: {csv_path}")

    fig = go.Figure()
    for rc, recs in series.items():
        recs_sorted = sorted(recs, key=lambda r: r["phi"])
        phi = [r["phi"] for r in recs_sorted]
        bsfc = [r["bsfc_g_per_kWh"] for r in recs_sorted]
        fig.add_trace(
            go.Scatter(
                x=phi,
                y=bsfc,
                mode="lines+markers",
                name=f"r_c = {rc:g}",
            )
        )

    fig.update_layout(
        title="Brake specific fuel consumption vs equivalence ratio",
        xaxis_title="Equivalence ratio phi",
        yaxis_title="BSFC [g/kWh]",
    )

    html_path = OUT_DIR / "bsfc_vs_phi_rc_plot.html"
    fig.write_html(str(html_path))
    print(f"[BSFC phi] Wrote HTML plot: {html_path}")


if __name__ == "__main__":  # pragma: no cover
    main()
