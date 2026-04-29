#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""Command-line interface for vICE / ``simulator``.

The CLI is intentionally conservative: it preserves the existing engine
simulation workflows while adding a deployment-safe Sphinx skeleton generator
for GitHub Pages.

Commands
--------
``run``
    Run a cycle simulation from a JSON configuration file.

``list-inputs``
    List example JSON input files under ``simulator/in``.

``plot``
    Generate a Plotly P-V indicator diagram from a simulation result JSON.

``pump-match-system``
    Match a centrifugal pump curve to a system curve at one pump speed.

``pump-rpm-sweep``
    Sweep pump operating points across an engine RPM range.

``pump-combined``
    Match identical pumps combined in parallel or series to a system curve.

``pump-bep-speed``
    Check whether changing pump speed can put the scaled BEP on a system curve.

``pump-family-summary``
    Summarize a digitized multi-curve pump-family map JSON.

``pump-plot-family``
    Export a digitized pump-family map to Plotly HTML and/or static image.

``pump-plot-operating``
    Export a pump/system operating-point overlay plot.

``pump-plot-sweep``
    Export an RPM-sweep dashboard from a pump sweep result JSON.

``sphinx-skel``
    Generate a conservative Sphinx documentation skeleton under
    ``simulator/docs`` by default.

Deployment notes
----------------
The ``sphinx-skel`` command follows the lessons learned from the related
engineering-tool projects:

- dynamic reStructuredText heading underlines
- conservative generated RST files
- ``_static/.gitkeep`` and ``_templates/.gitkeep``
- minimal Sphinx Makefile
- importable-module filtering for autodoc
- deploy-safe mock imports for optional scientific, plotting, and GUI deps

Typical documentation command from the repository root::

    python -m simulator.cli sphinx-skel

Then build locally with::

    make -C simulator/docs html
