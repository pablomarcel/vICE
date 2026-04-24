# vICE — Virtual Internal Combustion Engine Simulator

**vICE** is a Python-first virtual internal combustion engine simulator for spark-ignition engine studies, indicator diagrams, virtual dyno sweeps, BSFC maps, combustion metrics, adiabatic flame temperature studies, and early turbocharger matching.

It is designed for the kind of workflow engine people actually use when exploring concepts: edit a JSON engine file, run a case from the CLI, generate a result JSON, then build plots and tables from that result. The simulator is intentionally scriptable, inspectable, and easy to extend.

<p align="center">
  <em>0-D cycle simulation, P-V diagrams, dyno-style sweeps, BSFC maps, flame-temperature tools, and turbo matching in one practical Python package.</em>
</p>

---

## Why vICE exists

Most engine simulation tools are either too simplified to be useful, too locked into a GUI, or too heavy for quick experimentation. vICE sits in the middle:

- It is **not** pretending to be GT-Power, Ricardo WAVE, or a full CFD/1-D gas dynamics solver.
- It **is** a practical Python engine sandbox for learning, rapid studies, JSON-driven experiments, and engineering-style visualization.
- It gives you a clean architecture for adding more physics later without turning the project into a monolithic script.

Use it when you want to answer questions like:

- What does the P-V loop look like for this SI engine case?
- How do IMEP, BMEP, torque, brake power, and BSFC change with speed?
- What happens if I change fuel from gasoline to methanol or E85?
- How does intake pressure affect BMEP and power?
- Where is the best BSFC island on a BMEP-vs-speed map?
- How does equivalence ratio affect BSFC and flame temperature?
- How can I sketch a first-pass turbocharger operating line?

---

## Feature overview

### Core cycle simulator

- Spark-ignition engine cycle simulation from JSON input files
- Slider-crank cylinder volume model
- Compression and expansion polytropic models
- Wiebe-style burn fraction model
- P-V indicator diagram generation
- Multi-cycle runs for repeatability checks
- IMEP, BMEP, FMEP, indicated power, brake power, indicated torque, and brake torque
- Per-cylinder and total-engine outputs
- Mechanical efficiency and FMEP-speed friction models
- Cylinder-count scaling studies

### Fuel and combustion metrics

- Built-in fuel database for gasoline, methanol, E85, ethanol, methane, and related studies
- Stoichiometric AFR and LHV-based heat-release scaling
- Equivalence ratio and lambda reporting
- BSFC calculation in g/kWh
- Brake and indicated thermal efficiency
- MFB10, MFB50, MFB90 extraction
- Peak pressure and crank angle at peak pressure
- Simple knock-index proxy

### Virtual dyno and maps

- Full-load virtual dyno sweeps
- Motored sweeps
- Intake-pressure / boost sweeps
- BSFC vs speed
- BSFC vs BMEP
- BSFC vs equivalence ratio
- BSFC vs compression ratio
- BSFC contour maps over speed and intake pressure
- Brake thermal efficiency contour maps
- EPA-style BMEP-vs-speed BSFC map with brake-power contours and best-BSFC marker

### Thermochemistry tools

- Ideal backend flame-temperature studies
- Optional Cantera backend for HP-equilibrium adiabatic flame temperature
- Methane, propane, hydrogen, carbon monoxide, gasoline, methanol, ethanol, and E85 comparison workflows
- Flame-temperature vs equivalence-ratio plots
- Flame summary tools tied back to dyno output JSON files

### Turbocharger add-on

- Mean-value turbocharger model
- Optional `turbo` block in the engine JSON
- NA vs turbo virtual dyno comparison
- Compressor pressure ratio schedule vs RPM
- Intercooler effectiveness model
- Corrected mass-flow estimate
- Compressor operating-line tools
- Turbine map visualization hooks
- 4-cylinder, 8-cylinder, and 12-cylinder turbo matching examples

---

## Project philosophy

vICE follows a simple engineering-app pattern:

