# RUNS — `ice/simulator` Command Cookbook (v1)

Run these from the **ICE root** (the directory that contains `simulator/`).  
Outputs default to `simulator/out/`.

> CLI
>
> ```bash
> runroot python -m simulator.cli [run|list-inputs|plot] ...
> ```
>
> The sections below assume you have a `runroot` helper set up.

## -1) One-time session bootstrap (ICE-aware)

Define a small helper so you can run commands from anywhere inside the repo:

```bash
# --- run-from-root helpers (ICE-aware) -------------------------------------
_sim_root() {
  # Walk up until we find a directory that *contains* the simulator package.
  local d="$PWD"
  while [ "$d" != "/" ]; do
    if [ -d "$d/simulator" ] && [ -f "$d/simulator/__init__.py" ]; then
      echo "$d"; return
    fi
    # Monorepo layout: .../repo/ice/simulator
    if [ -d "$d/ice/simulator" ] && [ -f "$d/ice/simulator/__init__.py" ]; then
      echo "$d/ice"; return
    fi
    d="$(dirname "$d")"
  done
  # Last resort: Git top-level
  if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git rev-parse --show-toplevel
    return
  fi
  echo "$PWD"
}
runroot() { ( cd "$(_sim_root)" && "$@" ); }
runroot mkdir -p simulator/out simulator/in
```

## 0) Help

```bash
runroot python -m simulator.cli \
  --help
```

## 1) Text UI (Simulator console front-end)

Interactive menu: list inputs, run a case, plot indicator diagram.

```bash
runroot python -m simulator.main
```

## 2) List available JSON input cases

```bash
runroot python -m simulator.cli list-inputs
```

You should see paths under `simulator/in/`, e.g.:

- `simulator/in/sample_si_engine.json`
- `simulator/in/sample_si_methanol_engine.json`
- `simulator/in/template_si_engine.json` (after step 3)

## 3) Seed a template SI engine input

One-time helper: write a generic SI case you can clone/edit.

```bash
runroot python -m simulator.tools.tool_generate_template_input
```

This creates:

- `simulator/in/template_si_engine.json`

## 4) Baseline gasoline SI case (single cylinder) — run + plot

Run one 4‑stroke cycle using the sample gasoline config, then plot the P–V loop.

```bash
runroot python -m simulator.cli run \
  --config simulator/in/sample_si_engine.json \
  --outfile simulator/out/sample_si_engine_out.json \
  --cycles 1
```

```bash
runroot python -m simulator.cli plot \
  --result simulator/out/sample_si_engine_out.json
```

Or using the lower-level tool:

```bash
runroot python -m simulator.tools.tool_indicator_from_result simulator/out/sample_si_engine_out.json
```

## 5) Methanol comparison (same geometry, different fuel)

Assuming you have a methanol case in `simulator/in/sample_si_methanol_engine.json`
(same geometry, `fuel_id: "methanol"`):

# Step 1 - Solve - Indicator Diagram

```bash
runroot python -m simulator.cli run \
  --config simulator/in/sample_si_methanol_engine.json \
  --outfile simulator/out/methanol_out.json \
  --cycles 1
```

# Step 2 - Plot - Indicator Diagram

```bash
runroot python -m simulator.cli plot \
  --result simulator/out/methanol_out.json
```

Compare:

- peak pressure,
- IMEP/BMEP,
- indicated / brake power and torque,
driven by different LHV and AFR.

## 6) Multi‑cycle run (stability check / repeated P–V loops)

Run several cycles in one shot to check repeatability of the indicator diagram
and integrated work.

```bash
runroot python -m simulator.cli run \
  --config simulator/in/sample_si_engine.json \
  --outfile simulator/out/sample_si_engine_3cyc_out.json \
  --cycles 3
```

```bash
runroot python -m simulator.cli plot \
  --result simulator/out/sample_si_engine_3cyc_out.json
```

The `SimulationResult` still reports IMEP / power / torque based on a
**per‑cycle** normalization; total work is internally divided by the number
of simulated cycles.

## 7) Cylinder‑count effect — 1‑cyl vs 4‑cyl at fixed IMEP

