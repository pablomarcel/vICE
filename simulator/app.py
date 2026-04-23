from __future__ import annotations
from pathlib import Path
from . import apis

try:
    from pyfiglet import Figlet
except Exception:  # pragma: no cover
    Figlet = None  # type: ignore[assignment]


class ICESimulatorApp:
    """Simple text-based front-end for the ICE simulator.

    This is deliberately console-first so it's easy to wrap with
    richer UIs later (PySide6, Tk, web, etc.).
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parent
        self.in_dir = self.root / "in"
        self.out_dir = self.root / "out"

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------
    def _print_banner(self) -> None:
        title = "ICE Simulator"
        if Figlet is not None:
            fig = Figlet(font="slant")
            print(fig.renderText(title))
        else:
            print(title)
            print("-" * len(title))

    def _print_menu(self) -> None:
        print("=" * 70)
        print("[MAIN MENU] Select an action:")
        print("  1) List example input cases")
        print("  2) Run simulation from JSON input")
        print("  3) Plot indicator diagram (P-V) from result")
        print("  4) Quit")
        print("=" * 70)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def run_main_menu(self) -> None:
        self._print_banner()
        while True:
            self._print_menu()
            choice = input("Enter option [1-4]: ").strip()
            if choice == "1":
                self._menu_list_inputs()
            elif choice == "2":
                self._menu_run_simulation()
            elif choice == "3":
                self._menu_plot_indicator()
            elif choice == "4":
                print("[OK] Exiting ICE Simulator. Bye.")
                return
            else:
                print("[WARN] Invalid choice, please select 1-4.")

    # ------------------------------------------------------------------
    # Menu actions
    # ------------------------------------------------------------------
    def _menu_list_inputs(self) -> None:
        res = apis.run(apis.RunRequest(verb="list-inputs"))
        if not res.ok:
            print(f"[ERROR] Could not list inputs: {res.reason}")
            return
        inputs = res.data.get("inputs", [])
        if not inputs:
            print(f"[INFO] No JSON input files found in '{self.in_dir}'.")
            return
        print("\n[INFO] Available input cases:")
        for i, path in enumerate(inputs, start=1):
            print(f"  {i:2d}) {path}")
        print(f"[OK] Listed {len(inputs)} case(s).")

    def _menu_run_simulation(self) -> None:
        default_in = self.in_dir / "sample_si_engine.json"
        path = input(f"Path to JSON input file [default: {default_in}]: ").strip()
        if not path:
            path = str(default_in)
        default_out = self.out_dir / f"{Path(path).stem}_out.json"
        outfile = input(f"Path to output JSON [default: {default_out}]: ").strip()
        if not outfile:
            outfile = str(default_out)
        req = apis.RunRequest(verb="run-sim", infile=path, outfile=outfile)
        res = apis.run(req)
        if not res.ok:
            print(f"[ERROR] Simulation failed: {res.reason}")
            return
        print("[OK] Simulation complete.")
        print(f"     Input : {path}")
        print(f"     Output: {outfile}")
        summary = res.data.get("summary", {})
        if summary:
            print("     Summary:")
            for k, v in summary.items():
                print(f"       - {k}: {v}")

    def _menu_plot_indicator(self) -> None:
        result_path = input("Path to result JSON: ").strip()
        if not result_path:
            print("[WARN] Result JSON path is required.")
            return
        out_html = input("Path to HTML plot [default: next to JSON]: ").strip()
        params = {"result_path": result_path}
        if out_html:
            params["out_html"] = out_html
        res = apis.run(apis.RunRequest(verb="plot-indicator", params=params))
        if not res.ok:
            print(f"[ERROR] Plotting failed: {res.reason}")
            return
        print(f"[OK] Indicator diagram written to: {res.data.get('html')}")


def run() -> None:
    ICESimulatorApp().run_main_menu()