```text
JSON input  →  Python solver  →  JSON result  →  tables / plots / HTML reports
```

The result JSON is the source of truth. Plots are generated from saved result files, which makes the workflow reproducible and easy to debug.

The package is built around small modules:

```text
simulator/
├── cli.py          # command-line interface
├── main.py         # text UI entry point
├── app.py          # console front-end
├── apis.py         # high-level dispatcher
├── core.py         # engine geometry, operating conditions, solver, results
├── design.py       # sweeps: intake pressure, full-load speed, motored tests
├── fuels.py        # fuel database
├── io.py           # JSON IO and P-V plotting helpers
├── turbo.py        # mean-value turbocharger add-on
├── utils.py        # utility helpers
├── in/             # input JSON cases
├── out/            # generated JSON / CSV / HTML outputs
└── tools/          # plotting, sweep, thermo, BSFC, turbo tools
```

---

## Quick start

### 1. Clone the project

```bash
git clone <your-repo-url>
cd <your-repo-root>
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

The exact dependency list depends on which tools you want to use. The core simulator needs NumPy and Plotly. The flame-equilibrium tools can optionally use Cantera.

```bash
pip install numpy plotly pyfiglet
```

Optional thermochemistry backend:

```bash
pip install cantera
```

### 4. Define the `runroot` helper

The command cookbook uses a small helper so commands can be launched from anywhere inside the repo.

```bash
# --- run-from-root helpers (ICE-aware) -------------------------------------
_sim_root() {
  local d="$PWD"
  while [ "$d" != "/" ]; do
    if [ -d "$d/simulator" ] && [ -f "$d/simulator/__init__.py" ]; then
      echo "$d"; return
    fi
    if [ -d "$d/ice/simulator" ] && [ -f "$d/ice/simulator/__init__.py" ]; then
      echo "$d/ice"; return
    fi
    d="$(dirname "$d")"
  done
  if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git rev-parse --show-toplevel
    return
  fi
  echo "$PWD"
}
runroot() { ( cd "$(_sim_root)" && "$@" ); }
runroot mkdir -p simulator/out simulator/in
```

---

## Basic CLI usage

```bash
runroot python -m simulator.cli --help
```

The core CLI has three main commands:

```bash
runroot python -m simulator.cli list-inputs
```

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

That sequence runs a gasoline SI engine case and writes an interactive Plotly P-V indicator diagram next to the output JSON.

---

## Interactive text UI

vICE also includes a small console front-end:

```bash
runroot python -m simulator.main
```

The text UI can:

1. list available input cases,
2. run a simulation from a JSON file,
3. plot a P-V indicator diagram from a result JSON,
4. exit.

This is intentionally simple, but it provides a clean foundation for wrapping the same backend with richer GUIs later.

---

## Example input file

A typical engine input is a JSON file with `geometry` and `operating` blocks:

```json
{
  "meta": {
    "title": "demonstration SI engine case (gasoline)",
    "description": "Simple single-cylinder, four-stroke SI engine for architecture testing.",
    "units": "SI (m, kg, s, K, Pa)"
  },
  "geometry": {
    "bore_m": 0.086,
    "stroke_m": 0.086,
    "con_rod_m": 0.143,
    "compression_ratio": 10.0,
    "piston_pin_offset_m": 0.0
  },
  "operating": {
    "engine_speed_rpm": 4500.0,
    "air_fuel_ratio": 14.7,
    "intake_pressure_Pa": 101325.0,
    "exhaust_pressure_Pa": 101325.0,
    "intake_temp_K": 300.0,
    "crank_angle_ignition_deg": -20.0,
    "combustion_duration_deg": 60.0,
    "fuel_id": "gasoline",
    "integration_tolerance": 1e-5,
    "crank_step_deg": 1.0,
    "egr_mass_fraction": 0.0,
    "combustion_efficiency": 0.98,
    "pressure_rise_factor": 3.0,
    "num_cylinders": 1,
    "stroke_type": "four-stroke",
    "friction_model": "fmep-speed",
    "mechanical_efficiency": 0.9,
    "fmep_base_bar": 2.0,
    "fmep_speed_coeff_bar_per_krpm": 0.12,
    "fmep_speed_quad_bar_per_krpm2": 0.0
  }
}
```

The model is easy to clone and mutate. Change `fuel_id`, `air_fuel_ratio`, `compression_ratio`, `intake_pressure_Pa`, `num_cylinders`, or friction settings, then rerun the same CLI commands.

---

## Baseline gasoline SI case

Run one four-stroke cycle:

```bash
runroot python -m simulator.cli run \
  --config simulator/in/sample_si_engine.json \
  --outfile simulator/out/sample_si_engine_out.json \
  --cycles 1