Use the same per‑cylinder thermodynamics but vary `num_cylinders` to show
how **total** brake power / torque scale with cylinder count, while
per‑cylinder values stay nearly constant.

```bash
runroot python - << 'PY'
from simulator import io
from simulator.core import EngineSimulator

base_cfg = io.load_json("simulator/in/sample_si_engine.json")

for n_cyl in [1, 4]:
    cfg = dict(base_cfg)
    op = cfg.setdefault("operating", {})
    op["num_cylinders"] = n_cyl
    sim = EngineSimulator.from_dict(cfg)
    result = sim.run(cycles=1)
    print(f"{n_cyl} cyl -> "
          f"Pb_total = {result.brake_power_kW:6.2f} kW, "
          f"T_total = {result.brake_torque_Nm:7.2f} N·m, "
          f"T_per_cyl = {result.brake_torque_per_cyl_Nm:7.2f} N·m")
PY
```

This is a nice “so‑what” demo: **same IMEP**, but total power/torque scale
with cylinder count, which is exactly what you’d discuss in a performance
/ architecture review.

## 8) Friction presets — passenger vs performance vs F1‑ish

If you’re using the FMEP presets version of `core.py` with `friction_mode`
support (`"passenger"`, `"performance"`, `"f1"`, `"generic"`), you can
quickly sweep different friction maps over the **same** pressure trace
and show how brake power / torque shift.

```bash
runroot python - << 'PY'
from simulator import io
from simulator.core import EngineSimulator

base_cfg = io.load_json("simulator/in/sample_si_engine.json")

modes = ["passenger", "performance", "f1"]
for mode in modes:
    cfg = dict(base_cfg)
    op = cfg.setdefault("operating", {})
    op["friction_model"] = "fmep-speed"
    op["friction_mode"] = mode
    sim = EngineSimulator.from_dict(cfg)
    result = sim.run(cycles=1)
    print(f"mode={mode:11s}  "
          f"IMEP={result.imep_bar:5.2f} bar  "
          f"BMEP={result.bmep_bar:5.2f} bar  "
          f"Pb={result.brake_power_kW:6.2f} kW  "
          f"T_b={result.brake_torque_Nm:7.2f} N·m  "
          f"η_mech={result.mechanical_efficiency_effective:5.3f}")
PY
```

Talking point with a performance team: you’re holding combustion / IMEP
roughly fixed and showing how **friction strategy** (passenger vs
performance vs F1‑ish) eats into BMEP and Pb.

If `friction_mode` isn’t wired yet on your branch, this block simply
needs the updated `core.py` that defines it.

## 9) Intake‑pressure sweep (boost / operating‑point study)

Use the small design helper to sweep intake pressure and see how BMEP /
brake power respond — a mini performance map slice.

```bash
runroot python - << 'PY'
from pathlib import Path
from simulator.design import sweep_intake_pressure
from simulator.io import load_json

base_cfg = "simulator/in/sample_si_engine.json"
pressures = [80_000.0, 90_000.0, 101_325.0, 120_000.0, 140_000.0, 160_000.0, 180_000.0, 200_000.0, 220_000.0, 240_000.0, 260_000.0, 280_000.0, 300_000.0, 320_000.0, 340_000.0, 360_000.0, 380_000.0, 400_000.0]

results = sweep_intake_pressure(
    base_config_path=base_cfg,
    pressures_Pa=pressures,
    out_prefix="simulator/out/pboost"
)

print("Intake pressure sweep (per-cylinder BMEP & total Pb):")
for r in results:
    data = load_json(r.outfile)
    bmep = data.get("bmep_bar", float("nan"))
    pb_kw = data.get("brake_power_kW", float("nan"))
    print(f"  {r.label:>8s}:  BMEP={bmep:5.2f} bar,  Pb={pb_kw:6.2f} kW")
PY
```

This is a good hook for talking about **boost strategy** and how an OEM or an
F1 customer might explore intake‑side changes without rewriting the core
solver.

## 10) Quick JSON peek (scalar sanity check)

To quickly inspect the scalar fields (IMEP, BMEP, power, torque) from a
previous run:

