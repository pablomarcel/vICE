from __future__ import annotations
from pathlib import Path
from .. import io


def main() -> None:
    import sys

    if len(sys.argv) != 2:
        raise SystemExit(f"Usage: {Path(sys.argv[0]).name} RESULT_JSON")

    result_path = Path(sys.argv[1])
    fig = io.plot_indicator_pv(result_path)
    out_html = io.default_plot_path(result_path, kind="pv")
    io.ensure_dir_for(out_html)
    fig.write_html(out_html)
    print(f"[OK] Wrote indicator diagram to: {out_html}")


if __name__ == "__main__":  # pragma: no cover
    main()