```

Plot the indicator diagram:

```bash
runroot python -m simulator.cli plot \
  --result simulator/out/sample_si_engine_out.json
```

The output is an interactive P-V loop. This is the core “hello world” workflow for vICE.

---

## Methanol comparison

Run the methanol case:

```bash
runroot python -m simulator.cli run \
  --config simulator/in/sample_si_methanol_engine.json \
  --outfile simulator/out/methanol_out.json \
  --cycles 1
```

Plot it:

```bash
runroot python -m simulator.cli plot \
  --result simulator/out/methanol_out.json
```

Use this to compare peak pressure, IMEP, BMEP, indicated power, brake power, torque, and BSFC for the same geometry with a different fuel model.

---

## Multi-cycle stability check

Run three cycles:

```bash
runroot python -m simulator.cli run \
  --config simulator/in/sample_si_engine.json \
  --outfile simulator/out/sample_si_engine_3cyc_out.json \
  --cycles 3
```

Plot the repeated P-V loops:

```bash
runroot python -m simulator.cli plot \
  --result simulator/out/sample_si_engine_3cyc_out.json
```

The result object reports cycle-normalized IMEP, power, and torque. Multi-cycle runs are useful for checking that the integrated work and P-V loops behave consistently over repeated simulated cycles.

---

## Scalar sanity check

Because results are JSON, quick inspection is easy:

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

Example output:

```text
imep_bar                         : 9.971475549707131
bmep_bar                         : 7.431475549707131
indicated_power_kW               : 18.679959552202007
brake_power_kW                   : 13.921677086776251
indicated_torque_Nm              : 39.64010532652822
brake_torque_Nm                  : 29.542716326528232
mechanical_efficiency_effective  : 0.7452734063942421
```

---

## Cylinder-count scaling

Use the same per-cylinder thermodynamic model and vary cylinder count:

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

Example output:

```text
1 cyl -> Pb_total =  13.92 kW, T_total =   29.54 N·m, T_per_cyl =   29.54 N·m
4 cyl -> Pb_total =  55.69 kW, T_total =  118.17 N·m, T_per_cyl =   29.54 N·m
```

This is a clean demonstration of total engine scaling at fixed per-cylinder IMEP.

---

## Friction presets

vICE supports FMEP-speed friction behavior and named friction modes:

- `passenger`
- `performance`
- `f1`
- `generic`

Sweep them over the same base pressure trace:

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

Example output:

```text
mode=passenger    IMEP= 9.97 bar  BMEP= 7.77 bar  Pb= 14.56 kW  T_b=  30.90 N·m  η_mech=0.780
mode=performance  IMEP= 9.97 bar  BMEP= 7.16 bar  Pb= 13.41 kW  T_b=  28.45 N·m  η_mech=0.718
mode=f1           IMEP= 9.97 bar  BMEP= 6.71 bar  Pb= 12.57 kW  T_b=  26.67 N·m  η_mech=0.673
```

This is useful for showing how friction assumptions eat into BMEP and brake power while holding combustion approximately constant.

---

## Intake-pressure sweep

Use the design helper to sweep manifold pressure:

```bash
runroot python - << 'PY'
from simulator.design import sweep_intake_pressure
from simulator.io import load_json

