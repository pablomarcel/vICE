from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from simulator.fuels import get_fuel
from simulator.thermo.equilibrium import ideal_adiabatic_flame, BackendType


@dataclass
class FlameSummaryRow:
    filename: str
    N_rpm: float
    phi: float
    T_ad: float
    bsfc_g_per_kWh: Optional[float]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_float(
    d: Dict[str, Any],
    keys: List[str],
    default: float | None = None,
) -> float:
    """Try a sequence of keys in a dict and return the first float value.

    If none of the keys is found and default is not None, the default is
    returned. Otherwise a KeyError is raised.
    """
    for k in keys:
        if k in d and d[k] is not None:
            return float(d[k])
    if default is not None:
        return float(default)
    raise KeyError(f"None of keys {keys} found in JSON and no default provided.")


def _speed_from_filename(path: Path) -> float:
    """Fallback: parse engine speed from filenames like full_load_N_00500.json."""
    import re

    m = re.search(r"_N_(\d+)", path.name)
    if not m:
        raise KeyError(
            "Engine speed not found in JSON and filename does not match "
            f"'*_N_XXXX.json': {path.name!r}"
        )
    return float(m.group(1))


# ---------------------------------------------------------------------------
# Main data collection
# ---------------------------------------------------------------------------

def collect_rows(
    pattern: str,
    fuel_id: str,
    backend: BackendType,
    pressure_Pa: float,
    Tin_K: float,
    mechanism: str | None = None,
    fuel_species: str | None = None,
) -> List[FlameSummaryRow]:
    """Walk dyno-style JSON outputs and attach a T_ad to each point.

    pattern is a glob pattern, e.g. 'simulator/out/full_load_N_*.json'.
    """
    fuel = get_fuel(fuel_id)
    afr_st = fuel.afr_stoich

    rows: List[FlameSummaryRow] = []

    # Note: Path() is the current working directory;
    # runroot already puts you at repo root so the pattern is fine.
    for path in sorted(Path().glob(pattern)):
        if not path.is_file():
            continue

        with path.open() as f:
            data = json.load(f)

        # --- Engine speed ---
        # Try to read from JSON; fall back to filename full_load_N_XXXXX.json.
        try:
            N_rpm = _extract_float(
                data,
                ["N_rpm", "speed_rpm", "engine_speed_rpm", "N_engine_rpm"],
                default=None,
            )
        except KeyError:
            N_rpm = _speed_from_filename(path)

        # --- Equivalence ratio φ ---
        # Prefer direct key; otherwise derive from lambda.
        try:
            phi = _extract_float(data, ["equivalence_ratio", "phi"], default=None)
        except KeyError:
            try:
                lam = _extract_float(data, ["lambda_value", "lambda"], default=None)
            except KeyError:
                raise KeyError(
                    f"Could not find equivalence ratio or lambda in {path.name!r}."
                )
            phi = 1.0 / lam

        # --- BSFC (if present) ---
        try:
            bsfc = _extract_float(
                data,
                ["bsfc_g_per_kWh", "bsfc", "BSFC_g_per_kWh"],
                default=None,
            )
        except KeyError:
            bsfc = None

        # --- Flame temperature using selected backend ---
        res = ideal_adiabatic_flame(
            fuel_name=fuel_id,
            phi=phi,
            p=pressure_Pa,
            T_intake=Tin_K,
            afr_stoich=afr_st,
            backend=backend,
            mechanism=mechanism,
            fuel_species=fuel_species,
        )

        rows.append(
            FlameSummaryRow(
                filename=path.name,
                N_rpm=N_rpm,
                phi=phi,
                T_ad=res.T_ad,
                bsfc_g_per_kWh=bsfc,
            )
        )

    return rows


# ---------------------------------------------------------------------------
# Output: CSV + Plotly
# ---------------------------------------------------------------------------

def write_csv(rows: List[FlameSummaryRow], out_csv: Path) -> None:
    with out_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["filename", "N_rpm", "phi", "T_ad_K", "bsfc_g_per_kWh"])
        for r in rows:
            w.writerow(
                [
                    r.filename,
                    f"{r.N_rpm:.1f}",
                    f"{r.phi:.4f}",
                    f"{r.T_ad:.2f}",
                    "" if r.bsfc_g_per_kWh is None else f"{r.bsfc_g_per_kWh:.2f}",
                ]
            )


