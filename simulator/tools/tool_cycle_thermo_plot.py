
# simulator/tools/tool_cycle_thermo_plot.py

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def _get_array(d: dict, key: str) -> np.ndarray:
    if key not in d:
        raise KeyError(f"Key {key!r} not found in JSON.")
    return np.asarray(d[key], dtype=float)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Crank-angle resolved thermo plot (p(θ), T(θ)) from a simulator cycle JSON."
    )
    p.add_argument(
        "--infile",
        required=True,
        help="Path to a single simulator cycle output JSON.",
    )
    p.add_argument(
        "--out-html",
        required=True,
        help="Output HTML path for the Plotly figure.",
    )
    p.add_argument(
        "--theta-key",
        default="crank_deg",
        help="Key for crank angle array in degrees (default: crank_deg).",
    )
    p.add_argument(
        "--p-key",
        default="pressure_Pa",
        help="Key for cylinder pressure array [Pa] (default: pressure_Pa).",
    )
    p.add_argument(
        "--T-key",
        default="temperature_K",
        help=(
            "Key for gas temperature array [K] (default: temperature_K). "
            "If not present we will try to infer T from p, V, m, R if available."
        ),
    )
    p.add_argument(
        "--V-key",
        default="volume_m3",
        help="Key for cylinder volume array [m³] (used only if T must be inferred).",
    )
    p.add_argument(
        "--mass-key",
        default="mass_gas_kg",
        help="Key for total gas mass [kg] (scalar or array, used if T is inferred).",
    )
    p.add_argument(
        "--R-mix",
        type=float,
        default=287.0,
        help="Gas constant [J/kg-K] to use when inferring T (default: 287).",
    )
    return p.parse_args(argv)


def infer_temperature(
    data: dict,
    p: np.ndarray,
    V_key: str,
    mass_key: str,
    R_mix: float,
) -> np.ndarray:
    """If no temperature array is present, infer T from p V = m R T."""
    V = _get_array(data, V_key)

    if mass_key in data:
        m_raw = data[mass_key]
        if isinstance(m_raw, (list, tuple)):
            m_arr = np.asarray(m_raw, dtype=float)
            if m_arr.size == 1:
                m = float(m_arr[0])
            else:
                if m_arr.shape != p.shape:
                    raise ValueError("mass-key array shape does not match p array.")
                m = m_arr
        else:
            m = float(m_raw)
    else:
        raise KeyError(
            f"Temperature array missing and mass-key {mass_key!r} not found; "
            "cannot infer T."
        )

    T = p * V / (m * R_mix)
    return np.asarray(T, dtype=float)


def make_plot(theta: np.ndarray, p: np.ndarray, T: np.ndarray, out_html: Path) -> None:
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Scatter(
            x=theta,
            y=p / 1e5,  # show pressure in bar
            mode="lines",
            name="p_cyl [bar]",
        ),
        secondary_y=False,
    )

    fig.add_trace(
        go.Scatter(
            x=theta,
            y=T,
            mode="lines",
            name="T_gas [K]",
        ),
        secondary_y=True,
    )

    fig.update_xaxes(title_text="Crank angle θ [deg]")
    fig.update_yaxes(title_text="Cylinder pressure [bar]", secondary_y=False)
    fig.update_yaxes(title_text="Gas temperature [K]", secondary_y=True)

    fig.update_layout(
        title="Cycle thermo: p(θ) & T(θ)",
        template="plotly_white",
    )

    fig.write_html(str(out_html), include_plotlyjs="cdn")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    infile = Path(args.infile)
    out_html = Path(args.out_html)

    with infile.open() as f:
        data = json.load(f)

    theta = _get_array(data, args.theta_key)
    p = _get_array(data, args.p_key)

    # Try to get T directly; if missing, infer via pV = mRT
    if args.T_key in data:
        T = _get_array(data, args.T_key)
    else:
        T = infer_temperature(
            data=data,
            p=p,
            V_key=args.V_key,
            mass_key=args.mass_key,
            R_mix=float(args.R_mix),
        )

    make_plot(theta, p, T, out_html)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