```bash
runroot python - << 'PY'
from simulator.io import load_json
data = load_json("simulator/out/sample_si_engine_out.json")
keys = [
    "imep_bar", "bmep_bar",
    "indicated_power_kW", "brake_power_kW",
    "indicated_torque_Nm", "brake_torque_Nm",
    "mechanical_efficiency_effective",
]
for k in keys:
    if k in data:
        print(f"{k:32s} : {data[k]}")
PY
```

# Annex — Dyno-style sweeps & combustion metrics (v1)

## A1) Single-cycle indicated demo — gasoline
```bash
runroot python -m simulator.cli run \
  --config simulator/in/sample_si_engine.json \
  --outfile simulator/out/sample_si_engine_out.json
```

```bash
runroot python -m simulator.cli plot \
  --result simulator/out/sample_si_engine_out.json
```

## A2) Multi-cycle stability demo (CoV(IMEP), knock index proxy)
```bash
runroot python -m simulator.cli run \
  --config simulator/in/sample_si_engine.json \
  --outfile simulator/out/sample_si_engine_3cyc_out.json \
  --cycles 3
```

```bash
runroot python -m simulator.cli plot \
  --result simulator/out/sample_si_engine_3cyc_out.json
```

## A3) Fuel comparison — gasoline vs methanol

# Step 1 - Solve - Gasoline - Indicator Diagram

```bash
runroot python -m simulator.cli run \
  --config simulator/in/sample_si_engine.json \
  --outfile simulator/out/gasoline_out.json
```

# Step 2 - Plot - Gasoline - Indicator Diagram

```bash
runroot python -m simulator.cli plot \
  --result simulator/out/gasoline_out.json
```

# Step 1 - Solve - Methanol - Indicator Diagram

```bash
runroot python -m simulator.cli run \
  --config simulator/in/sample_si_methanol_engine.json \
  --outfile simulator/out/methanol_out.json
```

# Step 2 - Plot - Methanol - Indicator Diagram

```bash
runroot python -m simulator.cli plot \
  --result simulator/out/methanol_out.json
```

## A4) Full-load virtual dyno sweep

```bash
runroot python -m simulator.tools.tool_full_load_sweep \
  --config simulator/in/sample_si_engine.json \
  --speeds 500 1000 1500 2000 2500 3000 3500 4000 4500 5000 5500 6000 6500 7000 7500 8000
```

```bash
runroot python -m simulator.tools.tool_full_load_sweep \
  --config simulator/in/sample_si_engine_turbo_4cyl.json \
  --speeds 500 1000 1500 2000 2500 3000 3500 4000 4500 5000 5500 6000 6500 7000 7500 8000
```

```bash
runroot python -m simulator.tools.tool_full_load_sweep \
  --config simulator/in/sample_si_engine_turbo_8cyl.json \
  --speeds 500 1000 1500 2000 2500 3000 3500 4000 4500 5000 5500 6000 6500 7000 7500 8000
```

```bash
runroot python -m simulator.tools.tool_full_load_sweep \
  --config simulator/in/sample_si_engine_turbo_12cyl.json \
  --speeds 500 1000 1500 2000 2500 3000 3500 4000 4500 5000 5500 6000 6500 7000 7500 8000
```

## Quick BSFC / full-load summary, mimicking a dyno “curve fit” table:

```bash
runroot python - << 'PY'
from pathlib import Path
import json, re

root = Path("simulator/out")
for path in sorted(root.glob("full_load_N_*.json")):
    m = re.search(r"_N_(\d+)\.json$", path.name)
    if not m:
        continue
    N = int(m.group(1))
    with path.open() as f:
        data = json.load(f)
    bmep = data.get("bmep_bar")
    bsfc = data.get("bsfc_g_per_kWh")
    bp_kw = data.get("brake_power_kW")
    bt = data.get("brake_torque_Nm")
    print(f"{N:5d} rpm  BMEP={bmep:6.2f} bar  "
          f"BP={bp_kw:7.2f} kW  BT={bt:7.2f} Nm  BSFC={bsfc:7.1f} g/kWh")
PY
```