base_cfg = "simulator/in/sample_si_engine.json"
pressures = [
    80_000.0, 90_000.0, 101_325.0, 120_000.0, 140_000.0, 160_000.0,
    180_000.0, 200_000.0, 220_000.0, 240_000.0, 260_000.0, 280_000.0,
    300_000.0, 320_000.0, 340_000.0, 360_000.0, 380_000.0, 400_000.0
]

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

This is one of the most practical early-design studies: change intake pressure and watch BMEP and brake power respond.

---

## Full-load virtual dyno sweep

Run a speed sweep:

```bash
runroot python -m simulator.tools.tool_full_load_sweep \
  --config simulator/in/sample_si_engine.json \
  --speeds 500 1000 1500 2000 2500 3000 3500 4000 4500 5000 5500 6000 6500 7000 7500 8000
```

You can also run turbo sample configs:

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

Then print a dyno-style summary table:

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

Example excerpt:

```text
  500 rpm  BMEP=  4.00 bar  BP=  10.00 kW  BT= 191.02 Nm  BSFC=  592.3 g/kWh
 3500 rpm  BMEP=  8.14 bar  BP= 142.27 kW  BT= 388.16 Nm  BSFC=  393.5 g/kWh
 5000 rpm  BMEP=  6.71 bar  BP= 167.61 kW  BT= 320.12 Nm  BSFC=  420.9 g/kWh
 8000 rpm  BMEP=  4.31 bar  BP= 172.18 kW  BT= 205.53 Nm  BSFC=  522.8 g/kWh
```

---

## Motored sweep

A motored sweep disables combustion and simulates compression/expansion plus pumping/friction behavior:

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

---

## BSFC tables and plots

Build CSV tables and Plotly HTML plots from virtual dyno outputs:

```bash
runroot python -m simulator.tools.tool_bsfc_table
```

Typical outputs:

```text
simulator/out/bsfc_full_load_table.csv
simulator/out/bsfc_pboost_table.csv
simulator/out/bsfc_full_load_plot.html
simulator/out/bsfc_pboost_plot.html
```

---

## BSFC and thermal-efficiency contour maps

Generate contour maps over intake pressure and engine speed:

```bash
runroot python -m simulator.tools.tool_bsfc_contours
```

This produces maps such as:

- BSFC contour map — speed vs intake pressure
- Brake thermal efficiency contour map — speed vs intake pressure

These maps are useful for thinking about operating regions rather than isolated speed points.

---

## Compression-ratio sweeps

BSFC vs RPM for several compression ratios:

```bash
runroot python -m simulator.tools.tool_bsfc_vs_speed_rc
```

BSFC vs equivalence ratio for several compression ratios:

```bash
runroot python -m simulator.tools.tool_bsfc_vs_phi_rc
```

Full BSFC-vs-phi map for compression ratios 8 through 15:

```bash
runroot python -m simulator.tools.bsfc_sweep_phi \
  --config simulator/in/sample_si_engine.json \
  --out-csv simulator/out/bsfc_vs_phi_rc8_15.csv \
  --out-html simulator/out/bsfc_vs_phi_rc8_15.html
```

Only selected compression ratios:

```bash
runroot python -m simulator.tools.bsfc_sweep_phi \
  --config simulator/in/sample_si_engine.json \
  --out-csv simulator/out/bsfc_vs_phi_rc8_10_12.csv \
  --out-html simulator/out/bsfc_vs_phi_rc8_10_12.html \
  --rc "8,10,12"
```

---

## Equivalence-ratio cases

Run individual phi cases:

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

Then plot pressure and temperature vs crank angle:

```bash
runroot python -m simulator.tools.tool_cycle_thermo_plot \
  --infile simulator/out/si_phi0.9_out.json \
  --out-html simulator/out/si_phi0.9_cycle_thermo.html
```

---

## EPA-style BSFC map

Generate the default “Baby F1” engine map:

```bash
runroot python -m simulator.tools.tool_bsfc_map_epa
```

