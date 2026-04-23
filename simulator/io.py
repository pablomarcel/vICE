from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List
import plotly.graph_objects as go
from . import utils

ROOT = Path(__file__).resolve().parent
IN_DIR = ROOT / "in"
OUT_DIR = ROOT / "out"


def ensure_dir_for(path: str | Path) -> None:
    utils.ensure_dir(path)


def load_json(path: str | Path) -> Dict[str, Any]:
    data = utils.load_json(path)
    print(f"[IO] Loaded JSON from {path}")
    return data


def save_json(path: str | Path, data: Dict[str, Any]) -> None:
    utils.save_json(path, data)
    print(f"[IO] Wrote JSON to {path}")


def list_input_files() -> List[str]:
    if not IN_DIR.exists():
        return []
    return sorted(str(p) for p in IN_DIR.glob("*.json"))


def default_plot_path(result_path: str | Path, kind: str = "pv") -> str:
    result_path = Path(result_path)
    stem = result_path.stem
    return str(result_path.with_name(f"{stem}_{kind}.html"))


def plot_indicator_pv(result_path: str | Path) -> go.Figure:
    data = load_json(result_path)
    v = data.get("volume_m3", [])
    p = data.get("pressure_Pa", [])
    if not v or not p:
        raise ValueError("Result file does not contain volume_m3/pressure_Pa arrays")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=v, y=[pi / 1e5 for pi in p], mode="lines", name="Cycle"))
    fig.update_layout(
        title="Indicator Diagram (P-V)",
        xaxis_title="Volume [m^3]",
        yaxis_title="Pressure [bar]",
    )
    return fig