## A5) Motored sweep (virtual motoring test)

```bash
runroot python - << 'PY'
from simulator.design import sweep_speed_motored
res = sweep_speed_motored(
    "simulator/in/sample_si_engine.json",
    [500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000, 5500, 6000, 6500, 7000, 7500, 8000],
    "simulator/out/motored"
)
for r in res:
    print(f"{r.label:>14s} -> {r.outfile}")
PY
```

## A6) Intake-pressure (“boost”) sweep

```bash
runroot python - << 'PY'
from simulator.design import sweep_intake_pressure
pressures = [80e3, 90e3, 101.3e3, 120e3, 140e3]
res = sweep_intake_pressure(
    "simulator/in/sample_si_engine.json",
    pressures,
    "simulator/out/pboost"
)
for r in res:
    print(f"{r.label:>8s} -> {r.outfile}")
PY
```

## X) BSFC tables & plots from virtual dyno outputs

# Build CSV tables and Plotly HTML plots from:
#   - simulator/out/full_load_N_*.json
#   - simulator/out/pboost_pint_*.json
#
# Outputs:
#   - simulator/out/bsfc_full_load_table.csv
#   - simulator/out/bsfc_pboost_table.csv
#   - simulator/out/bsfc_full_load_plot.html
#   - simulator/out/bsfc_pboost_plot.html

# Bsfc vs BMEP

```bash
runroot python -m simulator.tools.tool_bsfc_table
```

# η_th contour maps - intake pressure vs RPM

```bash
runroot python -m simulator.tools.tool_bsfc_contours
```

# BSFC vs RPM - Compression Ratio Sweep

```bash
runroot python -m simulator.tools.tool_bsfc_vs_speed_rc
```

# BSFC vs Equivalence Ratio - Compression Ratio Sweep

```bash
runroot python -m simulator.tools.tool_bsfc_vs_phi_rc
```

# BSFC vs Displacement

```bash
runroot python -m simulator.tools.tool_bsfc_vs_displacement
```

## BSFC new commands

```bash
runroot python -m simulator.cli run \
  --config simulator/in/sample_si_engine_phi0.9.json \
  --outfile simulator/out/si_phi0.9_out.json
```

```bash
runroot python -m simulator.cli run \
  --config simulator/in/sample_si_engine_phi1.0.json \
  --outfile simulator/out/si_phi1.0_out.json
```

```bash
runroot python -m simulator.cli run \
  --config simulator/in/sample_si_engine_phi1.1.json \
  --outfile simulator/out/si_phi1.1_out.json
```

# Full BSFC vs phi map for rc = 8..15

```bash
runroot python -m simulator.tools.bsfc_sweep_phi \
  --config simulator/in/sample_si_engine.json \
  --out-csv simulator/out/bsfc_vs_phi_rc8_15.csv \
  --out-html simulator/out/bsfc_vs_phi_rc8_15.html
```

# If you want only three compression ratios, say 8, 10, 12:

```bash
runroot python -m simulator.tools.bsfc_sweep_phi \
  --config simulator/in/sample_si_engine.json \
  --out-csv simulator/out/bsfc_vs_phi_rc8_10_12.csv \
  --out-html simulator/out/bsfc_vs_phi_rc8_10_12.html \
  --rc "8,10,12"
```

```bash
runroot python -c 'import cantera; print(cantera.__version__)'
```

## T1) Ideal adiabatic flame vs φ (gasoline, toy cp model)

```bash
runroot python -m simulator.thermo.tools.equilibrium_flame \
  --fuel-id gasoline \
  --backend ideal \
  --phi-start 0.6 \
  --phi-stop 1.4 \
  --phi-step 0.05 \
  --pressure-Pa 101325 \
  --Tin-K 298.15 \
  --out-json simulator/out/flame_gasoline_phi_ideal.json \
  --out-html simulator/out/flame_gasoline_phi_ideal.html
```

## T2) Cantera HP-equilibrium adiabatic flame vs φ (methane, gri30)

