from __future__ import annotations
from pathlib import Path
import json
from simulator import cli


def test_cli_run_smoke(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1]
    cfg_path = root / "in" / "sample_si_engine.json"
    out_path = tmp_path / "result.json"
    exit_code = cli.main([
        "run",
        "--config", str(cfg_path),
        "--outfile", str(out_path),
        "--cycles", "1",
    ])
    assert exit_code == 0
    assert out_path.exists()
    data = json.loads(out_path.read_text())
    assert "crank_deg" in data
    assert "pressure_Pa" in data