This produces a BMEP-vs-speed BSFC contour map with:

- filled BSFC contours,
- dashed brake-power contour lines,
- best-BSFC marker.

Run the same map with alternate fuels:

```bash
runroot python -m simulator.tools.tool_bsfc_map_epa \
  --config simulator/in/sample_si_methanol_engine.json \
  --html simulator/out/methanol_bsfc_map_epa.html \
  --csv simulator/out/methanol_bsfc_map_epa_points.csv
```

```bash
runroot python -m simulator.tools.tool_bsfc_map_epa \
  --config simulator/in/sample_si_e85_engine.json \
  --html simulator/out/e85_bsfc_map_epa.html \
  --csv simulator/out/e85_bsfc_map_epa_points.csv
```

---

## Flame-temperature tools

### Ideal backend — gasoline

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

### Cantera backend — methane, GRI-Mech 3.0

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

### Cantera fuel comparison — methane vs propane

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

### Cantera fuel comparison — methane vs hydrogen

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

### Cantera fuel comparison — methane vs carbon monoxide

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

---

## Flame summary tied to dyno outputs

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

This is a useful bridge between dyno-style results and combustion-temperature summaries.

---

## Turbocharger add-on

vICE includes a mean-value turbocharger add-on. It is deliberately simple and algebraic: it does not yet solve real compressor/turbine maps or shaft dynamics, but it provides the right workflow skeleton.

A turbo config can be added as an optional top-level `turbo` block:

```jsonc
{
  "turbo": {
    "enabled": true,
    "p_amb_bar": 1.013,
    "T_amb_K": 298.15,
    "p_manifold_target_bar": 2.0,
    "N_idle_rpm": 1000.0,
    "N_full_boost_rpm": 2000.0,
    "compressor_efficiency": 0.72,
    "gamma_air": 1.40,
    "cp_air_J_per_kgK": 1005.0,
    "intercooler_effectiveness": 0.70,
    "volumetric_efficiency": 0.90
  }
}
```

### Turbo matching

```bash
runroot python -m simulator.tools.tool_turbo_match_opline \
  --config simulator/in/sample_si_engine_turbo.json \
  --out simulator/out/turbo_match_opline.csv \
  --N-min 1500 \
  --N-max 6000 \
  --N-step 500
```

4-cylinder example:

```bash
runroot python -m simulator.tools.tool_turbo_match_opline \
  --config simulator/in/sample_si_engine_turbo_4cyl.json \
  --out simulator/out/turbo_match_opline_4cyl.csv \
  --N-min 1500 \
  --N-max 6000 \
  --N-step 500
```

8-cylinder example:

```bash
runroot python -m simulator.tools.tool_turbo_match_opline \
  --config simulator/in/sample_si_engine_turbo_8cyl.json \
  --out simulator/out/turbo_match_opline_8cyl.csv \
  --N-min 1500 \
  --N-max 6000 \
  --N-step 500
```

12-cylinder example:

```bash
runroot python -m simulator.tools.tool_turbo_match_opline \
  --config simulator/in/sample_si_engine_turbo_12cyl.json \
  --out simulator/out/turbo_match_opline_12cyl.csv \
  --N-min 1500 \
  --N-max 6000 \
  --N-step 500
```

### Compressor map with operating line

```bash
runroot python -m simulator.tools.tool_compressor_map_efr71 \
  --csv simulator/in/compressor_efr71_grid.csv \
  --speedlines-csv simulator/in/compressor_efr71_speedlines.csv \
  --opline-csv simulator/out/turbo_match_opline.csv \
  --out-html simulator/out/compressor_efr71_map.html
```

### Turbine map with engine operating line

```bash
runroot python -m simulator.tools.tool_turbine_map_gt4088 \
  --csv simulator/in/turbine_gt4088_like.csv \
  --opline-csv simulator/out/turbo_match_opline.csv \
  --out-html simulator/out/turbine_gt4088_map.html
```

