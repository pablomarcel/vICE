from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List
import csv
import json

import plotly.graph_objects as go

from ..core import EngineSimulator, EngineGeometry

ROOT = Path(__file__).resolve().parents[1]
IN_DIR = ROOT / "in"
OUT_DIR = ROOT / "out"


def _load_base_config(name: str = "sample_si_engine.json") -> Dict[str, Any]:
    path = IN_DIR / name
    with path.open("r", encoding="utf-8") as f:
        cfg = json.load(f)
    print(f"[BSFC Vd] Loaded base config: {path}")
    return cfg


def main() -> None:
    # Qualitative BSFC vs displacement curve, similar to Pulkrabek Fig. 2-14.
    base_cfg = _load_base_config()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Base geometry / cylinder-count for scaling
    base_sim = EngineSimulator.from_dict(base_cfg)
    base_geom = base_sim.geometry
    base_op = base_sim.operating
    base_n_cyl = max(int(getattr(base_op, "num_cylinders", 4)), 1)

    # (total displacement [L], representative speed [rpm])
    cases = [
        (5.0, 4200.0),
        (10.0, 3600.0),
        (15.0, 3200.0),
        (20.0, 2800.0),
        (25.0, 2400.0),
    ]

    rows: List[List[float]] = []
    disp_L: List[float] = []
    bsfc_list: List[float] = []

    for Vd_L, N in cases:
        cfg = json.loads(json.dumps(base_cfg))
        geom_cfg = cfg.setdefault("geometry", {})
        op = cfg.setdefault("operating", {})
        op["engine_speed_rpm"] = float(N)
        op.setdefault("friction_mode", "passenger")

        # Determine cylinder count for this case (default to base)
        n_cyl = int(op.get("num_cylinders", base_n_cyl)) or base_n_cyl

        # Target total and per-cylinder displacement [m³]
        Vd_target_total_m3 = float(Vd_L) * 1e-3
        Vd_target_cyl = Vd_target_total_m3 / float(n_cyl)

        # Current geometry (fallback to base if fields missing)
        geom_current = EngineGeometry(
            bore_m=float(geom_cfg.get("bore_m", base_geom.bore_m)),
            stroke_m=float(geom_cfg.get("stroke_m", base_geom.stroke_m)),
            con_rod_m=float(geom_cfg.get("con_rod_m", base_geom.con_rod_m)),
            compression_ratio=float(
                geom_cfg.get("compression_ratio", base_geom.compression_ratio)
            ),
            piston_pin_offset_m=float(
                geom_cfg.get("piston_pin_offset_m", base_geom.piston_pin_offset_m)
            ),
        )
        Vd_base_cyl = geom_current.displacement_volume()

        if Vd_base_cyl > 0.0 and Vd_target_cyl > 0.0:
            # Scale bore, stroke and rod length with a single linear factor
            scale = (Vd_target_cyl / Vd_base_cyl) ** (1.0 / 3.0)
        else:
            scale = 1.0

        geom_cfg["bore_m"] = geom_current.bore_m * scale
        geom_cfg["stroke_m"] = geom_current.stroke_m * scale
        geom_cfg["con_rod_m"] = geom_current.con_rod_m * scale
        geom_cfg["compression_ratio"] = geom_current.compression_ratio
        geom_cfg["piston_pin_offset_m"] = geom_current.piston_pin_offset_m

        sim = EngineSimulator.from_dict(cfg)
        result = sim.run(cycles=1).to_dict()
        bsfc = result.get("bsfc_g_per_kWh")
        if bsfc is None:
            continue

        disp_L.append(float(Vd_L))
        bsfc_list.append(float(bsfc))
        rows.append([float(Vd_L), float(N), float(bsfc)])

    csv_path = OUT_DIR / "bsfc_vs_displacement_table.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["displacement_L", "representative_speed_rpm", "bsfc_g_per_kWh"])
        for r in rows:
            w.writerow(r)
    print(f"[BSFC Vd] Wrote CSV: {csv_path}")

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=disp_L,
            y=bsfc_list,
            mode="lines+markers",
            name="BSFC vs displacement",
        )
    )
    fig.update_layout(
        title="Brake specific fuel consumption vs displacement (qualitative)",
        xaxis_title="Displacement Vd [L]",
        yaxis_title="BSFC [g/kWh]",
    )

    html_path = OUT_DIR / "bsfc_vs_displacement_plot.html"
    fig.write_html(str(html_path))
    print(f"[BSFC Vd] Wrote HTML plot: {html_path}")


if __name__ == "__main__":  # pragma: no cover
    main()