```bash
runroot python -m simulator.thermo.tools.equilibrium_flame \
  --fuel-id methane \
  --backend cantera \
  --mech gri30.yaml \
  --fuel-species CH4 \
  --phi-start 0.6 \
  --phi-stop 1.4 \
  --phi-step 0.05 \
  --pressure-Pa 101325 \
  --Tin-K 298.15 \
  --out-json simulator/out/flame_methane_phi_cantera.json \
  --out-html simulator/out/flame_methane_phi_cantera.html
```

# Ideal backend, gasoline vs methanol vs E85 - Adiabatic Flame Temperature

```bash
runroot python -m simulator.thermo.tools.equilibrium_flame_compare \
  --fuel-ids gasoline,methanol,e85 \
  --backend ideal \
  --phi-start 0.6 \
  --phi-stop 1.4 \
  --phi-step 0.05 \
  --pressure-Pa 101325 \
  --Tin-K 298.15 \
  --out-json simulator/out/flame_compare_ideal.json \
  --out-html simulator/out/flame_compare_ideal.html
```

# Ideal backend, gasoline vs methanol vs E85 vs Ethanol - Adiabatic Flame Temperature

```bash
runroot python -m simulator.thermo.tools.equilibrium_flame_compare \
  --fuel-ids gasoline,methanol,e85,ethanol \
  --backend ideal \
  --phi-start 0.6 \
  --phi-stop 1.4 \
  --phi-step 0.05 \
  --pressure-Pa 101325 \
  --Tin-K 298.15 \
  --out-json simulator/out/flame_compare_ideal_gas_meth_e85_etoh.json \
  --out-html simulator/out/flame_compare_ideal_gas_meth_e85_etoh.html
```

# Cantera Backend, Methane vs Propane - Adiabatic Flame Temperature vs Equivalence Ratio

```bash
runroot python -m simulator.thermo.tools.equilibrium_flame_compare \
  --fuel-ids methane,propane \
  --backend cantera \
  --mech gri30.yaml \
  --fuel-species CH4,C3H8 \
  --phi-start 0.6 \
  --phi-stop 1.4 \
  --phi-step 0.05 \
  --pressure-Pa 101325 \
  --Tin-K 298.15 \
  --out-json simulator/out/flame_compare_cantera.json \
  --out-html simulator/out/flame_compare_cantera.html
```

# Cantera Backend, Methane vs Hydrogen - Adiabatic Flame Temperature vs Equivalence Ratio

```bash
runroot python -m simulator.thermo.tools.equilibrium_flame_compare \
  --fuel-ids methane,hydrogen \
  --backend cantera \
  --mech gri30.yaml \
  --fuel-species CH4,H2 \
  --phi-start 0.6 \
  --phi-stop 1.4 \
  --phi-step 0.05 \
  --pressure-Pa 101325 \
  --Tin-K 298.15 \
  --out-json simulator/out/flame_compare_cantera_CH4_H2.json \
  --out-html simulator/out/flame_compare_cantera_CH4_H2.html
```

# Cantera backend, Methane vs Carbon Monoxide - Adiabatic Flame Temperature vs Equivalence Ratio

```bash
runroot python -m simulator.thermo.tools.equilibrium_flame_compare \
  --fuel-ids methane,carbon_monoxide \
  --backend cantera \
  --mech gri30.yaml \
  --fuel-species CH4,CO \
  --phi-start 0.6 \
  --phi-stop 1.4 \
  --phi-step 0.05 \
  --pressure-Pa 101325 \
  --Tin-K 298.15 \
  --out-json simulator/out/flame_compare_cantera_CH4_CO.json \
  --out-html simulator/out/flame_compare_cantera_CH4_CO.html
```

# Cantera backend, Hydrogen vs Carbon Monoxide - Adiabatic Flame Temperature vs Equivalence Ratio

```bash
runroot python -m simulator.thermo.tools.equilibrium_flame_compare \
  --fuel-ids hydrogen,carbon_monoxide \
  --backend cantera \
  --mech gri30.yaml \
  --fuel-species H2,CO \
  --phi-start 0.6 \
  --phi-stop 1.4 \
  --phi-step 0.05 \
  --pressure-Pa 101325 \
  --Tin-K 298.15 \
  --out-json simulator/out/flame_compare_cantera_H2_CO.json \
  --out-html simulator/out/flame_compare_cantera_H2_CO.html
```

