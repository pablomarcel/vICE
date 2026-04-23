from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from . import core, io


@dataclass
class RunRequest:
    verb: str
    params: Dict[str, Any] = field(default_factory=dict)
    infile: Optional[str] = None
    outfile: Optional[str] = None


@dataclass
class RunResult:
    ok: bool
    data: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""


def run(request: RunRequest) -> RunResult:
    """Dispatch high-level verbs for the simulator CLI / TUI.

    Currently supported verbs:
      - "run-sim": run a cycle simulation from JSON config
      - "list-inputs": list available JSON inputs under simulator/in
      - "plot-indicator": generate a P–V HTML plot from a result JSON
    """
    verb = request.verb
    try:
        if verb == "run-sim":
            if not request.infile:
                return RunResult(ok=False, reason="Missing infile for run-sim")
            cfg = io.load_json(request.infile)
            sim = core.EngineSimulator.from_dict(cfg)
            cycles = int(request.params.get("cycles", 1))
            result = sim.run(cycles=cycles)
            out_dict = result.to_dict()
            if request.outfile:
                io.ensure_dir_for(request.outfile)
                io.save_json(request.outfile, out_dict)
            return RunResult(
                ok=True,
                data={
                    "summary": sim.summary(result),
                    "result": out_dict,
                    "outfile": request.outfile,
                },
            )
        elif verb == "list-inputs":
            inputs = io.list_input_files()
            return RunResult(ok=True, data={"inputs": inputs})
        elif verb == "plot-indicator":
            result_path = request.params.get("result_path")
            if not result_path:
                return RunResult(ok=False, reason="Missing result_path for plot-indicator")
            out_html = request.params.get("out_html")
            if not out_html:
                out_html = io.default_plot_path(result_path, kind="pv")
            fig = io.plot_indicator_pv(result_path)
            io.ensure_dir_for(out_html)
            fig.write_html(out_html)
            print(f"[PLOT] Wrote indicator diagram to {out_html}")
            return RunResult(ok=True, data={"html": out_html})
        else:
            return RunResult(ok=False, reason=f"Unknown verb: {verb}")
    except Exception as exc:  # pragma: no cover - defensive
        return RunResult(ok=False, reason=str(exc))
