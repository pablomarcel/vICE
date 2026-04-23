from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Any, List

import numpy as np
import plotly.graph_objects as go

from ..core import EngineSimulator
from ..fuels import get_fuel


def _load_config(path: str | Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_csv(path: str | Path, rows: List[Dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        # nothing to write
        return

    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _parse_rc_list(rc_arg: str | None) -> List[float]:
    """Parse a comma-separated list of compression ratios.

    If rc_arg is None, use a default sweep of 8..15 in steps of 0.5.
    """
    if not rc_arg:
        return [8.0 + 0.5 * i for i in range(0, 15)]  # 8.0, 8.5, ..., 15.0

    vals: List[float] = []
    for token in rc_arg.split(","):
        token = token.strip()
        if not token:
            continue
        vals.append(float(token))
    return vals


def _phi_grid(phi_min: float, phi_max: float, phi_step: float) -> np.ndarray:
    n_steps = int(math.floor((phi_max - phi_min) / phi_step + 0.5))
    return np.linspace(phi_min, phi_max, n_steps + 1)


def _make_bsfc_figure(rows: List[Dict[str, Any]]) -> go.Figure:
    """Build a Plotly figure: BSFC vs φ with one curve per compression ratio."""
    # Group rows by rc
    by_rc: Dict[float, List[Dict[str, Any]]] = {}
    for r in rows:
        rc = float(r["compression_ratio"])
        by_rc.setdefault(rc, []).append(r)

    fig = go.Figure()

    # Sort rc for nicer legend ordering
    for rc in sorted(by_rc.keys()):
        data = sorted(by_rc[rc], key=lambda r: float(r["phi"]))
        phi_vals = [float(r["phi"]) for r in data]
        bsfc_vals = [float(r["bsfc_g_per_kWh"]) if r["bsfc_g_per_kWh"] is not None else None for r in data]

        fig.add_trace(
            go.Scatter(
                x=phi_vals,
                y=bsfc_vals,
                mode="lines+markers",
                name=f"r_c = {rc:g}",
            )
        )

    fig.update_layout(
        title="Brake specific fuel consumption vs equivalence ratio",
        xaxis_title="Equivalence ratio φ",
        yaxis_title="BSFC [g/kWh]",
        hovermode="x unified",
    )
    return fig


def run_bsfc_sweep(
    config_path: str | Path,
    out_csv: str | Path | None,
    out_html: str | Path | None,
    rc_list: List[float],
    phi_min: float,
    phi_max: float,
    phi_step: float,
) -> None:
    base_cfg = _load_config(config_path)

    # Determine fuel stoich AFR from the config
    fuel_id = base_cfg.get("operating", {}).get("fuel_id", "gasoline")
    fuel = get_fuel(fuel_id)
    afr_st = fuel.afr_stoich

    phis = _phi_grid(phi_min, phi_max, phi_step)

    rows: List[Dict[str, Any]] = []

    for rc in rc_list:
        for phi in phis:
            # Build a fresh config per point to avoid mutation carry-over
            cfg = json.loads(json.dumps(base_cfg))  # deep copy via JSON

            geom = cfg.setdefault("geometry", {})
            op = cfg.setdefault("operating", {})

            # Set compression ratio
            geom["compression_ratio"] = float(rc)

            # Set AFR from φ:  φ = (AF)_stoich / (AF)_act
            afr_act = afr_st / float(phi)
            op["air_fuel_ratio"] = float(afr_act)

            # Engine speed etc. come from base_cfg (we are sweeping only φ and r_c)
            sim = EngineSimulator.from_dict(cfg)
            result = sim.run(cycles=1)

            # Some runs (very lean/rich) may fail to produce BSFC (e.g., zero power)
            bsfc = result.bsfc_g_per_kWh
            eta_b = result.brake_thermal_efficiency
            eta_i = result.indicated_thermal_efficiency

            row: Dict[str, Any] = {
                "compression_ratio": float(rc),
                "phi": float(phi),
                "lambda": result.lambda_value if result.lambda_value is not None else afr_act / afr_st,
                "bsfc_g_per_kWh": bsfc,
                "brake_thermal_efficiency": eta_b,
                "indicated_thermal_efficiency": eta_i,
                "imep_bar": result.imep_bar,
                "bmep_bar": result.bmep_bar,
                "mechanical_efficiency_effective": result.mechanical_efficiency_effective,
                "heat_transfer_eff_factor": result.heat_transfer_eff_factor,
            }

            rows.append(row)

    # Write CSV
    if out_csv:
        _write_csv(out_csv, rows)

    # Write HTML plot
    if out_html:
        Path(out_html).parent.mkdir(parents=True, exist_ok=True)
        fig = _make_bsfc_figure(rows)
        fig.write_html(out_html, include_plotlyjs="cdn")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sweep BSFC vs equivalence ratio φ and compression ratio r_c."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Base JSON config (geometry + operating) for EngineSimulator.",
    )
    parser.add_argument(
        "--out-csv",
        help="Path to CSV output with all (r_c, φ) points.",
    )
    parser.add_argument(
        "--out-html",
        help="Optional Plotly HTML output (BSFC vs φ curves).",
    )
    parser.add_argument(
        "--rc",
        help='Comma-separated list of compression ratios, e.g. "8,10,12". '
             "If omitted, defaults to 8.0..15.0 in steps of 0.5.",
    )
    parser.add_argument(
        "--phi-min",
        type=float,
        default=0.8,
        help="Minimum equivalence ratio φ (default: 0.8).",
    )
    parser.add_argument(
        "--phi-max",
        type=float,
        default=1.2,
        help="Maximum equivalence ratio φ (default: 1.2).",
    )
    parser.add_argument(
        "--phi-step",
        type=float,
        default=0.05,
        help="Step in φ (default: 0.05).",
    )

    args = parser.parse_args(argv)

    rc_list = _parse_rc_list(args.rc)

    run_bsfc_sweep(
        config_path=args.config,
        out_csv=args.out_csv,
        out_html=args.out_html,
        rc_list=rc_list,
        phi_min=args.phi_min,
        phi_max=args.phi_max,
        phi_step=args.phi_step,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