def make_plot(
    rows: List[FlameSummaryRow],
    out_html: Path | None,
    backend: BackendType,
    fuel_id: str,
) -> go.Figure:
    """Plot BSFC vs N (primary y-axis) and T_ad vs N (secondary y-axis).

    For your current full-load sweeps at fixed φ, T_ad is expected to be
    almost constant vs speed (ideal backend has no speed dependence).
    BSFC, however, varies strongly with N.
    """
    if not rows:
        fig = go.Figure()
        fig.update_layout(
            title="No data rows collected",
            template="plotly_white",
        )
        if out_html is not None:
            fig.write_html(str(out_html), include_plotlyjs="cdn")
        return fig

    N = [r.N_rpm for r in rows]
    T_ad = [r.T_ad for r in rows]
    bsfc_vals = [r.bsfc_g_per_kWh for r in rows]

    any_bsfc = any(v is not None for v in bsfc_vals)

    if any_bsfc:
        # Use dual y-axis: BSFC on left, T_ad on right.
        fig = make_subplots(specs=[[{"secondary_y": True}]])

        fig.add_trace(
            go.Scatter(
                x=N,
                y=[v if v is not None else None for v in bsfc_vals],
                mode="lines+markers",
                name="BSFC [g/kWh]",
            ),
            secondary_y=False,
        )

        fig.add_trace(
            go.Scatter(
                x=N,
                y=T_ad,
                mode="lines+markers",
                name="T_ad [K]",
            ),
            secondary_y=True,
        )

        fig.update_xaxes(title_text="Engine speed N [rpm]")
        fig.update_yaxes(title_text="BSFC [g/kWh]", secondary_y=False)
        fig.update_yaxes(title_text="Adiabatic flame temperature T_ad [K]", secondary_y=True)

        fig.update_layout(
            title=f"Flame summary vs speed (fuel={fuel_id}, backend={backend})",
            template="plotly_white",
        )
    else:
        # Fallback: only T_ad vs N.
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=N,
                y=T_ad,
                mode="lines+markers",
                name="T_ad [K]",
            )
        )
        fig.update_layout(
            title=f"Flame summary vs speed (fuel={fuel_id}, backend={backend})",
            xaxis_title="Engine speed N [rpm]",
            yaxis_title="Adiabatic flame temperature T_ad [K]",
            template="plotly_white",
        )

    if out_html is not None:
        fig.write_html(str(out_html), include_plotlyjs="cdn")

    return fig


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Summarise adiabatic flame temperature across dyno outputs."
    )
    p.add_argument(
        "--pattern",
        required=True,
        help="Glob pattern for JSON files, e.g. 'simulator/out/full_load_N_*.json'",
    )
    p.add_argument(
        "--fuel-id",
        required=True,
        help="Fuel ID as in simulator.fuels (e.g. gasoline, methanol, e85, methane).",
    )
    p.add_argument(
        "--backend",
        choices=["ideal", "cantera", "legacy"],
        default="ideal",
    )
    p.add_argument(
        "--mech",
        dest="mechanism",
        default="gri30.yaml",
        help="Cantera mechanism (backend=cantera).",
    )
    p.add_argument(
        "--fuel-species",
        default=None,
        help="Fuel species name in Cantera mechanism (backend=cantera).",
    )
    p.add_argument("--pressure-Pa", type=float, default=101325.0)
    p.add_argument("--Tin-K", type=float, default=298.15)
    p.add_argument("--out-csv", type=str, required=True)
    p.add_argument("--out-html", type=str, required=True)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    backend: BackendType = args.backend  # type: ignore[assignment]

    rows = collect_rows(
        pattern=args.pattern,
        fuel_id=args.fuel_id,
        backend=backend,
        pressure_Pa=float(args.pressure_Pa),
        Tin_K=float(args.Tin_K),
        mechanism=args.mechanism if backend == "cantera" else None,
        fuel_species=args.fuel_species,
    )

    out_csv = Path(args.out_csv)
    out_html = Path(args.out_html)

    write_csv(rows, out_csv)
    make_plot(rows, out_html, backend=backend, fuel_id=args.fuel_id)

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
