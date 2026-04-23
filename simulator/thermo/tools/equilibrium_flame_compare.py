# simulator/thermo/tools/equilibrium_flame_compare.py

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import numpy as np
import plotly.graph_objects as go

from simulator.fuels import get_fuel
from simulator.thermo.equilibrium import ideal_adiabatic_flame, BackendType


@dataclass
class FlameCurve:
    fuel_id: str
    backend: BackendType
    mechanism: str | None
    fuel_species: str | None
    phi: np.ndarray
    T_ad: np.ndarray  # [K]


def sweep_flame_curve(
    fuel_id: str,
    backend: BackendType,
    phi_vals: np.ndarray,
    p: float,
    Tin: float,
    mechanism: str | None = None,
    fuel_species: str | None = None,
) -> FlameCurve:
    """Compute T_ad(φ) for one fuel / backend combination.

    Notes
    -----
    - For backend="ideal" or "legacy", fuel_id must exist in simulator.fuels.
    - For backend="cantera", fuel_id is only used as a *label* in the plot;
      the actual thermo comes from the Cantera mechanism / fuel_species.
    """
    if backend in ("ideal", "legacy"):
        fuel = get_fuel(fuel_id)
        afr_st = fuel.afr_stoich
    else:
        # backend == "cantera": afr_st is irrelevant for the HP backend.
        afr_st = 1.0

    T_list: List[float] = []

    for phi in phi_vals:
        res = ideal_adiabatic_flame(
            fuel_name=fuel_id,
            phi=float(phi),
            p=p,
            T_intake=Tin,
            afr_stoich=afr_st,
            backend=backend,
            mechanism=mechanism,
            fuel_species=fuel_species,
        )
        T_list.append(res.T_ad)

    return FlameCurve(
        fuel_id=fuel_id,
        backend=backend,
        mechanism=mechanism,
        fuel_species=fuel_species,
        phi=phi_vals,
        T_ad=np.asarray(T_list, dtype=float),
    )


def make_plot(
    curves: List[FlameCurve],
    out_html: Path | None,
    title_suffix: str = "",
) -> go.Figure:
    fig = go.Figure()
    for curve in curves:
        label = curve.fuel_id
        if curve.backend == "cantera" and curve.fuel_species:
            label += f" (CT {curve.fuel_species})"
        fig.add_trace(
            go.Scatter(
                x=curve.phi,
                y=curve.T_ad,
                mode="lines+markers",
                name=label,
            )
        )

    fig.update_layout(
        title=(
            "Adiabatic flame temperature vs equivalence ratio"
            + (f" {title_suffix}" if title_suffix else "")
        ),
        xaxis_title="Equivalence ratio, φ",
        yaxis_title="Adiabatic flame temperature T_ad [K]",
        template="plotly_white",
    )

    if out_html is not None:
        fig.write_html(str(out_html), include_plotlyjs="cdn")

    return fig


def write_json(curves: List[FlameCurve], out_json: Path | None) -> None:
    if out_json is None:
        return
    data: Dict[str, Dict[str, object]] = {}
    for c in curves:
        data[c.fuel_id] = {
            "backend": c.backend,
            "mechanism": c.mechanism,
            "fuel_species": c.fuel_species,
            "phi": c.phi.tolist(),
            "T_ad_K": c.T_ad.tolist(),
        }
    out_json.write_text(json.dumps(data, indent=2))


def _extract_species_names_from_comp(comp: str) -> List[str]:
    """Given a Cantera composition string, return the list of species names.

    Examples
    --------
    'CH4'                -> ['CH4']
    'CH4:1.0'            -> ['CH4']
    'CH4:0.7,C3H8:0.3'   -> ['CH4', 'C3H8']
    """
    names: List[str] = []
    for token in comp.split(","):
        token = token.strip()
        if not token:
            continue
        if ":" in token:
            name, _ = token.split(":", 1)
        else:
            name = token
        names.append(name.strip())
    return names


