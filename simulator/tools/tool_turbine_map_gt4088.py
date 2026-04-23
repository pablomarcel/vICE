"""
tool_turbine_map_gt4088.py

Plot a Garrett-style turbine swallowing map from CSV and optionally
overlay an engine turbine operating line.

Map CSV columns:
    A_over_R, PR_turb, m_corr_lb_per_min, eta

Operating-line CSV (from tool_turbo_match_opline):
    pr_turb, m_corr_lb_per_min, speed_rpm, ...

Usage:

    python -m simulator.tools.tool_turbine_map_gt4088 \\
        --csv simulator/in/turbine_gt4088_like.csv \\
        --opline-csv simulator/out/turbo_match_opline.csv \\
        --out-html simulator/out/turbine_gt4088_map.html
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, List

import numpy as np
import plotly.graph_objects as go


def _load_turbine_map(csv_path: Path) -> Dict[float, Dict[str, np.ndarray]]:
    by_ar: Dict[float, Dict[str, List[float]]] = {}

    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            A_R = float(row["A_over_R"])
            pr = float(row["PR_turb"])
            m = float(row["m_corr_lb_per_min"])
            eta = float(row["eta"])

            d = by_ar.setdefault(A_R, {"PR": [], "m_corr": [], "eta": []})
            d["PR"].append(pr)
            d["m_corr"].append(m)
            d["eta"].append(eta)

    out: Dict[float, Dict[str, np.ndarray]] = {}
    for A_R, d in by_ar.items():
        idx = np.argsort(d["PR"])
        out[A_R] = {
            "PR": np.array(d["PR"], dtype=float)[idx],
            "m_corr": np.array(d["m_corr"], dtype=float)[idx],
            "eta": np.array(d["eta"], dtype=float)[idx],
        }
    return out


def _load_opline(csv_path: Path) -> Dict[str, np.ndarray]:
    PR: List[float] = []
    m: List[float] = []
    N: List[float] = []
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                PR.append(float(row["pr_turb"]))
                m.append(float(row["m_corr_lb_per_min"]))
                N.append(float(row["speed_rpm"]))
            except (KeyError, ValueError):
                continue
    if not PR:
        raise ValueError(f"No usable turbine operating-line data in {csv_path}")
    return {
        "PR": np.array(PR, dtype=float),
        "m_corr": np.array(m, dtype=float),
        "N": np.array(N, dtype=float),
    }


def build_figure(
    map_csv: Path,
    opline_csv: Path | None = None,
) -> go.Figure:
    maps = _load_turbine_map(map_csv)
    fig = go.Figure()

    colours = ["red", "blue", "green", "magenta", "orange"]
    for idx, (A_R, data) in enumerate(sorted(maps.items())):
        colour = colours[idx % len(colours)]
        fig.add_trace(
            go.Scatter(
                x=data["PR"],
                y=data["m_corr"],
                mode="lines",
                line=dict(color=colour, width=2),
                name=f"A/R = {A_R:.2f} map",
                hovertemplate=(
                    f"A/R = {A_R:.2f}<br>"
                    "PR_turb = %{x:.2f}<br>"
                    "m_corr = %{y:.1f} lb/min<extra></extra>"
                ),
            )
        )

    if opline_csv is not None and opline_csv.exists():
        op = _load_opline(opline_csv)
        fig.add_trace(
            go.Scatter(
                x=op["PR"],
                y=op["m_corr"],
                mode="lines+markers",
                line=dict(color="black", width=2, dash="dot"),
                marker=dict(
                    size=7,
                    color=op["N"],
                    colorscale="Plasma",
                    showscale=True,
                    colorbar=dict(title="Speed [rpm]"),
                ),
                name="Engine operating line",
                hovertemplate=(
                    "Engine N = %{marker.color:.0f} rpm<br>"
                    "PR_turb = %{x:.2f}<br>"
                    "m_corr = %{y:.1f} lb/min<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        title="Turbine swallowing chart",
        xaxis_title="Pressure ratio (T/S) P_T1 / P_2S",
        yaxis_title="Corrected gas turbine flow [lb/min]",
        template="plotly_white",
        legend=dict(x=0.02, y=0.98, bgcolor="rgba(255,255,255,0.7)"),
        margin=dict(l=80, r=80, t=60, b=60),
    )

    return fig


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Plot a Garrett-like turbine swallowing map from CSV.",
    )
    p.add_argument(
        "--csv",
        type=str,
        default="simulator/in/turbine_gt4088_like.csv",
        help="Turbine map CSV (default: simulator/in/turbine_gt4088_like.csv)",
    )
    p.add_argument(
        "--opline-csv",
        type=str,
        default=None,
        help="Optional turbine operating-line CSV to overlay (turbo_match_opline.csv)",
    )
    p.add_argument(
        "--out-html",
        type=str,
        default="simulator/out/turbine_gt4088_map.html",
        help="Output Plotly HTML (default: simulator/out/turbine_gt4088_map.html)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    map_csv = Path(args.csv)
    opline_csv = Path(args.opline_csv) if args.opline_csv else None
    out_html = Path(args.out_html)

    if not map_csv.exists():
        raise SystemExit(f"Turbine map CSV not found: {map_csv}")

    fig = build_figure(map_csv, opline_csv)
    out_html.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(out_html), include_plotlyjs="cdn")
    print(f"[TURB-MAP] Wrote turbine map HTML: {out_html}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