## Flame Summary - Bsfc vs RPM

```bash
runroot python -m simulator.tools.tool_flame_summary \
  --pattern "simulator/out/full_load_N_*.json" \
  --fuel-id gasoline \
  --backend ideal \
  --pressure-Pa 101325 \
  --Tin-K 298.15 \
  --out-csv simulator/out/flame_summary_gasoline.csv \
  --out-html simulator/out/flame_summary_gasoline.html
```

# Cycle - P, T vs Crank Angle

```bash
runroot python -m simulator.tools.tool_cycle_thermo_plot \
  --infile simulator/out/si_phi0.9_out.json \
  --out-html simulator/out/si_phi0.9_cycle_thermo.html
```

# Default Baby F1 engine (gasoline) - Bsfc

```bash
runroot python -m simulator.tools.tool_bsfc_map_epa
```

# Baby F1 engine (methanol) - Bsfc

```bash
runroot python -m simulator.tools.tool_bsfc_map_epa \
  --config simulator/in/sample_si_methanol_engine.json \
  --html simulator/out/methanol_bsfc_map_epa.html \
  --csv simulator/out/methanol_bsfc_map_epa_points.csv
```

# Baby F1 engine (e85) - Bsfc

```bash
runroot python -m simulator.tools.tool_bsfc_map_epa \
  --config simulator/in/sample_si_e85_engine.json \
  --html simulator/out/e85_bsfc_map_epa.html \
  --csv simulator/out/e85_bsfc_map_epa_points.csv
```

# vICE – Turbocharger Add‑On (Mean‑Value v0)

This add‑on bolts a **very simple turbocharger model** onto the existing
`simulator` package *without* touching your core combustion / BSFC code.

It is intentionally mean‑value and algebraic (no shaft dynamics, no real
compressor / turbine maps yet) but it gives you:

* A `turbo` block in your JSON config to describe a generic turbo setup.
* A steady‑state “virtual dyno” that compares **NA vs turbocharged**
  torque / power / BSFC vs speed for a given engine.
* A basic compressor “operating line” plot: corrected mass flow vs
  pressure ratio, coloured by RPM.

The idea is to give you a **framework and patterns** that match the rest
of your app, so you can later swap in real compressor / turbine maps or
more detailed physics.

## 1. Config – new `turbo` block

In your existing engine JSON (e.g. `simulator/in/sample_si_engine.json`)
add an optional block:

```jsonc
{
  "geometry": {
    "...": "..."
  },
  "operating": {
    "fuel_id": "gasoline",
    "engine_speed_rpm": 4500,
    "intake_pressure_Pa": 101300.0,
    "intake_temperature_K": 298.15,
    "num_cylinders": 4,
    "stroke_type": "4-stroke",
    "volumetric_efficiency": 0.90
  },
  "turbo": {
    "enabled": true,
    "p_amb_bar": 1.013,
    "T_amb_K": 298.15,

    // Target manifold pressure behaviour
    "p_manifold_target_bar": 2.0,         // design full‑boost manifold pressure
    "N_idle_rpm": 1000.0,                 // below this → PR ≈ 1.0 (no boost)
    "N_full_boost_rpm": 2000.0,           // above this → PR ≈ p_manifold_target/p_amb

    // Simple compressor model
    "compressor_efficiency": 0.72,
    "gamma_air": 1.40,
    "cp_air_J_per_kgK": 1005.0,

    // Simple intercooler model (effectiveness ε)
    "intercooler_effectiveness": 0.70,

    // Volumetric efficiency used for ṁ estimation (fallback to operating block)
    "volumetric_efficiency": 0.90
  }
}
```

Notes:

* All fields are **optional**. Reasonable defaults are applied if missing.
* Nothing in your existing simulator depends on the `turbo` block, so
  current tests / runs remain unchanged until you call the new tools.

## 2. New module: `simulator/turbo.py`

This module implements:

* `TurboConfig` – dataclass built from your JSON.
* `TurboMatchPoint` – one steady‑state operating point (one speed).
* `compute_boost_schedule` – maps engine speed → compressor pressure ratio.
* `match_turbo_over_speeds` – outer loop that:
    1. Computes manifold pressure & temperature from the turbo model.
    2. Estimates mass flow from geometry, VE and intake state.
    3. Calls `EngineSimulator.from_dict(...)` with overridden
       `intake_pressure_Pa` and `intake_temperature_K`.
    4. Returns NA vs turbo results (torque, power, BSFC, etc.).

The physics is deliberately light‑weight (constant γ, constant η_c,
no turbine power balance yet). The goal is to keep it **transparent and
hackable** so you can later:

* Add a `T_turbine_in_K` model vs load.
* Add a turbine map & power balance `W_t η_m = W_c`.
* Replace the simple boost schedule with a map‑based or control‑based one.

## 3. New CLI tool: `simulator.tools.turbo_match`

This CLI is patterned after your existing tools (`tool_bsfc_map_epa.py`,
`tool_bsfc_vs_speed_rc.py`, etc.) and is meant to be run from the ICE root
using your usual `runroot` helper.

### Turbo - Compressor Matching

```bash
runroot python -m simulator.tools.turbo_match \
  --config simulator/in/sample_si_engine_turbo.json \
  --speeds 1500 2000 2500 3000 3500 4000 4500 5000 5500 6000 \
  --out-json simulator/out/turbo_match_demo.json \
  --out-html simulator/out/turbo_match_demo.html \
  --out-compressor-html simulator/out/turbo_compressor_opline.html
```

This will:

1. Build a baseline **naturally‑aspirated** curve using your original
   `intake_pressure_Pa` and `intake_temperature_K` from the JSON.
2. Build a **turbocharged** curve using the `turbo` block to compute
   manifold pressure / temperature vs RPM.
3. Call `EngineSimulator` for each speed in both NA and turbo modes.
4. Save a JSON table with all points.
5. Write a Plotly HTML file with:
     * Torque vs RPM (NA vs turbo)
     * BMEP vs RPM
     * BSFC vs RPM
     * Manifold pressure vs RPM
6. Write a second HTML file with a **compressor operating line** plot:
     * x = corrected air mass flow
     * y = pressure ratio
     * markers coloured by RPM

## 4. Extending this skeleton

Once this is wired and producing sensible trends, you can iterate:

* Add a simple turbine model and enforce `W_t η_m = W_c` instead of the
  current “prescribed boost schedule”.
* Swap the internal `compute_boost_schedule` for a map‑based solver using
  real BorgWarner / Garrett compressor maps (JSON inputs).
* Add new CLI verbs like:
    * `turbo-compressor-opline` → plot only the compressor operating line.
    * `turbo-turbine-opline`   → turbine swallowing / map plot.
* Cross‑link this with your existing BSFC and EPA‑style tools to overlay
  NA and turbo maps.

This v0 keeps all turbo logic outside your existing combustion / cycle
model, so you can freely refactor it without touching core tests.

# Turbochargers

## Turbo matching

```bash
runroot python -m simulator.tools.tool_turbo_match_opline \
  --config simulator/in/sample_si_engine_turbo.json \
  --out simulator/out/turbo_match_opline.csv \
  --N-min 1500 \
  --N-max 6000 \
  --N-step 500
```

# Turbo matching - 4cyl

```bash
runroot python -m simulator.tools.tool_turbo_match_opline \
  --config simulator/in/sample_si_engine_turbo_4cyl.json \
  --out simulator/out/turbo_match_opline_4cyl.csv \
  --N-min 1500 \
  --N-max 6000 \
  --N-step 500
```

# Turbo matching - 8cyl

```bash
runroot python -m simulator.tools.tool_turbo_match_opline \
  --config simulator/in/sample_si_engine_turbo_8cyl.json \
  --out simulator/out/turbo_match_opline_8cyl.csv \
  --N-min 1500 \
  --N-max 6000 \
  --N-step 500
```

# Turbo matching - 12cyl

