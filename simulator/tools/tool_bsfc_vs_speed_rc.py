from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List
import csv
import json

import plotly.graph_objects as go

from ..core import EngineSimulator

ROOT = Path(__file__).resolve().parents[1]
IN_DIR = ROOT / "in"
OUT_DIR = ROOT / "out"


def _load_base_config(name: str = "sample_si_engine.json") -> Dict[str, Any]:
    path = IN_DIR / name
    with path.open("r", encoding="utf-8") as f:
        cfg = json.load(f)
    print(f"[BSFC rc–N] Loaded base config: {path}")
    return cfg


def main() -> None:
    # Pulkrabek-style BSFC vs speed for two compression ratios.
    # Mimics Fig. 2-12: bsfc vs engine speed for rc = 8 and 10.
    base_cfg = _load_base_config()

    speeds = [500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000, 5500, 6000, 6500, 7000, 7500, 8000]
    rc_values = [8.0, 8.5, 9.0, 9.5, 10.0, 10.5, 11.0, 11.5, 12.0, 12.5, 13.0, 13.5, 14.0, 14.5, 15.0]

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows: List[List[float]] = []
    series: Dict[float, List[Dict[str, float]]] = {rc: [] for rc in rc_values}

    for rc in rc_values:
        for N in speeds:
            cfg = json.loads(json.dumps(base_cfg))
            geom = cfg.setdefault("geometry", {})
            op = cfg.setdefault("operating", {})

            geom["compression_ratio"] = rc
            op["engine_speed_rpm"] = float(N)
            op.setdefault("friction_mode", "passenger")

            sim = EngineSimulator.from_dict(cfg)
            result = sim.run(cycles=1).to_dict()

            bsfc = result.get("bsfc_g_per_kWh")
            bmep = result.get("bmep_bar")
            if bsfc is None or bmep is None:
                continue

            series[rc].append(
                {
                    "speed_rpm": float(N),
                    "bsfc_g_per_kWh": float(bsfc),
                    "bmep_bar": float(bmep),
                }
            )
            rows.append([rc, float(N), float(bmep), float(bsfc)])

    csv_path = OUT_DIR / "bsfc_vs_speed_rc_table.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["compression_ratio", "speed_rpm", "bmep_bar", "bsfc_g_per_kWh"])
        for r in rows:
            w.writerow(r)
    print(f"[BSFC rc–N] Wrote CSV: {csv_path}")

    fig = go.Figure()
    for rc, recs in series.items():
        recs_sorted = sorted(recs, key=lambda r: r["speed_rpm"])
        N = [r["speed_rpm"] for r in recs_sorted]
        bsfc = [r["bsfc_g_per_kWh"] for r in recs_sorted]
        fig.add_trace(
            go.Scatter(
                x=N,
                y=bsfc,
                mode="lines+markers",
                name=f"r_c = {rc:g}",
            )
        )

    fig.update_layout(
        title="Brake specific fuel consumption vs speed (Pulkrabek-style)",
        xaxis_title="Engine speed N [rpm]",
        yaxis_title="BSFC [g/kWh]",
    )

    html_path = OUT_DIR / "bsfc_vs_speed_rc_plot.html"
    fig.write_html(str(html_path))
    print(f"[BSFC rc–N] Wrote HTML plot: {html_path}")


if __name__ == "__main__":  # pragma: no cover
    main()
