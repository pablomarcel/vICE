# simulator/tools/tool_bsfc_map_epa.py

from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List
import json
import csv
import math
import argparse

import numpy as np
import plotly.graph_objects as go

from ..core import EngineSimulator
from .. import io

ROOT = Path(__file__).resolve().parents[1]
IN_DIR = ROOT / "in"
OUT_DIR = ROOT / "out"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _deep_copy_cfg(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Cheap deep copy via JSON round-trip."""
    return json.loads(json.dumps(cfg))


def _run_grid_point(cfg_base: Dict[str, Any], speed_rpm: float, pint_bar: float) -> Dict[str, Any]:
    """Run a single operating point and return BSFC / η_th / BMEP / torque / power.

    Axes:
      - speed_rpm: engine speed [rpm]
      - pint_bar:  intake absolute pressure [bar]
    """
    cfg = _deep_copy_cfg(cfg_base)
    op = cfg.setdefault("operating", {})
    op["engine_speed_rpm"] = float(speed_rpm)
    op["intake_pressure_Pa"] = float(pint_bar * 1e5)

    sim = EngineSimulator.from_dict(cfg)
    res = sim.run(cycles=1)

    return {
        "speed_rpm": float(speed_rpm),
        "pint_bar": float(pint_bar),
        "bmep_bar": res.bmep_bar,
        "torque_Nm": res.brake_torque_Nm,
        "power_kW": res.brake_power_kW,
        "bsfc_g_per_kWh": res.bsfc_g_per_kWh,
        "eta_b_th": res.brake_thermal_efficiency,
    }


def _ensure_dir(path: Path) -> None:
    """Ensure parent directory for a file path exists."""
    if path.suffix:
        path.parent.mkdir(parents=True, exist_ok=True)
    else:
        path.mkdir(parents=True, exist_ok=True)


def _write_csv(points: List[Dict[str, Any]], path: Path) -> None:
    if not points:
        print(f"[BSFC-MAP-EPA] No points to write for {path.name}, skipping CSV.")
        return

    _ensure_dir(path)
    fieldnames = [
        "speed_rpm",
        "pint_bar",
        "bmep_bar",
        "torque_Nm",
        "power_kW",
        "bsfc_g_per_kWh",
        "eta_b_th",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in sorted(points, key=lambda r: (r["speed_rpm"], r["pint_bar"])):
            w.writerow(r)

    print(f"[BSFC-MAP-EPA] Wrote CSV grid: {path}")


def _bmep_to_torque_Nm(bmep_bar: float, Vd_total_m3: float, stroke_type: str) -> float:
    """Convert BMEP [bar] to torque [Nm] for the full engine.

    For 4-stroke:   BMEP = 4πT / Vd  →  T = BMEP * Vd / (4π)
    For 2-stroke:   BMEP = 2πT / Vd  →  T = BMEP * Vd / (2π)
    """
    if Vd_total_m3 <= 0.0:
        return 0.0

    stroke = (stroke_type or "").lower()
    k = 2.0 if ("two" in stroke or "2-" in stroke) else 4.0
    bmep_Pa = float(bmep_bar) * 1e5
    return bmep_Pa * Vd_total_m3 / (k * math.pi)


# ---------------------------------------------------------------------------
# Build regular N–BMEP grids from N–p_int samples
# ---------------------------------------------------------------------------

def _build_bmep_grids(records: List[Dict[str, Any]], n_bmep: int = 25) -> Dict[str, Any]:
    """Convert flat list of (N, p_int) records into regular (N, BMEP) grids.

    Returns:
      - speeds: sorted unique speeds [rpm]
      - bmep:   regular BMEP levels [bar]
      - z_bsfc: BSFC [g/kWh]      shape = (len(bmep), len(speeds))
      - z_eta:  brake η_th [%]    same shape
      - z_pwr:  brake power [kW]  same shape
      - z_trq:  brake torque [Nm] same shape
      - bmep_min / bmep_max
    """
    if not records:
        raise ValueError("No records provided to build N–BMEP grids")

    speeds = sorted({float(r["speed_rpm"]) for r in records})
    by_speed: Dict[float, List[Dict[str, Any]]] = {N: [] for N in speeds}
    for r in records:
        by_speed[float(r["speed_rpm"])].append(r)

    bmep_vals = [
        float(r["bmep_bar"])
        for r in records
        if r.get("bmep_bar") is not None
    ]
    if not bmep_vals:
        raise ValueError("No BMEP data found in records")

    bmep_min = max(0.0, min(bmep_vals))
    bmep_max = max(bmep_vals)
    if bmep_max <= bmep_min:
        bmep_max = bmep_min + 0.1

    bmep_levels = np.linspace(bmep_min, bmep_max, int(max(n_bmep, 5)))

    nx = len(speeds)
    ny = len(bmep_levels)

    def _nan_grid() -> List[List[float]]:
        return [[float("nan")] * nx for _ in range(ny)]

    z_bsfc = _nan_grid()
    z_eta = _nan_grid()
    z_pwr = _nan_grid()
    z_trq = _nan_grid()

    for ix, N in enumerate(speeds):
        pts = by_speed[N]
        pts_valid = [p for p in pts if p.get("bmep_bar") is not None]
        if not pts_valid:
            continue

        pts_valid.sort(key=lambda r: r["bmep_bar"])
        bmep_arr = np.array([float(p["bmep_bar"]) for p in pts_valid], dtype=float)

        def _to_array(key: str, scale: float = 1.0) -> np.ndarray:
            vals: List[float] = []
            for p in pts_valid:
                v = p.get(key)
                if v is None:
                    vals.append(float("nan"))
                else:
                    vals.append(float(v) * scale)
            return np.array(vals, dtype=float)

        bsfc_arr = _to_array("bsfc_g_per_kWh", scale=1.0)
        eta_arr = _to_array("eta_b_th", scale=100.0)  # → %
        pwr_arr = _to_array("power_kW", scale=1.0)
        trq_arr = _to_array("torque_Nm", scale=1.0)

        for iy, target in enumerate(bmep_levels):
            idx = int(np.argmin(np.abs(bmep_arr - target)))
            if 0 <= idx < bmep_arr.size:
                if np.isfinite(bsfc_arr[idx]):
                    z_bsfc[iy][ix] = float(bsfc_arr[idx])
                if np.isfinite(eta_arr[idx]):
                    z_eta[iy][ix] = float(eta_arr[idx])
                if np.isfinite(pwr_arr[idx]):
                    z_pwr[iy][ix] = float(pwr_arr[idx])
                if np.isfinite(trq_arr[idx]):
                    z_trq[iy][ix] = float(trq_arr[idx])

    return {
        "speeds": [float(s) for s in speeds],
        "bmep": [float(b) for b in bmep_levels],
        "z_bsfc": z_bsfc,
        "z_eta": z_eta,
        "z_pwr": z_pwr,
        "z_trq": z_trq,
        "bmep_min": float(bmep_min),
        "bmep_max": float(bmep_max),
    }


# ---------------------------------------------------------------------------
# Plotting – EPA style
# ---------------------------------------------------------------------------

def _plot_bsfc_map_epa(html_path: Path, grid: Dict[str, Any],
                       Vd_total_m3: float, stroke_type: str) -> None:
    speeds: List[float] = grid["speeds"]
    bmep: List[float] = grid["bmep"]
    z_bsfc: List[List[float]] = grid["z_bsfc"]
    z_pwr: List[List[float]] = grid["z_pwr"]
    z_trq: List[List[float]] = grid["z_trq"]
    bmep_min: float = grid["bmep_min"]
    bmep_max: float = grid["bmep_max"]

    z_bsfc_arr = np.array(z_bsfc, dtype=float)
    z_pwr_arr = np.array(z_pwr, dtype=float)
    z_trq_arr = np.array(z_trq, dtype=float)

    # Best BSFC point
    best_speed = best_bmep = best_bsfc = None
    if np.isfinite(z_bsfc_arr).any():
        flat_idx = int(np.nanargmin(z_bsfc_arr))
        iy, ix = np.unravel_index(flat_idx, z_bsfc_arr.shape)
        best_speed = speeds[ix]
        best_bmep = bmep[iy]
        best_bsfc = float(z_bsfc_arr[iy, ix])

    # Power contour levels
    pwr_min = np.nanmin(z_pwr_arr) if np.isfinite(z_pwr_arr).any() else 0.0
    pwr_max = np.nanmax(z_pwr_arr) if np.isfinite(z_pwr_arr).any() else 0.0
    if pwr_max <= 0.0:
        pwr_min, pwr_max = 0.0, 0.0

    # More power traces: 20 kW step (40 if huge range)
    step = 20.0
    if pwr_max - pwr_min > 400.0:
        step = 40.0
    if pwr_max > 0.0:
        start = step * math.ceil(max(pwr_min, 10.0) / step)
        end = step * math.floor(pwr_max / step)
        if end <= start:
            start, end = max(step, pwr_min), pwr_max
    else:
        start, end = 0.0, 0.0

    fig = go.Figure()

    # customdata for richer hover: torque, power
    custom_bsfc = np.dstack([z_trq_arr, z_pwr_arr])

    # BSFC filled contours
    fig.add_trace(
        go.Contour(
            x=speeds,
            y=bmep,
            z=z_bsfc,
            colorbar_title="BSFC [g/kWh]",
            colorscale="Plasma",
            contours=dict(
                showlabels=True,
                labelfont=dict(size=10, color="white"),
            ),
            line=dict(width=0.6, color="rgba(0,0,0,0.3)"),
            name="BSFC",
            customdata=custom_bsfc,
            hovertemplate=(
                "N = %{x:.0f} rpm<br>"
                "BMEP = %{y:.1f} bar<br>"
                "T = %{customdata[0]:.1f} Nm<br>"
                "P_b = %{customdata[1]:.1f} kW<br>"
                "BSFC = %{z:.1f} g/kWh"
                "<extra></extra>"
            ),
        )
    )

    # Constant brake power lines (dashed lime, fluorescent text)
    if pwr_max > 0.0:
        fig.add_trace(
            go.Contour(
                x=speeds,
                y=bmep,
                z=z_pwr,
                contours=dict(
                    showlines=True,
                    showlabels=True,
                    labelfont=dict(size=9, color="lime"),
                    coloring="none",
                    start=start,
                    end=end,
                    size=step,
                ),
                line=dict(width=1.2, color="lime", dash="dash"),
                showscale=False,
                name="Brake power [kW]",
                hovertemplate=(
                    "N = %{x:.0f} rpm<br>"
                    "BMEP = %{y:.1f} bar<br>"
                    "P_b = %{z:.1f} kW"
                    "<extra></extra>"
                ),
            )
        )

    # Best BSFC marker – red text
    if best_speed is not None and best_bmep is not None and best_bsfc is not None:
        fig.add_trace(
            go.Scatter(
                x=[best_speed],
                y=[best_bmep],
                mode="markers+text",
                text=[f"{best_bsfc:.1f}"],
                textposition="top center",
                textfont=dict(color="red", size=12),
                marker=dict(symbol="star", size=12, line=dict(width=1), color="lime"),
                name="Best BSFC",
            )
        )

    # Torque ticks mapped onto BMEP axis
    bmep_ticks = np.linspace(bmep_min, bmep_max, 6)
    torque_ticks = [_bmep_to_torque_Nm(b, Vd_total_m3, stroke_type) for b in bmep_ticks]

    fig.update_layout(
        title="Baby F1 Toy Engine – EPA-style BSFC Map",
        xaxis=dict(title="Speed [rpm]"),
        yaxis=dict(title="BMEP [bar]", range=[bmep_min, bmep_max]),
        # Right side shows torque numbers at same vertical positions
        yaxis2=dict(
            title="Brake torque [Nm]",
            overlaying="y",
            side="right",
            showgrid=False,
            tickvals=list(bmep_ticks),
            ticktext=[f"{t:.0f}" for t in torque_ticks],
        ),
        legend=dict(x=0.02, y=0.98, bgcolor="rgba(255,255,255,0.6)"),
    )

    fig.add_annotation(
        xref="paper",
        yref="paper",
        x=0.01,
        y=1.08,
        showarrow=False,
        text="Filled contours: BSFC [g/kWh]; dashed lime lines: Brake power [kW]",
    )

    _ensure_dir(html_path)
    fig.write_html(str(html_path))
    print(f"[BSFC-MAP-EPA] Wrote EPA-style BSFC map: {html_path}")


# ---------------------------------------------------------------------------
# Main / CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate an EPA-style BSFC map (N vs BMEP) for any engine JSON config.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=str(IN_DIR / "sample_si_engine.json"),
        help="Path to engine configuration JSON (default: simulator/in/sample_si_engine.json)",
    )
    parser.add_argument(
        "--html",
        type=str,
        default=str(OUT_DIR / "bsfc_map_epa.html"),
        help="Output HTML path for the BSFC map (default: simulator/out/bsfc_map_epa.html)",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=str(OUT_DIR / "bsfc_map_epa_points.csv"),
        help="Output CSV path for raw grid points (default: simulator/out/bsfc_map_epa_points.csv)",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> None:
    args = _parse_args(argv)

    base_cfg_path = Path(args.config)
    if not base_cfg_path.exists():
        raise SystemExit(f"Base config not found: {base_cfg_path}")

    cfg_base = io.load_json(base_cfg_path)

    # Get displacement and stroke type from a "dummy" simulator instance
    sim0 = EngineSimulator.from_dict(cfg_base)
    Vd_cyl = sim0.geometry.displacement_volume()
    n_cyl = max(int(sim0.operating.num_cylinders), 1)
    Vd_total_m3 = Vd_cyl * n_cyl
    stroke_type = sim0.operating.stroke_type

    # N / p_int grid
    speeds_rpm = [
        500, 1000, 1500, 2000, 2500, 3000, 3500,
        4000, 4500, 5000, 5500, 6000, 6500, 7000, 7500, 8000,
    ]
    pint_bar_list = [
        0.8, 0.90, 1.013,
        1.20, 1.40, 1.60, 1.80, 2.0,
        2.20, 2.40, 2.60, 2.80, 3.0,
        3.20, 3.40, 3.60, 3.80, 4.0,
    ]

    print("[BSFC-MAP-EPA] Building N–p_int grid ...")
    points: List[Dict[str, Any]] = []
    for N in speeds_rpm:
        for pint_bar in pint_bar_list:
            pt = _run_grid_point(cfg_base, N, pint_bar)
            points.append(pt)
            print(
                f"  N={N:6.1f} rpm  p_int={pint_bar:5.3f} bar  "
                f"BMEP={pt.get('bmep_bar')!r}  T={pt.get('torque_Nm')!r} Nm  "
                f"P_b={pt.get('power_kW')!r} kW  BSFC={pt.get('bsfc_g_per_kWh')!r}"
            )

    csv_path = Path(args.csv)
    _write_csv(points, csv_path)

    print("[BSFC-MAP-EPA] Re-gridding to N–BMEP space ...")
    grid = _build_bmep_grids(points, n_bmep=25)

    html_path = Path(args.html)
    _plot_bsfc_map_epa(html_path, grid, Vd_total_m3, stroke_type)


if __name__ == "__main__":  # pragma: no cover
    main()