The turbo module is intentionally isolated from the core combustion/cycle solver, so it can evolve independently into a stronger map-based matching tool.

---

## Output files

Common outputs include:

```text
simulator/out/sample_si_engine_out.json
simulator/out/sample_si_engine_out_pv.html
simulator/out/full_load_N_04500.json
simulator/out/bsfc_full_load_table.csv
simulator/out/bsfc_full_load_plot.html
simulator/out/bsfc_pboost_table.csv
simulator/out/bsfc_pboost_plot.html
simulator/out/flame_methane_phi_cantera.json
simulator/out/flame_methane_phi_cantera.html
simulator/out/si_phi0.9_cycle_thermo.html
simulator/out/turbo_match_opline.csv
simulator/out/compressor_efr71_map.html
```

The JSON files are meant to be reusable: generate plots, compare sweeps, build CSV tables, or write your own post-processing scripts.

---

## What the generated plots show

vICE currently supports a practical set of engineering visualizations:

- **Indicator Diagram (P-V)** — cylinder pressure vs cylinder volume over the cycle
- **Multi-cycle P-V loops** — repeated cycle behavior and integrated work consistency
- **Full-load virtual dyno** — brake torque, brake power, and BSFC vs speed
- **BSFC contour map** — speed vs intake pressure
- **Brake thermal efficiency contour map** — speed vs intake pressure
- **BSFC vs speed** — multiple compression ratios
- **BSFC vs equivalence ratio** — multiple compression ratios
- **Adiabatic flame temperature vs equivalence ratio** — ideal or Cantera backend
- **Fuel comparison flame plots** — methane vs propane, methane vs hydrogen, methane vs CO, etc.
- **Cycle thermo plot** — cylinder pressure and gas temperature vs crank angle
- **EPA-style BSFC map** — BMEP vs speed, BSFC filled contours, brake-power contour lines, best-BSFC marker
- **Turbo compressor/turbine maps** — operating-line overlays for early matching studies

---

## Current modeling assumptions

vICE is useful, but it is still a simplified model. Current assumptions include:

- 0-D single-zone cylinder model
- Ideal-gas air/product approximation in the core cycle model
- Slider-crank volume model
- Polytropic compression and expansion
- Wiebe-style burn fraction
- Parametric heat-transfer efficiency factor
- Parametric equivalence-ratio behavior
- FMEP-speed friction correlation
- Simple volumetric-efficiency model
- Optional ideal or Cantera flame-temperature tools outside the core cycle model
- Mean-value turbo model with prescribed boost schedule, not full turbine/compressor power balance

This makes vICE fast, hackable, and transparent. It also means the numerical results should be interpreted as engineering-sandbox outputs, not certified engine calibration data.

---

## Roadmap ideas

Potential next upgrades:

- Real compressor and turbine map interpolation
- Turbo shaft power balance and turbine inlet temperature modeling
- Knock-limited spark advance model
- More detailed heat-transfer models
- Valve timing and residual gas modeling
- Volumetric efficiency maps from input CSV files
- Fuel-injection and combustion-duration maps
- Closed-loop boost control studies
- Plotly dashboard or DearPyGui front-end
- Exportable PDF/HTML engineering reports
- Test suite for canonical cases
- More physically grounded calibration against textbook examples or public engine datasets

---

## Suggested GitHub topics

```text
internal-combustion-engine
engine-simulation
ice-simulator
thermodynamics
spark-ignition
bsfc
bmep
imep
virtual-dyno
combustion
cantera
plotly
python
json-driven
mechanical-engineering
turbocharger
```

---

## License

Add your preferred license here.

For open-source engineering tooling, common choices are:

- MIT License for permissive reuse
- Apache-2.0 for permissive reuse with explicit patent language
- GPL-3.0 if you want derivative work to remain open

---

## Author

Built by **pablomarcel** as part of a growing Python engineering-simulation toolbox.

vICE is a practical, JSON-driven virtual engine laboratory: small enough to understand, useful enough to explore real engine-performance questions, and open enough to keep extending.
