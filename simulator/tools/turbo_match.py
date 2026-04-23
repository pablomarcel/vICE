from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

import json
import plotly.graph_objects as go
import numpy as np

from simulator.turbo import match_turbo_over_speeds


def _parse_speeds(args: argparse.Namespace) -> List[float]:
    if args.speeds:
        return [float(v) for v in args.speeds]
    # Fallback: simple generic dyno sweep
    return [
        1000, 1500, 2000, 2500, 3000, 3500,
        4000, 4500, 5000, 5500, 6000, 6500,
    ]


def _make_match_plot(
    result: dict,
    out_html: Path | None,
) -> None:
    points = result["points"]
    if not points:
        return

    N = np.array([p["speed_rpm"] for p in points], dtype=float)
    na_trq = np.array([p.get("na_torque_Nm") for p in points], dtype=float)
    tb_trq = np.array([p.get("tb_torque_Nm") for p in points], dtype=float)
    na_bsfc = np.array([p.get("na_bsfc_g_per_kWh") for p in points], dtype=float)
    tb_bsfc = np.array([p.get("tb_bsfc_g_per_kWh") for p in points], dtype=float)
    pr_c = np.array([p.get("pr_c") for p in points], dtype=float)
    p_int_bar = np.array([p.get("p_int_bar") for p in points], dtype=float)

    fig = go.Figure()

    # Torque – NA vs turbo
    fig.add_trace(
        go.Scatter(
            x=N,
            y=na_trq,
            mode="lines+markers",
            name="Torque NA [Nm]",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=N,
            y=tb_trq,
            mode="lines+markers",
            name="Torque Turbo [Nm]",
        )
    )

    # Secondary y‑axis: manifold pressure
    fig.add_trace(
        go.Scatter(
            x=N,
            y=p_int_bar,
            mode="lines+markers",
            name="p_int turbo [bar]",
            yaxis="y2",
        )
    )

    fig.update_layout(
        title="Turbo match – Torque & Manifold Pressure vs Speed",
        xaxis=dict(title="Speed [rpm]"),
        yaxis=dict(title="Torque [Nm]"),
        yaxis2=dict(
            title="Intake manifold pressure [bar abs]",
            overlaying="y",
            side="right",
        ),
        legend=dict(x=0.02, y=0.98),
    )

    # BSFC figure
    fig_bsfc = go.Figure()
    fig_bsfc.add_trace(
        go.Scatter(
            x=N,
            y=na_bsfc,
            mode="lines+markers",
            name="BSFC NA [g/kWh]",
        )
    )
    fig_bsfc.add_trace(
        go.Scatter(
            x=N,
            y=tb_bsfc,
            mode="lines+markers",
            name="BSFC Turbo [g/kWh]",
        )
    )
    fig_bsfc.update_layout(
        title="Turbo match – BSFC vs Speed",
        xaxis=dict(title="Speed [rpm]"),
        yaxis=dict(title="BSFC [g/kWh]"),
    )

    if out_html is not None:
        out_html.parent.mkdir(parents=True, exist_ok=True)
        # Combine as two separate figures in one HTML by simple concatenation
        html_path = str(out_html)
        fig.write_html(html_path, include_plotlyjs="cdn")
        # Append BSFC figure (Plotly includes its JS once via CDN)
        with open(html_path, "a", encoding="utf-8") as f:
            f.write("\n<!-- BSFC figure -->\n")
            f.write(fig_bsfc.to_html(full_html=False, include_plotlyjs=False))


def _make_compressor_opline_plot(
    result: dict,
    out_html: Path | None,
) -> None:
    if out_html is None:
        return
    points = result["points"]
    if not points:
        return

    N = np.array([p["speed_rpm"] for p in points], dtype=float)
    m_corr = np.array([p.get("m_dot_corr_kg_per_s") for p in points], dtype=float)
    pr_c = np.array([p.get("pr_c") for p in points], dtype=float)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=m_corr,
            y=pr_c,
            mode="markers+lines",
            marker=dict(
                size=8,
                color=N,
                colorscale="Viridis",
                showscale=True,
                colorbar=dict(title="Speed [rpm]"),
            ),
            name="Operating line",
        )
    )
    fig.update_layout(
        title="Compressor operating line (no background map yet)",
        xaxis=dict(title="Corrected air mass flow [kg/s]"),
        yaxis=dict(title="Compressor pressure ratio PR"),
    )
    out_html.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(out_html), include_plotlyjs="cdn")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="simulator-turbo-match",
        description=(
            "Steady‑state turbo match over a speed sweep, comparing NA vs "
            "turbocharged operation and producing plots."
        ),
    )
    p.add_argument(
        "--config",
        required=True,
        help="Path to engine JSON config (geometry + operating + optional turbo block).",
    )
    p.add_argument(
        "--speeds",
        nargs="+",
        type=float,
        help="List of engine speeds [rpm]. If omitted, a default dyno sweep is used.",
    )
    p.add_argument(
        "--out-json",
        type=str,
        required=True,
        help="Output JSON file with turbo match table.",
    )
    p.add_argument(
        "--out-html",
        type=str,
        help="Output HTML file for torque/BSFC plots.",
    )
    p.add_argument(
        "--out-compressor-html",
        type=str,
        help="Output HTML file for compressor operating line plot.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    speeds = _parse_speeds(args)
    result = match_turbo_over_speeds(
        base_cfg_path=args.config,
        speeds_rpm=speeds,
        compare_na=True,
    )

    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2))

    out_html = Path(args.out_html) if args.out_html else None
    _make_match_plot(result, out_html=out_html)

    out_comp_html = Path(args.out_compressor_html) if args.out_compressor_html else None
    _make_compressor_opline_plot(result, out_html=out_comp_html)

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