"""

import argparse
import importlib.util
import os
import sys
from pathlib import Path
from typing import Sequence

# ---------- Import shim so `python simulator/cli.py ...` also works ----------
if __package__ in (None, ""):
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)


def _load_apis():
    """Lazy-load simulator.apis so pump-only CLI commands avoid optional imports."""
    if __package__ in (None, ""):
        from simulator import apis as _apis  # type: ignore
    else:
        from . import apis as _apis
    return _apis


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _pkg_dir() -> Path:
    """Return the ``simulator`` package directory."""
    return Path(__file__).resolve().parent


def _repo_root() -> Path:
    """Return the repository root for the flat ``vice/simulator`` layout."""
    return _pkg_dir().parent


def _resolve_docs_dest(dest: str | Path | None) -> Path:
    """Resolve a docs destination for the vICE package layout.

    If no destination is supplied, the skeleton is created at
    ``simulator/docs``. Relative destinations are normally resolved against the
    package directory, so ``sphinx-skel docs`` also creates ``simulator/docs``.
    If the caller explicitly passes a path beginning with ``simulator/``, it is
    treated as repository-root-relative to avoid ``simulator/simulator/docs``.
    """
    if dest is None or str(dest).strip() == "":
        return (_pkg_dir() / "docs").resolve()

    p = Path(dest).expanduser()
    if p.is_absolute():
        return p.resolve()

    parts = p.parts
    if parts and parts[0] == "simulator":
        return (_repo_root() / p).resolve()

    return (_pkg_dir() / p).resolve()


# ---------------------------------------------------------------------------
# Sphinx skeleton helpers
# ---------------------------------------------------------------------------

_RST_CHARS = ("=", "-", "~", "^")

# Conservative import targets for the single-package vICE documentation site.
# Optional or future tools are safe to list because ``sphinx-skel`` filters the
# list with ``importlib.util.find_spec`` before generating ``api.rst``.
_MODULES: tuple[str, ...] = (
    # Package root / application layer
    "simulator",
    "simulator.cli",
    "simulator.main",
    "simulator.app",
    "simulator.apis",
    "simulator.core",
    "simulator.design",
    "simulator.fuels",
    "simulator.io",
    "simulator.turbo",
    "simulator.utils",
    # Pump analysis layer
    "simulator.pumps",
    "simulator.pumps.affinity",
    "simulator.pumps.cavitation",
    "simulator.pumps.combined",
    "simulator.pumps.curves",
    "simulator.pumps.power",
    "simulator.pumps.pump_map",
    "simulator.pumps.plotting",
    "simulator.pumps.system_curve",
    "simulator.pumps.water_pump",
    # Thermochemistry layer
    "simulator.thermo.equilibrium",
    "simulator.thermo.reactor0d",
    "simulator.thermo.species",
    "simulator.thermo.thermo_state",
    "simulator.thermo.tools.equilibrium_flame",
    "simulator.thermo.tools.equilibrium_flame_compare",
    # Tool scripts / analysis workflows
    "simulator.tools.bsfc_sweep_phi",
    "simulator.tools.tool_bsfc_contours",
    "simulator.tools.tool_bsfc_map_epa",
    "simulator.tools.tool_bsfc_table",
    "simulator.tools.tool_bsfc_vs_displacement",
    "simulator.tools.tool_bsfc_vs_phi_rc",
    "simulator.tools.tool_bsfc_vs_speed_rc",
    "simulator.tools.tool_compressor_map_efr71",
    "simulator.tools.tool_cycle_thermo_plot",
    "simulator.tools.tool_flame_summary",
    "simulator.tools.tool_full_load_sweep",
    "simulator.tools.tool_generate_template_input",
    "simulator.tools.tool_indicator_from_result",
    "simulator.tools.tool_turbine_map_gt4088",
    "simulator.tools.tool_turbo_match_opline",
    "simulator.tools.turbo_match",
)


def _rst_heading(title: str, level: int = 0) -> str:
    """Return a Sphinx-safe reStructuredText heading."""
    ch = _RST_CHARS[min(max(level, 0), len(_RST_CHARS) - 1)]
    text = str(title).strip() or "Untitled"
    return f"{text}\n{ch * len(text)}\n"


def _is_importable(module_name: str) -> bool:
    """Return whether a module can be located without importing it."""
    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        return False


def _write_text(path: Path, text: str, *, force: bool = False) -> bool:
    """Write text to ``path`` if missing, or always when ``force`` is true."""
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def _touch(path: Path) -> None:
    """Create an empty file and all parent directories if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)


def _generate_conf_py() -> str:
    """Generate a conservative Sphinx ``conf.py`` for ``simulator/docs``."""
    return '''# Generated by simulator.cli sphinx-skel
from __future__ import annotations

import sys
from pathlib import Path

# simulator/docs -> repository root
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

project = "vICE Simulator"
author = "Pablo Marcel Montijo"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
html_theme = "furo"
html_static_path = ["_static"]

autodoc_typehints = "description"
autodoc_member_order = "bysource"
autodoc_mock_imports = [
    "CoolProp",
    "cantera",
    "dearpygui",
    "dearpygui.dearpygui",
    "gekko",
    "matplotlib",
    "matplotlib.pyplot",
    "numpy",
    "pandas",
    "plotly",
    "plotly.graph_objects",
    "plotly.subplots",
    "pyfiglet",
    "scipy",
    "scipy.interpolate",
    "scipy.linalg",
    "scipy.optimize",
    "sympy",
    "yaml",
]

napoleon_google_docstring = True
napoleon_numpy_docstring = True
'''


def _module_group(module_name: str) -> str:
    """Return a readable documentation group for a module name."""
    if module_name.startswith("simulator.thermo.tools."):
        return "Thermochemistry Tools"
    if module_name.startswith("simulator.thermo."):
        return "Thermochemistry Core"
    if module_name.startswith("simulator.tools."):
        return "Engineering Tools"
    return "Simulator Core"


