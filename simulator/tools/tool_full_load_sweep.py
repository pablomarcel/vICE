from __future__ import annotations
import argparse
from pathlib import Path
from ..design import sweep_speed_full_load


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="simulator-full-load-sweep",
        description="Virtual dyno full-load speed sweep using the ICE simulator.",
    )
    p.add_argument("--config", required=True, help="Path to base JSON input file")
    p.add_argument(
        "--speeds",
        nargs="+",
        type=float,
        required=True,
        help="Engine speeds [rpm], e.g. 1500 2000 2500 3000",
    )
    p.add_argument(
        "--out-prefix",
        help="Output prefix for result JSON files (default: simulator/out/full_load)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    base_cfg = args.config
    if args.out_prefix:
        out_prefix = args.out_prefix
    else:
        root = Path(__file__).resolve().parents[1]
        out_prefix = str(root / "out" / "full_load")

    results = sweep_speed_full_load(base_cfg, args.speeds, out_prefix)
    print("[OK] Full-load sweep results:")
    for r in results:
        print(f"  {r.label:>8s} -> {r.outfile}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
