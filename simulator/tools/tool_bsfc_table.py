from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List
import csv
import json
import re

import plotly.graph_objects as go


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out"


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _collect_full_load(out_dir: Path) -> List[Dict[str, Any]]:
    """Collect full-load BSFC points from full_load_N_*.json files."""
    records: List[Dict[str, Any]] = []
    for path in sorted(out_dir.glob("full_load_N_*.json")):
        m = re.search(r"_N_(\d+)\.json$", path.name)
        if not m:
            continue
        speed_rpm = float(m.group(1))
        data = _load_json(path)
        bmep = data.get("bmep_bar")
        bsfc = data.get("bsfc_g_per_kWh")
        bp_kw = data.get("brake_power_kW")
        bt_Nm = data.get("brake_torque_Nm")
        if (
            bmep is None
            or bsfc is None
            or bp_kw is None
            or bt_Nm is None
        ):
            continue
        records.append(
            {
                "family": "full_load",
                "speed_rpm": speed_rpm,
                "bmep_bar": bmep,
                "brake_power_kW": bp_kw,
                "brake_torque_Nm": bt_Nm,
                "bsfc_g_per_kWh": bsfc,
                "source_file": path.name,
            }
        )
    return records


def _collect_pboost(out_dir: Path) -> List[Dict[str, Any]]:
    """Collect boosted-intake BSFC points from pboost_pint_*.json files."""
    records: List[Dict[str, Any]] = []
    for path in sorted(out_dir.glob("pboost_pint_*.json")):
        m = re.search(r"_pint_(\d+)\.json$", path.name)
        if not m:
            continue
        pint_code = float(m.group(1))  # e.g. 1400 -> 1.400 bar abs
        pint_bar = pint_code / 1000.0
        data = _load_json(path)
        bmep = data.get("bmep_bar")
        bsfc = data.get("bsfc_g_per_kWh")
        bp_kw = data.get("brake_power_kW")
        bt_Nm = data.get("brake_torque_Nm")
        if (
            bmep is None
            or bsfc is None
            or bp_kw is None
            or bt_Nm is None
        ):
            continue
        records.append(
            {
                "family": "pboost",
                "pint_bar": pint_bar,
                "bmep_bar": bmep,
                "brake_power_kW": bp_kw,
                "brake_torque_Nm": bt_Nm,
                "bsfc_g_per_kWh": bsfc,
                "source_file": path.name,
            }
        )
    return records


def _ensure_dir(path: Path) -> None:
    if path.is_dir():
        path.mkdir(parents=True, exist_ok=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)


def _write_csv(path: Path, records: List[Dict[str, Any]]) -> None:
    if not records:
        print(f"[BSFC] No records for {path.name}, skipping CSV.")
        return
    _ensure_dir(path)
    # Collect all keys seen so we don't accidentally drop columns
    fieldnames: List[str] = []
    for r in records:
        for k in r.keys():
            if k not in fieldnames:
                fieldnames.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in records:
            w.writerow(r)
    print(f"[BSFC] Wrote CSV table: {path}")


def _plot_full_load(html_path: Path, records: List[Dict[str, Any]]) -> None:
    if not records:
        print("[BSFC] No full-load records, skipping full-load plot.")
        return
    recs = sorted(records, key=lambda r: r["speed_rpm"])
    N = [r["speed_rpm"] for r in recs]
    bsfc = [r["bsfc_g_per_kWh"] for r in recs]
    bp_kw = [r["brake_power_kW"] for r in recs]
    bt_Nm = [r["brake_torque_Nm"] for r in recs]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=N,
            y=bp_kw,
            mode="lines+markers",
            name="Brake Power [kW]",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=N,
            y=bt_Nm,
            mode="lines+markers",
            name="Brake Torque [Nm]",
            yaxis="y2",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=N,
            y=bsfc,
            mode="lines+markers",
            name="BSFC [g/kWh]",
            yaxis="y3",
        )
    )

    fig.update_layout(
        title="Full-load virtual dyno – torque, power and BSFC vs speed",
        xaxis=dict(title="Speed [rpm]"),
        yaxis=dict(title="Brake Power [kW]"),
        yaxis2=dict(
            title="Brake Torque [Nm]",
            overlaying="y",
            side="right",
        ),
        yaxis3=dict(
            title="BSFC [g/kWh]",
            overlaying="y",
            side="right",
            anchor="free",
            position=0.05,
        ),
        legend=dict(x=0.01, y=0.99),
    )
    _ensure_dir(html_path)
    fig.write_html(str(html_path))
    print(f"[BSFC] Wrote full-load plot: {html_path}")


def _plot_pboost(html_path: Path, records: List[Dict[str, Any]]) -> None:
    if not records:
        print("[BSFC] No pboost records, skipping pboost plot.")
        return
    recs = sorted(records, key=lambda r: r["pint_bar"])
    pint = [r["pint_bar"] for r in recs]
    bmep = [r["bmep_bar"] for r in recs]
    bsfc = [r["bsfc_g_per_kWh"] for r in recs]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=bmep,
            y=bsfc,
            mode="lines+markers",
            text=[f"p_int={p:.3f} bar" for p in pint],
            name="BSFC vs BMEP (boost sweep)",
        )
    )
    fig.update_layout(
        title="Boosted intake sweep – BSFC vs BMEP",
        xaxis_title="BMEP [bar]",
        yaxis_title="BSFC [g/kWh]",
    )
    _ensure_dir(html_path)
    fig.write_html(str(html_path))
    print(f"[BSFC] Wrote pboost plot: {html_path}")


def main() -> None:
    out_dir = OUT_DIR
    full_load = _collect_full_load(out_dir)
    pboost = _collect_pboost(out_dir)

    # CSVs
    _write_csv(out_dir / "bsfc_full_load_table.csv", full_load)
    _write_csv(out_dir / "bsfc_pboost_table.csv", pboost)

    # Plots
    _plot_full_load(out_dir / "bsfc_full_load_plot.html", full_load)
    _plot_pboost(out_dir / "bsfc_pboost_plot.html", pboost)


if __name__ == "__main__":  # pragma: no cover
    main()
