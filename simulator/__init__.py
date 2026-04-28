from __future__ import annotations

"""vICE simulator package.

The package root intentionally avoids importing optional plotting or GUI
libraries at import time. This keeps lightweight CLI subcommands such as the
pump analyzers fast and robust even when optional dependencies are absent.
"""


def main() -> None:
    from .main import main as _main
    _main()


__all__ = ["main"]