# Package aggregator modules re-export objects from implementation modules.
# Documenting their members causes Sphinx duplicate-object warnings such as
# ``simulator.main`` being emitted once from ``simulator`` and once from
# ``simulator.main``. Keep package roots as landing summaries and document
# implementation modules with full autodoc member listings.
_PACKAGE_SUMMARY_MODULES: tuple[str, ...] = (
    "simulator",
    "simulator.pumps",
)


def _automodule_block(module_name: str) -> str:
    """Return a duplicate-safe automodule block for ``api.rst``."""
    if module_name in _PACKAGE_SUMMARY_MODULES:
        return f".. automodule:: {module_name}\n\n"
    return (
        f".. automodule:: {module_name}\n"
        "   :members:\n"
        "   :undoc-members:\n"
        "   :show-inheritance:\n\n"
    )


def _generate_api_rst(modules: Sequence[str]) -> str:
    """Generate a duplicate-safe API page for importable simulator modules."""
    parts: list[str] = [_rst_heading("API Reference", 0)]

    grouped: dict[str, list[str]] = {}
    for mod in modules:
        grouped.setdefault(_module_group(mod), []).append(mod)

    group_order = [
        "Simulator Core",
        "Thermochemistry Core",
        "Thermochemistry Tools",
        "Engineering Tools",
    ]

    for group in group_order:
        mods = grouped.get(group, [])
        if not mods:
            continue
        parts.append(_rst_heading(group, 1))
        for mod in mods:
            parts.append(_rst_heading(mod, 2))
            parts.append(_automodule_block(mod))

    return "\n".join(parts).rstrip() + "\n"

def _generate_index_rst() -> str:
    """Generate the Sphinx root page."""
    return (
        _rst_heading("vICE Simulator Documentation", 0)
        + "\n"
        + "vICE is a Python-first Virtual Internal Combustion Engine simulator "
          "for cycle thermodynamics, combustion sweeps, BSFC maps, turbocharger "
          "matching utilities, and reproducible engine-analysis workflows.\n\n"
        + ".. toctree::\n"
          "   :maxdepth: 2\n"
          "   :caption: Contents:\n\n"
          "   api\n"
    )


def _generate_makefile() -> str:
    """Generate a minimal project-standard Sphinx Makefile."""
    return (
        "# Minimal Sphinx Makefile\n"
        ".PHONY: html clean\n"
        "html:\n"
        "\t+sphinx-build -b html . _build/html\n"
        "clean:\n"
        "\t+rm -rf _build\n"
    )