def _validate_cantera_fuels(
    mechanism: str,
    fuel_species_map: Dict[str, str | None],
) -> None:
    """Ensure all requested fuel species exist in the Cantera mechanism."""

    import cantera as ct  # local import to keep ideal backend light

    gas = ct.Solution(mechanism)
    available = set(gas.species_names)

    for fuel_id, comp in fuel_species_map.items():
        if comp is None:
            raise SystemExit(
                f"backend=cantera: no fuel species specified for fuel-id {fuel_id!r}. "
                f"Use --fuel-species to map fuel-ids to mechanism species names."
            )
        for sp_name in _extract_species_names_from_comp(comp):
            if sp_name not in available:
                # Give a short preview of available species to help debugging.
                preview = ", ".join(sorted(list(available))[:10])
                raise SystemExit(
                    f"Fuel species {sp_name!r} (from fuel-id {fuel_id!r}) is not present "
                    f"in mechanism {mechanism!r}.\n"
                    f"Example species in this mechanism: {preview} ..."
                )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Compare adiabatic flame temperature vs φ for several fuels."
    )
    p.add_argument(
        "--fuel-ids",
        required=True,
        help=(
            "Comma-separated list of fuel IDs for simulator.fuels "
            "(e.g. 'gasoline,methanol,e85' or just 'methane'). "
            "For backend=cantera these are only used as labels."
        ),
    )
    p.add_argument(
        "--backend",
        choices=["ideal", "cantera", "legacy"],
        default="ideal",
        help="Backend for equilibrium calculation (default: ideal).",
    )
    p.add_argument(
        "--mech",
        dest="mechanism",
        default="gri30.yaml",
        help="Cantera mechanism file (for backend=cantera).",
    )
    p.add_argument(
        "--fuel-species",
        default=None,
        help=(
            "Comma-separated list of Cantera fuel composition strings corresponding to "
            "fuel-ids (for backend=cantera). Example: 'CH4,C3H8' or "
            "'CH4:0.7,C3H8:0.3'. If omitted and only one fuel-id is given, that "
            "species name is assumed to match the fuel-id exactly."
        ),
    )
    p.add_argument("--phi-start", type=float, default=0.6)
    p.add_argument("--phi-stop", type=float, default=1.4)
    p.add_argument("--phi-step", type=float, default=0.05)
    p.add_argument("--pressure-Pa", type=float, default=101325.0)
    p.add_argument("--Tin-K", type=float, default=298.15)
    p.add_argument("--out-json", type=str, default=None)
    p.add_argument("--out-html", type=str, default=None)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    fuel_ids = [s.strip() for s in args.fuel_ids.split(",") if s.strip()]
    if not fuel_ids:
        raise SystemExit("No valid fuel IDs supplied in --fuel-ids.")

    backend: BackendType = args.backend  # type: ignore[assignment]

    phi_vals = np.arange(args.phi_start, args.phi_stop + 1e-9, args.phi_step)
    p = float(args.pressure_Pa)
    Tin = float(args.Tin_K)

    # Map fuel_ids -> fuel_species (only relevant for Cantera backend)
    fuel_species_map: Dict[str, str | None] = {fid: None for fid in fuel_ids}
    if backend == "cantera":
        if args.fuel_species is None:
            if len(fuel_ids) == 1:
                fuel_species_map[fuel_ids[0]] = fuel_ids[0]
            else:
                raise SystemExit(
                    "backend=cantera with multiple fuels requires --fuel-species "
                    "to map fuel-ids to mechanism species names."
                )
        else:
            species_list = [s.strip() for s in args.fuel_species.split(",") if s.strip()]
            if len(species_list) != len(fuel_ids):
                raise SystemExit(
                    "Length of --fuel-species list must match --fuel-ids list "
                    "for backend=cantera."
                )
            for fid, sp in zip(fuel_ids, species_list):
                fuel_species_map[fid] = sp

        # New: validate that all requested species really exist in the mechanism.
        _validate_cantera_fuels(args.mechanism, fuel_species_map)

    curves: List[FlameCurve] = []
    for fid in fuel_ids:
        sp_name = fuel_species_map[fid]
        curve = sweep_flame_curve(
            fuel_id=fid,
            backend=backend,
            phi_vals=phi_vals,
            p=p,
            Tin=Tin,
            mechanism=args.mechanism if backend == "cantera" else None,
            fuel_species=sp_name,
        )
        curves.append(curve)

    out_json = Path(args.out_json) if args.out_json else None
    out_html = Path(args.out_html) if args.out_html else None

    title_suffix = f"(backend={backend}"
    if backend == "cantera":
        title_suffix += f", mech={args.mechanism}"
    title_suffix += ")"

    make_plot(curves, out_html=out_html, title_suffix=title_suffix)
    write_json(curves, out_json=out_json)

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
