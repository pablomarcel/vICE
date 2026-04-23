from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import numpy as np
import plotly.graph_objects as go

from simulator.fuels import get_fuel
from simulator.thermo.equilibrium import ideal_adiabatic_flame
from simulator.thermo.thermo_state import ThermoState


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Sweep equivalence ratio and compute adiabatic flame "
            "temperature using either the 'ideal' or 'cantera' backend."
        )
    )
    p.add_argument(
        "--fuel-id",
        default="gasoline",
        help="Fuel ID as understood by simulator.fuels (default: gasoline).",
    )
    p.add_argument(
        "--backend",
        choices=["ideal", "cantera"],
        default="ideal",
        help="Thermochemistry backend: 'ideal' (LHV + cp) or 'cantera'.",
    )
    p.add_argument(
        "--mech",
        default="gri30.yaml",
        help="Cantera mechanism YAML file (backend='cantera'). "
             "Default: gri30.yaml",
    )
    p.add_argument(
        "--fuel-species",
        default=None,
        help="Cantera fuel species name (e.g. 'CH4') for backend='cantera'. "
             "Required when backend='cantera'.",
    )
    p.add_argument(
        "--phi-start",
        type=float,
        default=0.6,
        help="Start equivalence ratio φ (default: 0.6).",
    )
    p.add_argument(
        "--phi-stop",
        type=float,
        default=1.4,
        help="Stop equivalence ratio φ (default: 1.4).",
    )
    p.add_argument(
        "--phi-step",
        type=float,
        default=0.05,
        help="Step in equivalence ratio φ (default: 0.05).",
    )
    p.add_argument(
        "--pressure-Pa",
        type=float,
        default=101_325.0,
        help="Cylinder pressure during combustion [Pa] (default: 101325).",
    )
    p.add_argument(
        "--Tin-K",
        type=float,
        default=298.15,
        help="Unburned-gas temperature before combustion [K] (default: 298.15).",
    )
    p.add_argument(
        "--out-json",
        required=True,
        help="Output JSON file for the φ-sweep table.",
    )
    p.add_argument(
        "--out-html",
        required=False,
        help="Optional Plotly HTML output with T_ad vs φ plot.",
    )
    return p


def run_sweep(
    fuel_id: str,
    backend: str,
    mech: str,
    fuel_species: str | None,
    phi_start: float,
    phi_stop: float,
    phi_step: float,
    p_cyl: float,
    Tin: float,
    out_json: Path,
    out_html: Path | None,
) -> None:
    # For 'ideal' backend we still use simulator.fuels to get afr_stoich.
    fuel = get_fuel(fuel_id)

    phis: List[float] = []
    Tad: List[float] = []
    gammas: List[float] = []
    cps: List[float] = []
    Rmix: List[float] = []

    rows: List[Dict] = []

    phi_values = np.arange(phi_start, phi_stop + 0.5 * phi_step, phi_step)

    for phi in phi_values:
        phi = float(phi)
        res = ideal_adiabatic_flame(
            fuel_name=fuel_id,
            phi=phi,
            p=p_cyl,
            T_intake=Tin,
            afr_stoich=fuel.afr_stoich,
            backend=backend,          # 'ideal' or 'cantera'
            mechanism=mech,
            fuel_species=fuel_species,
        )
        st: ThermoState = res.burned_state

        phis.append(phi)
        Tad.append(res.T_ad)
        gammas.append(st.gamma)
        cps.append(st.cp)
        Rmix.append(st.R_mix)

        rows.append(
            {
                "phi": phi,
                "T_ad_K": res.T_ad,
                "pressure_Pa": res.p,
                "gamma": st.gamma,
                "cp_J_per_kgK": st.cp,
                "R_mix_J_per_kgK": st.R_mix,
                "rho_kg_per_m3": st.rho,
                "mass_fractions": st.mass_fractions,
            }
        )

    # JSON table
    out_json.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "fuel_id": fuel_id,
        "backend": backend,
        "mechanism": mech if backend == "cantera" else None,
        "fuel_species": fuel_species if backend == "cantera" else None,
        "pressure_Pa": p_cyl,
        "Tin_K": Tin,
        "afr_stoich": fuel.afr_stoich,
        "rows": rows,
    }
    out_json.write_text(json.dumps(data, indent=2))

    # Optional Plotly HTML
    if out_html is not None:
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=phis,
                y=Tad,
                mode="lines+markers",
                name=f"T_ad ({backend})",
            )
        )
        fig.update_layout(
            title=(
                f"Adiabatic flame temperature vs equivalence ratio "
                f"(fuel_id={fuel_id}, backend={backend})"
            ),
            xaxis_title="Equivalence ratio, φ",
            yaxis_title="Adiabatic flame temperature T_ad [K]",
        )
        out_html.parent.mkdir(parents=True, exist_ok=True)
        fig.write_html(str(out_html), include_plotlyjs="cdn")


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.backend == "cantera" and args.fuel_species is None:
        parser.error(
            "backend='cantera' requires --fuel-species, e.g. "
            "--fuel-species CH4 for gri30.yaml."
        )

    out_json = Path(args.out_json)
    out_html = Path(args.out_html) if args.out_html else None

    run_sweep(
        fuel_id=args.fuel_id,
        backend=args.backend,
        mech=args.mech,
        fuel_species=args.fuel_species,
        phi_start=args.phi_start,
        phi_stop=args.phi_stop,
        phi_step=args.phi_step,
        p_cyl=args.pressure_Pa,
        Tin=args.Tin_K,
        out_json=out_json,
        out_html=out_html,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