def create_sphinx_skeleton(dest: str | Path | None = None, *, force: bool = False) -> Path:
    """Create a conservative Sphinx skeleton for the vICE simulator package."""
    out_dir = _resolve_docs_dest(dest)
    out_dir.mkdir(parents=True, exist_ok=True)

    root_s = str(_repo_root())
    if root_s not in sys.path:
        sys.path.insert(0, root_s)

    importable_modules = [m for m in _MODULES if _is_importable(m)]
    if not importable_modules:
        importable_modules = [
            "simulator",
            "simulator.cli",
            "simulator.app",
            "simulator.apis",
            "simulator.core",
            "simulator.design",
            "simulator.fuels",
            "simulator.io",
            "simulator.turbo",
            "simulator.utils",
        ]

    _write_text(out_dir / "conf.py", _generate_conf_py(), force=force)
    _write_text(out_dir / "index.rst", _generate_index_rst(), force=force)
    _write_text(out_dir / "api.rst", _generate_api_rst(importable_modules), force=force)
    _write_text(out_dir / "Makefile", _generate_makefile(), force=force)

    _touch(out_dir / "_static" / ".gitkeep")
    _touch(out_dir / "_templates" / ".gitkeep")

    return out_dir


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Build the vICE command-line parser."""
    parser = argparse.ArgumentParser(
        prog="simulator",
        description="vICE – Virtual Internal Combustion Engine Simulator",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run a simulation from a JSON input file")
    run_p.add_argument("--config", required=True, help="Path to JSON input file")
    run_p.add_argument("--outfile", required=True, help="Path to output JSON file")
    run_p.add_argument(
        "--cycles",
        type=int,
        default=1,
        help="Number of engine cycles to simulate",
    )

    sub.add_parser("list-inputs", help="List example JSON input files")

    plot_p = sub.add_parser(
        "plot",
        help="Plot an indicator diagram from a result JSON file",
    )
    plot_p.add_argument("--result", required=True, help="Path to result JSON file")
    plot_p.add_argument(
        "--html",
        help="Output HTML path (default: next to result JSON)",
    )

    pump_match_p = sub.add_parser(
        "pump-match-system",
        help="Match a centrifugal pump curve to a system curve at one pump speed.",
    )
    pump_match_p.add_argument("--pump", required=True, help="Path to pump curve JSON")
    pump_match_p.add_argument("--system", required=True, help="Path to system curve JSON")
    pump_match_p.add_argument("--pump-rpm", type=float, required=True, help="Pump speed [rpm]")
    pump_match_p.add_argument("--engine-rpm", type=float, help="Optional engine speed metadata [rpm]")
    pump_match_p.add_argument("--out-json", required=True, help="Output JSON path")
    pump_match_p.add_argument("--out-csv", help="Optional one-row CSV output path")
    pump_match_p.add_argument(
        "--npsh-margin-ft",
        type=float,
        default=3.0,
        help="Required NPSH margin used for status flagging [ft]",
    )

    pump_sweep_p = sub.add_parser(
        "pump-rpm-sweep",
        help="Run a centrifugal water-pump operating-point sweep vs engine RPM.",
    )
    pump_sweep_p.add_argument("--pump", required=True, help="Path to pump curve JSON")
    pump_sweep_p.add_argument("--system", required=True, help="Path to system curve JSON")
    pump_sweep_p.add_argument("--engine-rpm-min", type=float, required=True, help="Minimum engine speed [rpm]")
    pump_sweep_p.add_argument("--engine-rpm-max", type=float, required=True, help="Maximum engine speed [rpm]")
    pump_sweep_p.add_argument("--engine-rpm-step", type=float, required=True, help="Engine speed step [rpm]")
    pump_sweep_p.add_argument("--pulley-ratio", type=float, default=1.0, help="pump_rpm / engine_rpm")
    pump_sweep_p.add_argument("--out-json", required=True, help="Output JSON path")
    pump_sweep_p.add_argument("--out-csv", help="Optional CSV table output path")
    pump_sweep_p.add_argument(
        "--npsh-margin-ft",
        type=float,
        default=3.0,
        help="Required NPSH margin used for status flagging [ft]",
    )

    pump_combined_p = sub.add_parser(
        "pump-combined",
        help="Match identical centrifugal pumps in parallel or series to a system curve.",
    )
    pump_combined_p.add_argument("--pump", required=True, help="Path to pump curve JSON")
    pump_combined_p.add_argument("--system", required=True, help="Path to system curve JSON")
    pump_combined_p.add_argument("--arrangement", choices=["parallel", "series"], required=True, help="Pump arrangement")
    pump_combined_p.add_argument("--number-of-pumps", type=int, default=2, help="Number of identical pumps")
    pump_combined_p.add_argument("--pump-rpm", type=float, required=True, help="Pump speed [rpm]")
    pump_combined_p.add_argument("--engine-rpm", type=float, help="Optional engine speed metadata [rpm]")
    pump_combined_p.add_argument("--out-json", required=True, help="Output JSON path")
    pump_combined_p.add_argument("--out-csv", help="Optional one-row CSV output path")
    pump_combined_p.add_argument(
        "--npsh-margin-ft",
        type=float,
        default=3.0,
        help="Required NPSH margin used for status flagging [ft]",
    )

    pump_bep_p = sub.add_parser(
        "pump-bep-speed",
        help="Check if a speed change can put the scaled BEP point on the system curve.",
    )
    pump_bep_p.add_argument("--pump", required=True, help="Path to pump curve JSON")
    pump_bep_p.add_argument("--system", required=True, help="Path to system curve JSON")
    pump_bep_p.add_argument("--out-json", required=True, help="Output JSON path")

    pump_family_p = sub.add_parser(
        "pump-family-summary",
        help="Summarize a digitized multi-curve pump-family map JSON.",
    )
    pump_family_p.add_argument("--map", required=True, help="Path to pump-family map JSON")
    pump_family_p.add_argument("--out-json", help="Optional output JSON path")

    pump_plot_family_p = sub.add_parser(
        "pump-plot-family",
        help="Export a digitized pump-family map to Plotly HTML and/or static image.",
    )
    pump_plot_family_p.add_argument("--map", required=True, help="Path to pump-family map JSON")
    pump_plot_family_p.add_argument("--out-html", help="Output Plotly HTML path")
    pump_plot_family_p.add_argument("--out-png", help="Output static image path, typically .png; .svg/.pdf also work")
    pump_plot_family_p.add_argument("--title", help="Optional plot title")
    pump_plot_family_p.add_argument("--no-efficiency", action="store_true", help="Hide efficiency contours")
    pump_plot_family_p.add_argument("--no-power", action="store_true", help="Hide brake-horsepower guide lines")
    pump_plot_family_p.add_argument("--no-npsh", action="store_true", help="Hide NPSH/NPSHR layer")
    pump_plot_family_p.add_argument("--dpi", type=int, default=160, help="DPI for static image output")

    pump_plot_operating_p = sub.add_parser(
        "pump-plot-operating",
        help="Export a pump/system operating-point overlay plot.",
    )
    pump_plot_operating_p.add_argument("--pump", required=True, help="Path to pump curve JSON")
    pump_plot_operating_p.add_argument("--system", required=True, help="Path to system curve JSON")
    pump_plot_operating_p.add_argument("--pump-rpm", type=float, required=True, help="Pump speed [rpm]")
    pump_plot_operating_p.add_argument("--engine-rpm", type=float, help="Optional engine speed metadata [rpm]")
    pump_plot_operating_p.add_argument("--result-json", help="Optional existing pump result JSON to plot the operating point")
    pump_plot_operating_p.add_argument("--arrangement", choices=["single", "parallel", "series"], default="single", help="Pump arrangement for the plotted pump curve")
    pump_plot_operating_p.add_argument("--number-of-pumps", type=int, default=1, help="Number of identical pumps for series/parallel overlays")
    pump_plot_operating_p.add_argument("--out-html", help="Output Plotly HTML path")
    pump_plot_operating_p.add_argument("--out-png", help="Output static image path, typically .png; .svg/.pdf also work")
    pump_plot_operating_p.add_argument("--title", help="Optional plot title")
    pump_plot_operating_p.add_argument("--samples", type=int, default=300, help="Number of sample points for curve plotting")
    pump_plot_operating_p.add_argument("--dpi", type=int, default=160, help="DPI for static image output")
    pump_plot_operating_p.add_argument(
        "--npsh-margin-ft",
        type=float,
        default=3.0,
        help="Required NPSH margin used when recomputing the operating point [ft]",
    )

    pump_plot_sweep_p = sub.add_parser(
        "pump-plot-sweep",
        help="Export an RPM-sweep dashboard from a pump sweep result JSON.",
    )
    pump_plot_sweep_p.add_argument("--result", required=True, help="Path to pump_rpm_sweep result JSON")
    pump_plot_sweep_p.add_argument("--out-html", help="Output Plotly HTML path")
    pump_plot_sweep_p.add_argument("--out-png", help="Output static image path, typically .png; .svg/.pdf also work")
    pump_plot_sweep_p.add_argument("--title", help="Optional plot title")
    pump_plot_sweep_p.add_argument("--dpi", type=int, default=160, help="DPI for static image output")

    sphinx_p = sub.add_parser(
        "sphinx-skel",
        help="Create a conservative Sphinx docs skeleton for GitHub Pages.",
    )
    sphinx_p.add_argument(
        "dest",
        nargs="?",
        default=None,
        help=(
            "Destination directory. Default: simulator/docs. "
            "Relative 'docs' is resolved under the simulator package."
        ),
    )
    sphinx_p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing generated files.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "pump-match-system":
        from simulator.pumps import (
            CentrifugalWaterPump,
            QuadraticSystemCurve,
            SuctionState,
            load_system_json,
            match_system,
            write_points_csv,
            write_points_json,
        )

        pump = CentrifugalWaterPump.from_json(args.pump)
        system_data = load_system_json(args.system)
        system = QuadraticSystemCurve.from_dict(system_data)
        suction = SuctionState.from_dict(system_data.get("suction"))
        point = match_system(
            pump,
            system,
            args.pump_rpm,
            suction=suction,
            engine_speed_rpm=args.engine_rpm,
            npsh_margin_required_ft=args.npsh_margin_ft,
        )
        payload = {
            "kind": "pump_match_system",
            "pump": pump.to_summary_dict(),
            "system": system.to_dict(),
            "suction": suction.to_dict(),
            "point": point.to_dict(),
        }
        write_points_json(args.out_json, payload)
        if args.out_csv:
            write_points_csv(args.out_csv, [point])
        print(args.out_json)
        return 0

    if args.command == "pump-rpm-sweep":
        from simulator.pumps import (
            CentrifugalWaterPump,
            QuadraticSystemCurve,
            SuctionState,
            load_system_json,
            rpm_sweep,
            write_points_csv,
            write_points_json,
        )

        pump = CentrifugalWaterPump.from_json(args.pump)
        system_data = load_system_json(args.system)
        system = QuadraticSystemCurve.from_dict(system_data)
        suction = SuctionState.from_dict(system_data.get("suction"))
        points = rpm_sweep(
            pump,
            system,
            engine_rpm_min=args.engine_rpm_min,
            engine_rpm_max=args.engine_rpm_max,
            engine_rpm_step=args.engine_rpm_step,
            pulley_ratio=args.pulley_ratio,
            suction=suction,
            npsh_margin_required_ft=args.npsh_margin_ft,
        )
        payload = {
            "kind": "pump_rpm_sweep",
            "pump": pump.to_summary_dict(),
            "system": system.to_dict(),
            "suction": suction.to_dict(),
            "pulley_ratio": args.pulley_ratio,
            "points": [p.to_dict() for p in points],
        }
        write_points_json(args.out_json, payload)
        if args.out_csv:
            write_points_csv(args.out_csv, points)
        print(args.out_json)
        return 0

    if args.command == "pump-combined":
        from simulator.pumps import (
            CentrifugalWaterPump,
            QuadraticSystemCurve,
            SuctionState,
            load_system_json,
            match_combined_system,
            write_combined_csv,
            write_combined_json,
        )

        pump = CentrifugalWaterPump.from_json(args.pump)
        system_data = load_system_json(args.system)
        system = QuadraticSystemCurve.from_dict(system_data)
        suction = SuctionState.from_dict(system_data.get("suction"))
        point = match_combined_system(
            pump,
            system,
            args.pump_rpm,
            arrangement=args.arrangement,
            number_of_pumps=args.number_of_pumps,
            suction=suction,
            engine_speed_rpm=args.engine_rpm,
            npsh_margin_required_ft=args.npsh_margin_ft,
        )
        payload = {
            "kind": "pump_combined",
            "arrangement": args.arrangement,
            "number_of_pumps": args.number_of_pumps,
            "pump": pump.to_summary_dict(),
            "system": system.to_dict(),
            "suction": suction.to_dict(),
            "point": point.to_dict(),
        }
        write_combined_json(args.out_json, payload)
        if args.out_csv:
            write_combined_csv(args.out_csv, [point])
        print(args.out_json)
        return 0

    if args.command == "pump-bep-speed":
        from simulator.pumps import (
            CentrifugalWaterPump,
            QuadraticSystemCurve,
            bep_speed_to_match_system,
            load_system_json,
            write_points_json,
        )

        pump = CentrifugalWaterPump.from_json(args.pump)
        system_data = load_system_json(args.system)
        system = QuadraticSystemCurve.from_dict(system_data)
        result = bep_speed_to_match_system(pump, system)
        payload = {
            "kind": "pump_bep_speed",
            "pump": pump.to_summary_dict(),
            "system": system.to_dict(),
            "result": result.to_dict(),
        }
        write_points_json(args.out_json, payload)
        print(args.out_json)
        return 0

    if args.command == "pump-family-summary":
        import json
        from simulator.pumps import load_pump_family_json, write_points_json

        family = load_pump_family_json(args.map)
        payload = {"kind": "pump_family_summary", "summary": family.to_summary_dict()}
        if args.out_json:
            write_points_json(args.out_json, payload)
            print(args.out_json)
        else:
            print(json.dumps(payload, indent=2))
        return 0

    if args.command == "pump-plot-family":
        from simulator.pumps.plotting import write_pump_family_plot

        result = write_pump_family_plot(
            args.map,
            out_html=args.out_html,
            out_image=args.out_png,
            title=args.title,
            include_efficiency=not args.no_efficiency,
            include_power=not args.no_power,
            include_npsh=not args.no_npsh,
            dpi=args.dpi,
        )
        if result.html:
            print(result.html)
        if result.image:
            print(result.image)
        return 0

    if args.command == "pump-plot-operating":
        from simulator.pumps.plotting import write_operating_point_plot

        result = write_operating_point_plot(
            args.pump,
            args.system,
            pump_rpm=args.pump_rpm,
            result_json=args.result_json,
            out_html=args.out_html,
            out_image=args.out_png,
            arrangement=args.arrangement,
            number_of_pumps=args.number_of_pumps,
            engine_rpm=args.engine_rpm,
            npsh_margin_required_ft=args.npsh_margin_ft,
            title=args.title,
            samples=args.samples,
            dpi=args.dpi,
        )
        if result.html:
            print(result.html)
        if result.image:
            print(result.image)
        return 0

    if args.command == "pump-plot-sweep":
        from simulator.pumps.plotting import write_sweep_plot

        result = write_sweep_plot(
            args.result,
            out_html=args.out_html,
            out_image=args.out_png,
            title=args.title,
            dpi=args.dpi,
        )
        if result.html:
            print(result.html)
        if result.image:
            print(result.image)
        return 0

    if args.command == "sphinx-skel":
        out_dir = create_sphinx_skeleton(args.dest, force=bool(args.force))
        print(str(out_dir))
        return 0

    if args.command == "run":
        apis = _load_apis()
        req = apis.RunRequest(
            verb="run-sim",
            infile=args.config,
            outfile=args.outfile,
            params={"cycles": args.cycles},
        )
        res = apis.run(req)
        if not res.ok:
            parser.error(res.reason)
        return 0

    if args.command == "list-inputs":
        apis = _load_apis()
        res = apis.run(apis.RunRequest(verb="list-inputs"))
        if not res.ok:
            parser.error(res.reason)
        for path in res.data.get("inputs", []):
            print(path)
        return 0

    if args.command == "plot":
        apis = _load_apis()
        params = {"result_path": args.result}
        if args.html:
            params["out_html"] = args.html
        res = apis.run(apis.RunRequest(verb="plot-indicator", params=params))
        if not res.ok:
            parser.error(res.reason)
        print(res.data.get("html"))
        return 0

    parser.error("Unknown command")
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
