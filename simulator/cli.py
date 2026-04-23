from __future__ import annotations
import argparse
from typing import Sequence
from . import apis


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="simulator",
        description="ICE Simulator – GM-style single-cylinder engine",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run a simulation from a JSON input file")
    run_p.add_argument("--config", required=True, help="Path to JSON input file")
    run_p.add_argument("--outfile", required=True, help="Path to output JSON file")
    run_p.add_argument(
        "--cycles", type=int, default=1, help="Number of engine cycles to simulate"
    )

    sub.add_parser("list-inputs", help="List example JSON input files")

    plot_p = sub.add_parser(
        "plot", help="Plot an indicator diagram from a result JSON file"
    )
    plot_p.add_argument("--result", required=True, help="Path to result JSON file")
    plot_p.add_argument(
        "--html", help="Output HTML path (default: next to result JSON)"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "run":
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
        res = apis.run(apis.RunRequest(verb="list-inputs"))
        if not res.ok:
            parser.error(res.reason)
        for path in res.data.get("inputs", []):
            print(path)
        return 0
    if args.command == "plot":
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
