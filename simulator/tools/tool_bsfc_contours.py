from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List
import json
import csv

import plotly.graph_objects as go

from ..core import EngineSimulator
from .. import io


ROOT = Path(__file__).resolve().parents[1]
IN_DIR = ROOT / "in"
OUT_DIR = ROOT / "out"


def _deep_copy_cfg(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Cheap deep copy via JSON round-trip.

    We avoid importing copy.deepcopy just to keep the tool self-contained.
    """
    return json.loads(json.dumps(cfg))


def _run_grid_point(cfg_base: Dict[str, Any], speed_rpm: float, pint_bar: float) -> Dict[str, Any]:
    """Run a single operating point and return BSFC / η_th / BMEP.

    Axes are:
      - speed_rpm: engine speed [rpm]
      - pint_bar: intake absolute pressure [bar]

    We keep the rest of the configuration identical to the base config.
    """
    cfg = _deep_copy_cfg(cfg_base)
    op = cfg.setdefault("operating", {})
    op["engine_speed_rpm"] = float(speed_rpm)
    op["intake_pressure_Pa"] = float(pint_bar * 1e5)

    sim = EngineSimulator.from_dict(cfg)
    sim_result = sim.run(cycles=1)

    return {
        "speed_rpm": float(speed_rpm),
        "pint_bar": float(pint_bar),
        "bmep_bar": sim_result.bmep_bar,
        "bsfc_g_per_kWh": sim_result.bsfc_g_per_kWh,
        "eta_b_th": sim_result.brake_thermal_efficiency,
    }


def _build_grids(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Convert a flat list of records into 2-D grids for contour plots.

    Returns a dict with:
      - speeds: sorted unique speed values [rpm]
      - pint:   sorted unique intake pressures [bar]
      - z_bsfc: 2-D list [len(pint) x len(speeds)] of BSFC [g/kWh]
      - z_eta:  2-D list [len(pint) x len(speeds)] of brake η_th [%]
    """
    if not records:
        raise ValueError("No records provided to build BSFC/η_th grids")

    speeds = sorted({r["speed_rpm"] for r in records})
    pint = sorted({r["pint_bar"] for r in records})

    speed_index = {v: i for i, v in enumerate(speeds)}
    pint_index = {v: j for j, v in enumerate(pint)}

    def _nan_grid(ny: int, nx: int) -> List[List[float]]:
        return [[float("nan")] * nx for _ in range(ny)]

    z_bsfc = _nan_grid(len(pint), len(speeds))
    z_eta = _nan_grid(len(pint), len(speeds))

    for r in records:
        i = speed_index[r["speed_rpm"]]
        j = pint_index[r["pint_bar"]]
        bsfc = r.get("bsfc_g_per_kWh")
        eta = r.get("eta_b_th")
        if bsfc is not None:
            z_bsfc[j][i] = float(bsfc)
        if eta is not None:
            # convert to percent for nicer contours
            z_eta[j][i] = float(eta) * 100.0

    return {
        "speeds": speeds,
        "pint": pint,
        "z_bsfc": z_bsfc,
        "z_eta": z_eta,
    }


def _ensure_dir(path: Path) -> None:
    if path.is_dir():
        path.mkdir(parents=True, exist_ok=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)


def _write_csv(points: List[Dict[str, Any]], path: Path) -> None:
    if not points:
        print(f"[BSFC-MAP] No points to write for {path.name}, skipping CSV.")
        return
    _ensure_dir(path)
    fieldnames = ["speed_rpm", "pint_bar", "bmep_bar", "bsfc_g_per_kWh", "eta_b_th"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in sorted(points, key=lambda r: (r["speed_rpm"], r["pint_bar"])):
            w.writerow(r)
    print(f"[BSFC-MAP] Wrote CSV grid: {path}")


def _plot_contours_bsfc(html_path: Path, grid: Dict[str, Any]) -> None:
    speeds = grid["speeds"]
    pint = grid["pint"]
    z_bsfc = grid["z_bsfc"]

    fig = go.Figure(
        data=go.Contour(
            x=speeds,
            y=pint,
            z=z_bsfc,
            colorbar_title="BSFC [g/kWh]",
            contours=dict(showlabels=True, labelfont=dict(size=10)),
        )
    )
    fig.update_layout(
        title="BSFC contour map – speed vs intake pressure",
        xaxis_title="Speed [rpm]",
        yaxis_title="Intake pressure [bar abs]",
    )
    _ensure_dir(html_path)
    fig.write_html(str(html_path))
    print(f"[BSFC-MAP] Wrote BSFC contour map: {html_path}")


def _plot_contours_eta(html_path: Path, grid: Dict[str, Any]) -> None:
    speeds = grid["speeds"]
    pint = grid["pint"]
    z_eta = grid["z_eta"]

    fig = go.Figure(
        data=go.Contour(
            x=speeds,
            y=pint,
            z=z_eta,
            colorbar_title="Brake η_th [%]",
            contours=dict(showlabels=True, labelfont=dict(size=10)),
        )
    )
    fig.update_layout(
        title="Brake thermal efficiency contour map – speed vs intake pressure",
        xaxis_title="Speed [rpm]",
        yaxis_title="Intake pressure [bar abs]",
    )
    _ensure_dir(html_path)
    fig.write_html(str(html_path))
    print(f"[BSFC-MAP] Wrote η_th contour map: {html_path}")


def main() -> None:
    # Base configuration
    base_cfg_path = IN_DIR / "sample_si_engine.json"
    if not base_cfg_path.exists():
        raise SystemExit(f"Base config not found: {base_cfg_path}")

    cfg_base = io.load_json(base_cfg_path)

    # You can tweak these lists to refine map resolution.
    speeds_rpm = [500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000, 5500, 6000, 6500, 7000, 7500, 8000]
    pint_bar_list = [0.8, 0.90, 1.013, 1.20, 1.40, 1.60, 1.80, 2.0, 2.20, 2.40, 2.60, 2.80, 3.0, 3.20, 3.40, 3.60, 3.80, 4.0]

    print("[BSFC-MAP] Building grid ...")
    points: List[Dict[str, Any]] = []
    for N in speeds_rpm:
        for pint_bar in pint_bar_list:
            pt = _run_grid_point(cfg_base, N, pint_bar)
            points.append(pt)
            print(
                f"  N={N:6.1f} rpm  p_int={pint_bar:5.3f} bar  "
                f"BMEP={pt.get('bmep_bar')!r}  BSFC={pt.get('bsfc_g_per_kWh')!r}  "
                f"η_th={pt.get('eta_b_th')!r}"
            )

    # CSV of raw points
    csv_path = OUT_DIR / "bsfc_eta_grid_points.csv"
    _write_csv(points, csv_path)

    # Build grids & make contours
    grid = _build_grids(points)
    _plot_contours_bsfc(OUT_DIR / "bsfc_contour_speed_pint.html", grid)
    _plot_contours_eta(OUT_DIR / "eta_th_contour_speed_pint.html", grid)


if __name__ == "__main__":  # pragma: no cover
    main()