```bash
runroot python -m simulator.tools.tool_turbo_match_opline \
  --config simulator/in/sample_si_engine_turbo_12cyl.json \
  --out simulator/out/turbo_match_opline_12cyl.csv \
  --N-min 1500 \
  --N-max 6000 \
  --N-step 500
```

## Compressors

```bash
runroot python -m simulator.tools.tool_compressor_map_efr71 \
  --csv simulator/in/compressor_efr71_grid.csv \
  --speed-lines-csv simulator/in/compressor_efr71_speed_lines.csv \
  --out-html simulator/out/compressor_efr71_map.html
```

  # optional:
  # --opline-csv simulator/out/turbo_match_opline.csv

```bash
runroot python -m simulator.tools.tool_compressor_map_efr71 \
  --csv simulator/in/compressor_efr71_grid.csv \
  --speedlines-csv simulator/in/compressor_efr71_speedlines.csv \
  --opline-csv simulator/out/turbo_match_opline.csv \
  --out-html simulator/out/compressor_efr71_map.html
```

# Compressor matching - 4cyl

```bash
runroot python -m simulator.tools.tool_compressor_map_efr71 \
  --csv simulator/in/compressor_efr71_grid.csv \
  --speedlines-csv simulator/in/compressor_efr71_speedlines.csv \
  --opline-csv simulator/out/turbo_match_opline_4cyl.csv \
  --out-html simulator/out/compressor_efr71_map_4cyl.html
```

# Compressor matching - 8cyl

```bash
runroot python -m simulator.tools.tool_compressor_map_efr71 \
  --csv simulator/in/compressor_efr71_grid.csv \
  --speedlines-csv simulator/in/compressor_efr71_speedlines.csv \
  --opline-csv simulator/out/turbo_match_opline_8cyl.csv \
  --out-html simulator/out/compressor_efr71_map_8cyl.html
```

# Compressor matching - 12cyl

```bash
runroot python -m simulator.tools.tool_compressor_map_efr71 \
  --csv simulator/in/compressor_efr71_grid.csv \
  --speedlines-csv simulator/in/compressor_efr71_speedlines.csv \
  --opline-csv simulator/out/turbo_match_opline_12cyl.csv \
  --out-html simulator/out/compressor_efr71_map_12cyl.html
```

## Turbos

# Plot

```bash
runroot python -m simulator.tools.tool_turbine_map_gt4088 \
  --csv simulator/in/turbine_gt4088_like.csv \
  --out-html simulator/out/turbine_gt4088_map.html
```

  # optional:
  # --opline-csv simulator/out/turbine_turbine_opline.csv

# With Engine Operating Line

```bash
runroot python -m simulator.tools.tool_turbine_map_gt4088 \
  --csv simulator/in/turbine_gt4088_like.csv \
  --opline-csv simulator/out/turbo_match_opline.csv \
  --out-html simulator/out/turbine_gt4088_map.html
```

# Turbo matching - 4cyl

```bash
runroot python -m simulator.tools.tool_turbine_map_gt4088 \
  --csv simulator/in/turbine_gt4088_like.csv \
  --opline-csv simulator/out/turbo_match_opline_4cyl.csv \
  --out-html simulator/out/turbine_gt4088_map_4cyl.html
```

# Turbo matching - 8cyl

```bash
runroot python -m simulator.tools.tool_turbine_map_gt4088 \
  --csv simulator/in/turbine_gt4088_like.csv \
  --opline-csv simulator/out/turbo_match_opline_8cyl.csv \
  --out-html simulator/out/turbine_gt4088_map_8cyl.html
```

# Turbo matching - 12cyl

```bash
runroot python -m simulator.tools.tool_turbine_map_gt4088 \
  --csv simulator/in/turbine_gt4088_like.csv \
  --opline-csv simulator/out/turbo_match_opline_12cyl.csv \
  --out-html simulator/out/turbine_gt4088_map_12cyl.html
```

#### RipGrep

rg -n "a|b|c|d" simulator
rg -n "a" simulator/b
rg -n "yaml" simulator
rg -n "JetSurf2" simulator
rg -n "Blanquart2018" simulator
rg -n "Methanol|methanol" simulator
rg -n "ICE Simulator" simulator
rg -n "GM" simulator