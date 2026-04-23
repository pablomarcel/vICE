"""
tool_compressor_map_efr71.py

Plot a BorgWarner‑EFR‑style compressor map from CSV and optionally
overlay an engine operating line exported by tool_turbo_match_opline.

Usage (from project root):

    python -m simulator.tools.tool_compressor_map_efr71 \\
        --csv simulator/in/compressor_efr71_grid.csv \\
        --speedlines-csv simulator/in/compressor_efr71_speedlines.csv \\
        --opline-csv simulator/out/turbo_match_opline.csv \\
        --out-html simulator/out/compressor_efr71_map.html

Map CSV columns (rectangular grid):
    m_dot_corr_kg_per_s, PR_comp, eta_c

Speed‑line CSV columns (one row per point):
    N_krpm, m_dot_corr_kg_per_s, PR_comp

Operating‑line CSV columns (from tool_turbo_match_opline):
    speed_rpm, pr_comp, m_dot_corr_kg_per_s, ...
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import plotly.graph_objects as go


def _load_grid(csv_path: Path) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    m_list: List[float] = []
    pr_list: List[float] = []
    eta_list: List[float] = []

    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            m_list.append(float(row["m_dot_corr_kg_per_s"]))
            pr_list.append(float(row["PR_comp"]))
            eta_list.append(float(row["eta_c"]))

    m_vals = sorted(set(m_list))
    pr_vals = sorted(set(pr_list))

    nx = len(m_vals)
    ny = len(pr_vals)
    Z = np.full((ny, nx), np.nan, dtype=float)

    m_index = {v: i for i, v in enumerate(m_vals)}
    pr_index = {v: j for j, v in enumerate(pr_vals)}

    for m, pr, eta in zip(m_list, pr_list, eta_list):
        i = m_index[m]
        j = pr_index[pr]
        Z[j, i] = eta

    return np.array(m_vals), np.array(pr_vals), Z


def _load_speedlines(csv_path: Path) -> Dict[float, Dict[str, np.ndarray]]:
    """Return dict keyed by N_krpm with arrays for m_corr & PR."""
    by_speed: Dict[float, Dict[str, List[float]]] = {}

    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            N = float(row["N_krpm"])
            m = float(row["m_dot_corr_kg_per_s"])
            pr = float(row["PR_comp"])
            d = by_speed.setdefault(N, {"m": [], "PR": []})
            d["m"].append(m)
            d["PR"].append(pr)

    out: Dict[float, Dict[str, np.ndarray]] = {}
    for N, d in by_speed.items():
        idx = np.argsort(d["m"])
        out[N] = {
            "m": np.array(d["m"], dtype=float)[idx],
            "PR": np.array(d["PR"], dtype=float)[idx],
        }
    return out


def _load_opline(csv_path: Path) -> Dict[str, np.ndarray]:
    """Operating line from turbo_match_opline.csv.

    Requires at least:
        m_dot_corr_kg_per_s, pr_comp, speed_rpm
    """
    m_list: List[float] = []
    pr_list: List[float] = []
    N_list: List[float] = []

    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                m_list.append(float(row["m_dot_corr_kg_per_s"]))
                pr_list.append(float(row["pr_comp"]))
                N_list.append(float(row["speed_rpm"]))
            except (KeyError, ValueError):
                continue

    if not m_list:
        raise ValueError(f"No usable operating-line data in {csv_path}")

    return {
        "m": np.array(m_list, dtype=float),
        "PR": np.array(pr_list, dtype=float),
        "N": np.array(N_list, dtype=float),
    }


def build_figure(
    map_csv: Path,
    speedlines_csv: Path | None = None,
    opline_csv: Path | None = None,
) -> go.Figure:
    X, Y, Z = _load_grid(map_csv)

    Z_plot = np.array(Z, copy=True)
    Z_plot[Z_plot < 0.62] = np.nan

    fig = go.Figure()

    fig.add_trace(
        go.Contour(
            x=X,
            y=Y,
            z=Z_plot,
            colorscale="Viridis",
            colorbar=dict(title="η_c", x=1.02),
            contours=dict(showlabels=True, labelfont=dict(size=10)),
            line=dict(width=0.5, color="rgba(0,0,0,0.3)"),
            name="η_c",
            hovertemplate=(
                "m_corr = %{x:.3f} kg/s<br>"
                "PR = %{y:.2f}<br>"
                "η_c = %{z:.2f}<extra></extra>"
            ),
        )
    )

    if speedlines_csv is not None and speedlines_csv.exists():
        maps = _load_speedlines(speedlines_csv)
        for N_krpm, data in sorted(maps.items()):
            fig.add_trace(
                go.Scatter(
                    x=data["m"],
                    y=data["PR"],
                    mode="lines+markers",
                    name=f"{N_krpm:.1f} krpm map",
                    line=dict(width=2),
                    marker=dict(size=6),
                    hovertemplate=(
                        f"N_red = {N_krpm:.1f} krpm<br>"
                        "m_corr = %{x:.3f} kg/s<br>"
                        "PR = %{y:.2f}<extra></extra>"
                    ),
                )
            )

    if opline_csv is not None and opline_csv.exists():
        op = _load_opline(opline_csv)
        fig.add_trace(
            go.Scatter(
                x=op["m"],
                y=op["PR"],
                mode="lines+markers",
                name="Engine operating line",
                marker=dict(
                    size=7,
                    color=op["N"],
                    colorscale="Plasma",
                    showscale=True,
                    colorbar=dict(title="Speed [rpm]", x=1.10),
                ),
                line=dict(width=2, dash="dot"),
                hovertemplate=(
                    "Engine N = %{marker.color:.0f} rpm<br>"
                    "m_corr = %{x:.3f} kg/s<br>"
                    "PR = %{y:.2f}<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        title="Compressor map with operating line",
        xaxis_title="Corrected air mass flow [kg/s]",
        yaxis_title="Compressor pressure ratio PR = p2 / p1",
        template="plotly_white",
        legend=dict(x=0.02, y=0.98, bgcolor="rgba(255,255,255,0.7)"),
        margin=dict(l=80, r=120, t=60, b=60),
    )

    return fig


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Plot an EFR-style compressor map from CSV.",
    )
    p.add_argument(
        "--csv",
        type=str,
        default="simulator/in/compressor_efr71_grid.csv",
        help="Compressor map CSV (default: simulator/in/compressor_efr71_grid.csv)",
    )
    p.add_argument(
        "--speedlines-csv",
        type=str,
        default="simulator/in/compressor_efr71_speedlines.csv",
        help="Optional speed-line CSV (default: simulator/in/compressor_efr71_speedlines.csv)",
    )
    p.add_argument(
        "--opline-csv",
        type=str,
        default=None,
        help="Optional turbo_match_opline CSV to overlay.",
    )
    p.add_argument(
        "--out-html",
        type=str,
        default="simulator/out/compressor_efr71_map.html",
        help="Output Plotly HTML (default: simulator/out/compressor_efr71_map.html)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    map_csv = Path(args.csv)
    speed_csv = Path(args.speedlines_csv) if args.speedlines_csv else None
    opline_csv = Path(args.opline_csv) if args.opline_csv else None
    out_html = Path(args.out_html)

    if not map_csv.exists():
        raise SystemExit(f"Map CSV not found: {map_csv}")

    fig = build_figure(map_csv, speed_csv, opline_csv)
    out_html.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(out_html), include_plotlyjs="cdn")
    print(f"[COMP-MAP] Wrote compressor map HTML: {out_html}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
