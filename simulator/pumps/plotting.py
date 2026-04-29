from __future__ import annotations

"""Plotting/export helpers for vICE pump analysis.

This module intentionally keeps Plotly and Matplotlib imports lazy so the pump
solvers, Sphinx autodoc, and lightweight CLI commands remain usable even when
optional plotting dependencies are not installed.

The plotting layer covers three common engineering views:

* rich supplier/textbook pump-family maps with impeller curves, efficiency
  contours, brake-horsepower guides, and NPSH information;
* single operating-point overlays showing pump curve, system curve, and the
  solved intersection;
* RPM-sweep dashboards showing flow, head, power, BEP ratio, and NPSH margin
  against engine speed;
* speed-family overlays similar to Frank White Fig. 11.9(a), where a
  fixed-size pump curve is shifted to several shaft speeds using affinity laws
  and optionally intersected with a system curve.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
import json
import math

from .combined import match_combined_system
from .curves import Curve1D
from .pump_map import DigitizedPumpFamilyMap, load_pump_family_json
from .system_curve import QuadraticSystemCurve
from .water_pump import CentrifugalWaterPump, load_system_json, match_system
from .cavitation import SuctionState


@dataclass(frozen=True)
class PlotExportResult:
    """Paths written by a plotting/export command."""

    html: str | None = None
    image: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {"html": self.html, "image": self.image}


# ---------------------------------------------------------------------------
# Public writer helpers
# ---------------------------------------------------------------------------

def write_pump_family_plot(
    map_path: str | Path,
    *,
    out_html: str | Path | None = None,
    out_image: str | Path | None = None,
    title: str | None = None,
    include_efficiency: bool = True,
    include_power: bool = True,
    include_npsh: bool = True,
    width: int = 1100,
    height: int = 760,
    dpi: int = 160,
) -> PlotExportResult:
    """Write a pump-family map plot to Plotly HTML and/or Matplotlib image.

    Parameters
    ----------
    map_path:
        Path to a rich pump-family JSON file, for example ``figure_11_7_a.json``
        or a supplier-style chart digitization.
    out_html:
        Optional Plotly HTML output path.
    out_image:
        Optional static image path written by Matplotlib. File extension controls
        the format, e.g. ``.png``, ``.svg``, or ``.pdf``.
    title:
        Optional plot title. Defaults to the map name.
    include_efficiency, include_power, include_npsh:
        Toggle contour/guide layers.
    width, height:
        Plotly layout size.
    dpi:
        Matplotlib image DPI.
    """
    family = load_pump_family_json(map_path)
    html_written: str | None = None
    image_written: str | None = None

    if out_html:
        fig = pump_family_figure_plotly(
            family,
            title=title,
            include_efficiency=include_efficiency,
            include_power=include_power,
            include_npsh=include_npsh,
            width=width,
            height=height,
        )
        html_path = _ensure_parent(out_html)
        fig.write_html(str(html_path), include_plotlyjs="cdn", full_html=True)
        html_written = str(html_path)

    if out_image:
        image_path = _ensure_parent(out_image)
        fig_mpl = pump_family_figure_matplotlib(
            family,
            title=title,
            include_efficiency=include_efficiency,
            include_power=include_power,
            include_npsh=include_npsh,
        )
        fig_mpl.savefig(str(image_path), dpi=dpi, bbox_inches="tight")
        _close_matplotlib(fig_mpl)
        image_written = str(image_path)

    if not out_html and not out_image:
        raise ValueError("At least one output path is required: out_html or out_image")

    return PlotExportResult(html=html_written, image=image_written)


def write_operating_point_plot(
    pump_path: str | Path,
    system_path: str | Path,
    *,
    pump_rpm: float,
    result_json: str | Path | None = None,
    out_html: str | Path | None = None,
    out_image: str | Path | None = None,
    arrangement: str = "single",
    number_of_pumps: int = 1,
    engine_rpm: float | None = None,
    npsh_margin_required_ft: float = 3.0,
    title: str | None = None,
    samples: int = 300,
    dpi: int = 160,
) -> PlotExportResult:
    """Plot pump curve, system curve, and operating point.

    The function can either read an existing result JSON or recompute the point
    from ``pump_path`` and ``system_path``. ``arrangement`` may be ``single``,
    ``parallel``, or ``series``.
    """
    pump = CentrifugalWaterPump.from_json(pump_path)
    system_data = load_system_json(system_path)
    system = QuadraticSystemCurve.from_dict(system_data)
    suction = SuctionState.from_dict(system_data.get("suction"))
    mode = arrangement.strip().lower()

    if result_json:
        payload = _read_json(result_json)
        point = _extract_point_from_payload(payload)
    elif mode in {"parallel", "series"}:
        point = match_combined_system(
            pump,
            system,
            pump_rpm,
            arrangement=mode,
            number_of_pumps=number_of_pumps,
            suction=suction,
            engine_speed_rpm=engine_rpm,
            npsh_margin_required_ft=npsh_margin_required_ft,
        ).to_dict()
    else:
        point = match_system(
            pump,
            system,
            pump_rpm,
            suction=suction,
            engine_speed_rpm=engine_rpm,
            npsh_margin_required_ft=npsh_margin_required_ft,
        ).to_dict()

    html_written: str | None = None
    image_written: str | None = None

    if out_html:
        fig = operating_point_figure_plotly(
            pump,
            system,
            point,
            pump_rpm=pump_rpm,
            arrangement=mode,
            number_of_pumps=number_of_pumps,
            title=title,
            samples=samples,
        )
        html_path = _ensure_parent(out_html)
        fig.write_html(str(html_path), include_plotlyjs="cdn", full_html=True)
        html_written = str(html_path)

    if out_image:
        fig_mpl = operating_point_figure_matplotlib(
            pump,
            system,
            point,
            pump_rpm=pump_rpm,
            arrangement=mode,
            number_of_pumps=number_of_pumps,
            title=title,
            samples=samples,
        )
        image_path = _ensure_parent(out_image)
        fig_mpl.savefig(str(image_path), dpi=dpi, bbox_inches="tight")
        _close_matplotlib(fig_mpl)
        image_written = str(image_path)

    if not out_html and not out_image:
        raise ValueError("At least one output path is required: out_html or out_image")

    return PlotExportResult(html=html_written, image=image_written)


def write_sweep_plot(
    result_json: str | Path,
    *,
    out_html: str | Path | None = None,
    out_image: str | Path | None = None,
    title: str | None = None,
    dpi: int = 160,
) -> PlotExportResult:
    """Write a dashboard plot for a ``pump_rpm_sweep`` result JSON."""
    payload = _read_json(result_json)
    points = payload.get("points", [])
    if not isinstance(points, list) or not points:
        raise ValueError("Sweep result JSON must contain a non-empty 'points' list")

    html_written: str | None = None
    image_written: str | None = None

    if out_html:
        fig = sweep_figure_plotly(payload, title=title)
        html_path = _ensure_parent(out_html)
        fig.write_html(str(html_path), include_plotlyjs="cdn", full_html=True)
        html_written = str(html_path)

    if out_image:
        fig_mpl = sweep_figure_matplotlib(payload, title=title)
        image_path = _ensure_parent(out_image)
        fig_mpl.savefig(str(image_path), dpi=dpi, bbox_inches="tight")
        _close_matplotlib(fig_mpl)
        image_written = str(image_path)

    if not out_html and not out_image:
        raise ValueError("At least one output path is required: out_html or out_image")

    return PlotExportResult(html=html_written, image=image_written)



def write_speed_family_plot(
    pump_path: str | Path,
    *,
    speeds_rpm: Sequence[float],
    system_path: str | Path | None = None,
    out_html: str | Path | None = None,
    out_image: str | Path | None = None,
    title: str | None = None,
    samples: int = 300,
    include_system: bool = True,
    include_operating_points: bool = True,
    include_bep_locus: bool = True,
    npsh_margin_required_ft: float = 3.0,
    width: int = 1100,
    height: int = 760,
    dpi: int = 160,
) -> PlotExportResult:
    """Write a shaft-speed family plot for a fixed-size centrifugal pump.

    This is the computational analog of Frank White Fig. 11.9(a): the impeller
    diameter is held fixed while shaft speed is varied. Head curves are shifted
    using the affinity rules, so flow scales with ``N`` and head scales with
    ``N^2``. If a system curve is supplied, operating points are solved and
    overlaid for each speed.

    Parameters
    ----------
    pump_path:
        Path to a single-pump JSON curve file.
    speeds_rpm:
        Shaft speeds to plot [rpm]. These are pump speeds, not engine speeds.
    system_path:
        Optional system-curve JSON. When provided, the system curve and solved
        operating points can be shown on the same axes.
    include_bep_locus:
        If the pump JSON defines ``bep_flow`` and ``bep_head``, draw the scaled
        BEP locus ``Q_BEP ~ N`` and ``H_BEP ~ N^2``.
    """
    pump = CentrifugalWaterPump.from_json(pump_path)
    speeds = _clean_speeds(speeds_rpm)
    system: QuadraticSystemCurve | None = None
    suction: SuctionState | None = None
    if system_path is not None:
        system_data = load_system_json(system_path)
        system = QuadraticSystemCurve.from_dict(system_data)
        suction = SuctionState.from_dict(system_data.get("suction"))

    html_written: str | None = None
    image_written: str | None = None

    if out_html:
        fig = speed_family_figure_plotly(
            pump,
            speeds,
            system=system,
            suction=suction,
            title=title,
            samples=samples,
            include_system=include_system,
            include_operating_points=include_operating_points,
            include_bep_locus=include_bep_locus,
            npsh_margin_required_ft=npsh_margin_required_ft,
            width=width,
            height=height,
        )
        html_path = _ensure_parent(out_html)
        fig.write_html(str(html_path), include_plotlyjs="cdn", full_html=True)
        html_written = str(html_path)

    if out_image:
        fig_mpl = speed_family_figure_matplotlib(
            pump,
            speeds,
            system=system,
            suction=suction,
            title=title,
            samples=samples,
            include_system=include_system,
            include_operating_points=include_operating_points,
            include_bep_locus=include_bep_locus,
            npsh_margin_required_ft=npsh_margin_required_ft,
        )
        image_path = _ensure_parent(out_image)
        fig_mpl.savefig(str(image_path), dpi=dpi, bbox_inches="tight")
        _close_matplotlib(fig_mpl)
        image_written = str(image_path)

    if not out_html and not out_image:
        raise ValueError("At least one output path is required: out_html or out_image")

    return PlotExportResult(html=html_written, image=image_written)


# ---------------------------------------------------------------------------
# Plotly figure factories
# ---------------------------------------------------------------------------

def pump_family_figure_plotly(
    family: DigitizedPumpFamilyMap,
    *,
    title: str | None = None,
    include_efficiency: bool = True,
    include_power: bool = True,
    include_npsh: bool = True,
    width: int = 1100,
    height: int = 760,
):
    """Return a Plotly figure for a rich pump-family map."""
    go = _require_plotly()
    fig = go.Figure()

    for key, curve in family.diameter_head_curves.items():
        xs, ys = _curve_xy(curve)
        fig.add_trace(go.Scatter(
            x=xs,
            y=ys,
            mode="lines+markers",
            name=f"{key} head",
            hovertemplate="Q=%{x}<br>H=%{y} ft<extra></extra>",
        ))
        if xs and ys:
            fig.add_annotation(x=xs[0], y=ys[0], text=key.replace("_", "."), showarrow=False, xanchor="left")

    if include_efficiency:
        for key, pts in family.efficiency_contours.items():
            xs, ys = _points_xy(pts)
            fig.add_trace(go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                line={"dash": "solid", "width": 1.5},
                name=f"η {key}",
                hovertemplate="Q=%{x}<br>H=%{y} ft<extra></extra>",
            ))

    if include_power:
        for key, pts in family.brake_hp_lines.items():
            xs, ys = _points_xy(pts)
            fig.add_trace(go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                line={"dash": "dash", "width": 1.25},
                name=f"{key} bhp",
                hovertemplate="Q=%{x}<br>H=%{y} ft<extra></extra>",
            ))

    if include_npsh and family.npshr_curve is not None:
        xs, ys = _curve_xy(family.npshr_curve)
        fig.add_trace(go.Scatter(
            x=xs,
            y=ys,
            mode="lines+markers",
            name=f"NPSHR [{family.npsh_unit}]",
            yaxis="y2",
            line={"dash": "dot", "width": 2.0},
            hovertemplate="Q=%{x}<br>NPSHR=%{y}<extra></extra>",
        ))

    fig.update_layout(
        title=title or family.name,
        width=width,
        height=height,
        hovermode="closest",
        xaxis_title=f"Flow [{family.flow_unit}]",
        yaxis={"title": f"Head [{family.head_unit}]"},
        yaxis2={
            "title": f"NPSHR [{family.npsh_unit}]",
            "overlaying": "y",
            "side": "right",
            "showgrid": False,
        },
        legend={"orientation": "v", "x": 1.04, "y": 1.0},
        margin={"l": 70, "r": 170, "t": 80, "b": 70},
    )
    return fig


def operating_point_figure_plotly(
    pump: CentrifugalWaterPump,
    system: QuadraticSystemCurve,
    point: Mapping[str, Any],
    *,
    pump_rpm: float,
    arrangement: str = "single",
    number_of_pumps: int = 1,
    title: str | None = None,
    samples: int = 300,
):
    """Return a Plotly figure for pump/system matching."""
    go = _require_plotly()
    q_vals = _operating_q_grid(pump, pump_rpm, arrangement, number_of_pumps, samples=samples)
    pump_heads = [_combined_or_single_head(pump, q, pump_rpm, arrangement, number_of_pumps) for q in q_vals]
    system_heads = [system.head_ft(q) for q in q_vals]
    op_q, op_h = _point_flow_head(point)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=q_vals, y=pump_heads, mode="lines", name="Pump curve"))
    fig.add_trace(go.Scatter(x=q_vals, y=system_heads, mode="lines", name="System curve", line={"dash": "dash"}))
    if op_q is not None and op_h is not None:
        fig.add_trace(go.Scatter(
            x=[op_q],
            y=[op_h],
            mode="markers+text",
            name="Operating point",
            text=["OP"],
            textposition="top center",
            marker={"size": 11},
        ))
    fig.update_layout(
        title=title or f"Pump/System Match — {pump.name}",
        xaxis_title=f"Flow [{pump.flow_unit}]",
        yaxis_title="Head [ft]",
        hovermode="closest",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
    )
    return fig


def sweep_figure_plotly(payload: Mapping[str, Any], *, title: str | None = None):
    """Return a Plotly multi-panel dashboard for a pump RPM sweep."""
    try:
        from plotly.subplots import make_subplots
        import plotly.graph_objects as go
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Plotly is required for HTML sweep plots. Install plotly.") from exc

    points = list(payload.get("points", []))
    x = [_num(p.get("engine_speed_rpm"), i) for i, p in enumerate(points)]
    x_title = "Engine speed [rpm]"

    fig = make_subplots(
        rows=3,
        cols=2,
        subplot_titles=(
            "Flow", "Head", "Brake power", "Efficiency / BEP", "NPSH", "Status",
        ),
        vertical_spacing=0.10,
        horizontal_spacing=0.10,
    )
    fig.add_trace(go.Scatter(x=x, y=[p.get("flow_gpm") for p in points], mode="lines+markers", name="Flow [gpm]"), row=1, col=1)
    fig.add_trace(go.Scatter(x=x, y=[p.get("head_pump_ft") for p in points], mode="lines+markers", name="Pump head [ft]"), row=1, col=2)
    fig.add_trace(go.Scatter(x=x, y=[p.get("head_system_ft") for p in points], mode="lines", name="System head [ft]", line={"dash": "dash"}), row=1, col=2)
    fig.add_trace(go.Scatter(x=x, y=[p.get("brake_kw") for p in points], mode="lines+markers", name="Brake power [kW]"), row=2, col=1)
    fig.add_trace(go.Scatter(x=x, y=[p.get("efficiency") for p in points], mode="lines+markers", name="Efficiency"), row=2, col=2)
    fig.add_trace(go.Scatter(x=x, y=[p.get("bep_ratio") for p in points], mode="lines+markers", name="BEP ratio"), row=2, col=2)
    fig.add_trace(go.Scatter(x=x, y=[p.get("npsha_ft") for p in points], mode="lines+markers", name="NPSHA [ft]"), row=3, col=1)
    fig.add_trace(go.Scatter(x=x, y=[p.get("npshr_ft") for p in points], mode="lines+markers", name="NPSHR [ft]"), row=3, col=1)
    fig.add_trace(go.Scatter(x=x, y=[p.get("npsh_margin_ft") for p in points], mode="lines+markers", name="NPSH margin [ft]"), row=3, col=1)
    status_y = list(range(len(points)))
    fig.add_trace(go.Scatter(
        x=x,
        y=status_y,
        mode="markers+text",
        text=[str(p.get("status", "")) for p in points],
        textposition="middle right",
        name="Status",
    ), row=3, col=2)

    fig.update_xaxes(title_text=x_title, row=3, col=1)
    fig.update_xaxes(title_text=x_title, row=3, col=2)
    fig.update_layout(
        title=title or payload.get("pump", {}).get("name", "Pump RPM sweep"),
        height=900,
        width=1200,
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
        margin={"l": 70, "r": 60, "t": 110, "b": 70},
    )
    return fig



def speed_family_figure_plotly(
    pump: CentrifugalWaterPump,
    speeds_rpm: Sequence[float],
    *,
    system: QuadraticSystemCurve | None = None,
    suction: SuctionState | None = None,
    title: str | None = None,
    samples: int = 300,
    include_system: bool = True,
    include_operating_points: bool = True,
    include_bep_locus: bool = True,
    npsh_margin_required_ft: float = 3.0,
    width: int = 1100,
    height: int = 760,
):
    """Return a Plotly figure showing head curves at multiple shaft speeds."""
    go = _require_plotly()
    speeds = _clean_speeds(speeds_rpm)
    fig = go.Figure()

    all_q: list[float] = []
    for speed in speeds:
        q_vals = _speed_curve_q_grid(pump, speed, samples=samples)
        h_vals = [pump.head_ft(q, speed) for q in q_vals]
        all_q.extend(q_vals)
        fig.add_trace(go.Scatter(
            x=q_vals,
            y=h_vals,
            mode="lines",
            name=f"H(Q), n={speed:g} rpm",
            hovertemplate=(
                f"n={speed:g} rpm<br>Q=%{{x:.4g}} {pump.flow_unit}"
                "<br>H=%{y:.4g} ft<extra></extra>"
            ),
        ))

    # Scaled BEP locus, useful because the user can see where the best point
    # moves as speed changes. This is the natural marker to add to Fig. 11.9.
    bep_pts = _bep_locus_points(pump, speeds)
    if include_bep_locus and bep_pts:
        fig.add_trace(go.Scatter(
            x=[p[1] for p in bep_pts],
            y=[p[2] for p in bep_pts],
            mode="lines+markers+text",
            name="Scaled BEP locus",
            text=[f"{p[0]:g} rpm" for p in bep_pts],
            textposition="top center",
            line={"dash": "dot", "width": 2.0},
            hovertemplate="n=%{text}<br>Q_BEP=%{x:.4g}<br>H_BEP=%{y:.4g} ft<extra></extra>",
        ))

    # System curve and solved OPs, if a system is provided.
    if system is not None and include_system:
        q_max = max(all_q) if all_q else 1.0
        q_vals_sys = [q_max * i / max(samples - 1, 1) for i in range(samples)]
        fig.add_trace(go.Scatter(
            x=q_vals_sys,
            y=[system.head_ft(q) for q in q_vals_sys],
            mode="lines",
            name="System curve",
            line={"dash": "dash", "width": 2.5},
            hovertemplate=f"Q=%{{x:.4g}} {system.flow_unit}<br>Hsys=%{{y:.4g}} ft<extra></extra>",
        ))

    if system is not None and include_operating_points:
        op_rows = _operating_points_for_speed_family(
            pump,
            system,
            suction,
            speeds,
            npsh_margin_required_ft=npsh_margin_required_ft,
        )
        if op_rows:
            fig.add_trace(go.Scatter(
                x=[p["flow"] for p in op_rows],
                y=[p["head_pump_ft"] for p in op_rows],
                mode="markers+text",
                name="Operating points",
                text=[f"{p['pump_speed_rpm']:g} rpm" for p in op_rows],
                textposition="middle right",
                marker={"size": 10, "symbol": "circle-open"},
                customdata=[[p.get("brake_kw"), p.get("efficiency"), p.get("bep_ratio"), p.get("npsh_margin_ft"), p.get("status")] for p in op_rows],
                hovertemplate=(
                    "n=%{text}<br>Q=%{x:.4g}<br>H=%{y:.4g} ft"
                    "<br>Brake kW=%{customdata[0]:.4g}"
                    "<br>η=%{customdata[1]:.4g}"
                    "<br>BEP ratio=%{customdata[2]:.4g}"
                    "<br>NPSH margin=%{customdata[3]:.4g} ft"
                    "<br>Status=%{customdata[4]}<extra></extra>"
                ),
            ))

    subtitle = f"reference speed = {pump.reference_speed_rpm:g} rpm; impeller/size fixed"
    fig.update_layout(
        title=title or f"Speed family — {pump.name}<br><sup>{subtitle}</sup>",
        width=width,
        height=height,
        hovermode="closest",
        xaxis_title=f"Flow [{pump.flow_unit}]",
        yaxis_title=f"Head [{pump.head_unit}]",
        legend={"orientation": "v", "x": 1.02, "y": 1.0},
        margin={"l": 70, "r": 190, "t": 90, "b": 70},
    )
    return fig


# ---------------------------------------------------------------------------
# Matplotlib figure factories
# ---------------------------------------------------------------------------

def pump_family_figure_matplotlib(
    family: DigitizedPumpFamilyMap,
    *,
    title: str | None = None,
    include_efficiency: bool = True,
    include_power: bool = True,
    include_npsh: bool = True,
):
    """Return a Matplotlib figure for a rich pump-family map."""
    plt = _require_matplotlib()
    fig, ax = plt.subplots(figsize=(11.5, 7.5))

    for key, curve in family.diameter_head_curves.items():
        xs, ys = _curve_xy(curve)
        ax.plot(xs, ys, marker="o", linewidth=2.0, label=f"{key} head")
        if xs and ys:
            ax.annotate(key.replace("_", "."), (xs[0], ys[0]), xytext=(5, 0), textcoords="offset points")

    if include_efficiency:
        for key, pts in family.efficiency_contours.items():
            xs, ys = _points_xy(pts)
            ax.plot(xs, ys, linewidth=1.1, alpha=0.75, label=f"η {key}")

    if include_power:
        for key, pts in family.brake_hp_lines.items():
            xs, ys = _points_xy(pts)
            ax.plot(xs, ys, linestyle="--", linewidth=1.1, alpha=0.75, label=f"{key} bhp")

    ax2 = None
    if include_npsh and family.npshr_curve is not None:
        xs, ys = _curve_xy(family.npshr_curve)
        ax2 = ax.twinx()
        ax2.plot(xs, ys, linestyle=":", marker="s", linewidth=1.8, label=f"NPSHR [{family.npsh_unit}]")
        ax2.set_ylabel(f"NPSHR [{family.npsh_unit}]")

    ax.set_title(title or family.name)
    ax.set_xlabel(f"Flow [{family.flow_unit}]")
    ax.set_ylabel(f"Head [{family.head_unit}]")
    ax.grid(True, which="both", linewidth=0.5, alpha=0.45)

    handles, labels = ax.get_legend_handles_labels()
    if ax2 is not None:
        h2, l2 = ax2.get_legend_handles_labels()
        handles.extend(h2)
        labels.extend(l2)
    ax.legend(handles, labels, loc="center left", bbox_to_anchor=(1.08, 0.5), fontsize="small")
    fig.tight_layout()
    return fig


def operating_point_figure_matplotlib(
    pump: CentrifugalWaterPump,
    system: QuadraticSystemCurve,
    point: Mapping[str, Any],
    *,
    pump_rpm: float,
    arrangement: str = "single",
    number_of_pumps: int = 1,
    title: str | None = None,
    samples: int = 300,
):
    """Return a Matplotlib figure for pump/system matching."""
    plt = _require_matplotlib()
    fig, ax = plt.subplots(figsize=(9.5, 6.2))
    q_vals = _operating_q_grid(pump, pump_rpm, arrangement, number_of_pumps, samples=samples)
    pump_heads = [_combined_or_single_head(pump, q, pump_rpm, arrangement, number_of_pumps) for q in q_vals]
    system_heads = [system.head_ft(q) for q in q_vals]
    op_q, op_h = _point_flow_head(point)

    ax.plot(q_vals, pump_heads, linewidth=2.0, label="Pump curve")
    ax.plot(q_vals, system_heads, linestyle="--", linewidth=2.0, label="System curve")
    if op_q is not None and op_h is not None:
        ax.scatter([op_q], [op_h], s=60, label="Operating point", zorder=5)
        ax.annotate("OP", (op_q, op_h), xytext=(8, 8), textcoords="offset points")
    ax.set_title(title or f"Pump/System Match — {pump.name}")
    ax.set_xlabel(f"Flow [{pump.flow_unit}]")
    ax.set_ylabel("Head [ft]")
    ax.grid(True, which="both", linewidth=0.5, alpha=0.45)
    ax.legend()
    fig.tight_layout()
    return fig


def sweep_figure_matplotlib(payload: Mapping[str, Any], *, title: str | None = None):
    """Return a Matplotlib dashboard for a pump RPM sweep."""
    plt = _require_matplotlib()
    points = list(payload.get("points", []))
    x = [_num(p.get("engine_speed_rpm"), i) for i, p in enumerate(points)]

    fig, axes = plt.subplots(3, 2, figsize=(13.0, 10.0))
    ax = axes[0][0]
    ax.plot(x, [p.get("flow_gpm") for p in points], marker="o")
    ax.set_title("Flow")
    ax.set_ylabel("gpm")

    ax = axes[0][1]
    ax.plot(x, [p.get("head_pump_ft") for p in points], marker="o", label="Pump")
    ax.plot(x, [p.get("head_system_ft") for p in points], linestyle="--", label="System")
    ax.set_title("Head")
    ax.set_ylabel("ft")
    ax.legend()

    ax = axes[1][0]
    ax.plot(x, [p.get("brake_kw") for p in points], marker="o")
    ax.set_title("Brake Power")
    ax.set_ylabel("kW")

    ax = axes[1][1]
    ax.plot(x, [p.get("efficiency") for p in points], marker="o", label="Efficiency")
    ax.plot(x, [p.get("bep_ratio") for p in points], marker="s", label="BEP ratio")
    ax.set_title("Efficiency / BEP")
    ax.legend()

    ax = axes[2][0]
    ax.plot(x, [p.get("npsha_ft") for p in points], marker="o", label="NPSHA")
    ax.plot(x, [p.get("npshr_ft") for p in points], marker="s", label="NPSHR")
    ax.plot(x, [p.get("npsh_margin_ft") for p in points], marker="^", label="Margin")
    ax.set_title("NPSH")
    ax.set_xlabel("Engine speed [rpm]")
    ax.set_ylabel("ft")
    ax.legend()

    ax = axes[2][1]
    ax.scatter(x, list(range(len(points))))
    for i, p in enumerate(points):
        ax.annotate(str(p.get("status", "")), (x[i], i), xytext=(6, 0), textcoords="offset points", fontsize="small")
    ax.set_title("Status")
    ax.set_xlabel("Engine speed [rpm]")
    ax.set_yticks([])

    for row in axes:
        for a in row:
            a.grid(True, which="both", linewidth=0.5, alpha=0.45)

    fig.suptitle(title or payload.get("pump", {}).get("name", "Pump RPM sweep"), y=0.995)
    fig.tight_layout()
    return fig



def speed_family_figure_matplotlib(
    pump: CentrifugalWaterPump,
    speeds_rpm: Sequence[float],
    *,
    system: QuadraticSystemCurve | None = None,
    suction: SuctionState | None = None,
    title: str | None = None,
    samples: int = 300,
    include_system: bool = True,
    include_operating_points: bool = True,
    include_bep_locus: bool = True,
    npsh_margin_required_ft: float = 3.0,
):
    """Return a Matplotlib figure showing head curves at multiple shaft speeds."""
    plt = _require_matplotlib()
    speeds = _clean_speeds(speeds_rpm)
    fig, ax = plt.subplots(figsize=(10.5, 6.8))

    all_q: list[float] = []
    for speed in speeds:
        q_vals = _speed_curve_q_grid(pump, speed, samples=samples)
        h_vals = [pump.head_ft(q, speed) for q in q_vals]
        all_q.extend(q_vals)
        ax.plot(q_vals, h_vals, linewidth=2.0, label=f"n={speed:g} rpm")

    bep_pts = _bep_locus_points(pump, speeds)
    if include_bep_locus and bep_pts:
        ax.plot(
            [p[1] for p in bep_pts],
            [p[2] for p in bep_pts],
            linestyle=":",
            marker="o",
            linewidth=2.0,
            label="Scaled BEP locus",
        )
        for speed, q, h in bep_pts:
            ax.annotate(f"{speed:g}", (q, h), xytext=(4, 4), textcoords="offset points", fontsize="small")

    if system is not None and include_system:
        q_max = max(all_q) if all_q else 1.0
        q_vals_sys = [q_max * i / max(samples - 1, 1) for i in range(samples)]
        ax.plot(q_vals_sys, [system.head_ft(q) for q in q_vals_sys], linestyle="--", linewidth=2.2, label="System curve")

    if system is not None and include_operating_points:
        op_rows = _operating_points_for_speed_family(
            pump,
            system,
            suction,
            speeds,
            npsh_margin_required_ft=npsh_margin_required_ft,
        )
        if op_rows:
            ax.scatter([p["flow"] for p in op_rows], [p["head_pump_ft"] for p in op_rows], s=55, zorder=5, label="Operating points")
            for p in op_rows:
                ax.annotate(f"{p['pump_speed_rpm']:g}", (p["flow"], p["head_pump_ft"]), xytext=(6, 0), textcoords="offset points", fontsize="small")

    ax.set_title(title or f"Speed family — {pump.name}\n(reference {pump.reference_speed_rpm:g} rpm, fixed impeller size)")
    ax.set_xlabel(f"Flow [{pump.flow_unit}]")
    ax.set_ylabel(f"Head [{pump.head_unit}]")
    ax.grid(True, which="both", linewidth=0.5, alpha=0.45)
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), fontsize="small")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _clean_speeds(speeds_rpm: Sequence[float]) -> list[float]:
    """Return sorted unique positive pump speeds."""
    speeds: list[float] = []
    for speed in speeds_rpm:
        s = float(speed)
        if s <= 0.0 or math.isnan(s) or math.isinf(s):
            raise ValueError(f"Invalid pump speed: {speed!r}")
        if not any(abs(s - old) < 1e-9 for old in speeds):
            speeds.append(s)
    if not speeds:
        raise ValueError("At least one positive pump speed is required")
    return sorted(speeds)


def _speed_curve_q_grid(pump: CentrifugalWaterPump, pump_rpm: float, *, samples: int) -> list[float]:
    """Flow grid for a speed-scaled pump curve."""
    q0, q1 = pump.flow_bounds_at_speed(pump_rpm)
    q0 = max(q0, 0.0)
    if q1 <= q0:
        q1 = q0 + 1.0
    if samples < 2:
        samples = 2
    return [q0 + (q1 - q0) * i / (samples - 1) for i in range(samples)]


def _bep_locus_points(pump: CentrifugalWaterPump, speeds_rpm: Sequence[float]) -> list[tuple[float, float, float]]:
    """Return (speed, scaled_Q_BEP, scaled_H_BEP) points when BEP data exists."""
    if pump.bep_flow is None or pump.bep_head is None:
        return []
    out: list[tuple[float, float, float]] = []
    for speed in speeds_rpm:
        scale = pump.speed_scale(float(speed))
        out.append((float(speed), scale.flow_from_reference(pump.bep_flow), scale.head_from_reference(pump.bep_head)))
    return out


def _operating_points_for_speed_family(
    pump: CentrifugalWaterPump,
    system: QuadraticSystemCurve,
    suction: SuctionState | None,
    speeds_rpm: Sequence[float],
    *,
    npsh_margin_required_ft: float,
) -> list[dict[str, Any]]:
    """Solve and return operating points for each speed; skip failed brackets."""
    rows: list[dict[str, Any]] = []
    for speed in speeds_rpm:
        try:
            point = match_system(
                pump,
                system,
                float(speed),
                suction=suction,
                engine_speed_rpm=None,
                npsh_margin_required_ft=npsh_margin_required_ft,
            )
        except Exception:
            # On early design plots, some speeds may not intersect the proposed
            # system curve. Keep the plot useful instead of failing the export.
            continue
        rows.append(point.to_dict())
    return rows


def _require_plotly():
    try:
        import plotly.graph_objects as go
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Plotly is required for HTML pump plots. Install plotly.") from exc
    return go


def _require_matplotlib():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Matplotlib is required for static pump plots. Install matplotlib.") from exc
    return plt


def _close_matplotlib(fig: Any) -> None:
    try:
        import matplotlib.pyplot as plt
        plt.close(fig)
    except Exception:
        pass


def _ensure_parent(path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def _curve_xy(curve: Curve1D) -> tuple[list[float], list[float]]:
    if curve.points:
        return [p[0] for p in curve.points], [p[1] for p in curve.points]
    # Polynomial curves need explicit bounds. Use a conservative 0..1 fallback;
    # operating-point plots use pump.flow_bounds_at_speed instead.
    samples = curve.sample(101, x_min=0.0, x_max=1.0)
    return [p["x"] for p in samples], [p["y"] for p in samples]


def _points_xy(points: Sequence[Sequence[float]]) -> tuple[list[float], list[float]]:
    return [float(p[0]) for p in points], [float(p[1]) for p in points]


def _operating_q_grid(
    pump: CentrifugalWaterPump,
    pump_rpm: float,
    arrangement: str,
    number_of_pumps: int,
    *,
    samples: int,
) -> list[float]:
    q0, q1 = pump.flow_bounds_at_speed(pump_rpm)
    q0 = max(q0, 0.0)
    mode = arrangement.strip().lower()
    n = max(int(number_of_pumps), 1)
    if mode == "parallel":
        q1 *= n
    if samples < 2:
        samples = 2
    return [q0 + (q1 - q0) * i / (samples - 1) for i in range(samples)]


def _combined_or_single_head(
    pump: CentrifugalWaterPump,
    q_total: float,
    pump_rpm: float,
    arrangement: str,
    number_of_pumps: int,
) -> float:
    mode = arrangement.strip().lower()
    n = max(int(number_of_pumps), 1)
    if mode == "parallel":
        return pump.head_ft(q_total / n, pump_rpm)
    if mode == "series":
        return n * pump.head_ft(q_total, pump_rpm)
    return pump.head_ft(q_total, pump_rpm)


def _extract_point_from_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    if "point" in payload and isinstance(payload["point"], Mapping):
        return payload["point"]
    return payload


def _point_flow_head(point: Mapping[str, Any]) -> tuple[float | None, float | None]:
    if "flow_total" in point:
        q = _optional_num(point.get("flow_total"))
        h = _optional_num(point.get("head_combined_ft", point.get("head_system_ft")))
        return q, h
    q = _optional_num(point.get("flow"))
    h = _optional_num(point.get("head_pump_ft", point.get("head_system_ft")))
    return q, h


def _optional_num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
    except Exception:
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def _num(value: Any, fallback: float) -> float:
    out = _optional_num(value)
    return float(fallback) if out is None else out
