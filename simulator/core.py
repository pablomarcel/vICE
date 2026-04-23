from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Dict, List
import math
import numpy as np
from . import utils
from .fuels import get_fuel, FuelProperties

R_GAS = 287.0  # J/(kg·K) – simple air model for air / products


# ----------------------------------------------------------------------
# Geometry & operating conditions
# ----------------------------------------------------------------------


@dataclass
class EngineGeometry:
    bore_m: float
    stroke_m: float
    con_rod_m: float
    compression_ratio: float
    piston_pin_offset_m: float = 0.0

    def area(self) -> float:
        """Piston crown area [m²]."""
        return math.pi * (self.bore_m ** 2) / 4.0

    def displacement_volume(self) -> float:
        """Single-cylinder displacement volume [m³]."""
        return self.area() * self.stroke_m

    def clearance_volume(self) -> float:
        """Clearance volume [m³]."""
        return self.displacement_volume() / (self.compression_ratio - 1.0)

    def volume(self, crank_deg: np.ndarray) -> np.ndarray:
        """Instantaneous cylinder volume vs crank angle.

        Classic slider–crank kinematics, ignoring pin offset for now.
        """
        theta = np.deg2rad(crank_deg)
        r = self.stroke_m / 2.0
        l = self.con_rod_m
        R = l / r
        term = 1.0 - np.cos(theta) + R - np.sqrt(R ** 2 - np.sin(theta) ** 2)
        return self.clearance_volume() + 0.5 * self.displacement_volume() * term


@dataclass
class OperatingConditions:
    # basic operating
    engine_speed_rpm: float
    air_fuel_ratio: float
    intake_pressure_Pa: float
    exhaust_pressure_Pa: float
    intake_temp_K: float
    crank_angle_ignition_deg: float
    combustion_duration_deg: float
    fuel_id: str = "gasoline"
    integration_tolerance: float = 1e-5
    crank_step_deg: float = 1.0
    egr_mass_fraction: float = 0.0

    # "base" combustion efficiency (will be shaped vs φ below)
    combustion_efficiency: float = 0.98

    # simple amplitude knob for pressure rise during combustion
    pressure_rise_factor: float = 3.0

    # Wiebe parameters
    wiebe_a: float = 5.0
    wiebe_m: float = 2.0

    # polytropic indices
    compression_polytropic_index: float = 1.32
    expansion_polytropic_index: float = 1.25

    # performance / friction model
    num_cylinders: int = 1
    stroke_type: str = "four-stroke"

    # friction_model:
    #   - "constant-eta": use mechanical_efficiency as configured
    #   - "fmep-speed": use speed/load-dependent FMEP correlation
    friction_model: str = "fmep-speed"

    # friction_mode presets (only used when friction_model == "fmep-speed"):
    #   - "generic": use raw a,b,c,d from config
    #   - "passenger": typical SI passenger-car map
    #   - "performance": hotter street/track engine
    #   - "f1": very high-speed race engine (illustrative)
    friction_mode: str = "generic"

    mechanical_efficiency: float = 0.9
    fmep_base_bar: float = 2.0
    fmep_speed_coeff_bar_per_krpm: float = 0.12
    fmep_speed_quad_bar_per_krpm2: float = 0.0
    fmep_load_coeff_bar_per_bar: float = 0.0  # d · BMEP term

    # volumetric efficiency vs speed (VE(N))
    #   ve_model: "constant" or "gaussian"
    ve_model: str = "gaussian"
    ve_base: float = 0.9
    ve_peak: float = 1.0
    ve_min: float = 0.7
    ve_N_peak_rpm: float = 3500.0
    ve_sigma_N_rpm: float = 1500.0

    # heat-transfer / indicated-efficiency vs speed & size
    #   heat_loss_model: "parametric" or "none"
    heat_loss_model: str = "parametric"
    heat_loss_k: float = 0.12
    heat_loss_ref_speed_rpm: float = 2500.0
    heat_loss_exp: float = 0.5
    heat_loss_ref_bore_m: float = 0.086  # reference bore for scaling (≈86 mm)
    heat_loss_geom_exponent: float = 1.0

    # combustion efficiency vs equivalence ratio (φ)
    #   η_c(φ) = η_max − k (φ − φ_opt)², clipped [η_min, η_max]
    combustion_eff_model: str = "parabolic"
    combustion_eff_phi_opt: float = 1.0
    combustion_eff_k: float = 0.15
    combustion_eff_min: float = 0.88

    # burn duration vs equivalence ratio (φ)
    #   duration_eff = base · (1 + k (φ − φ_opt)²), clipped [0.5, 3]×base
    combustion_duration_model: str = "parabolic"
    combustion_duration_phi_opt: float = 1.0
    combustion_duration_k: float = 2.0

    # ------------ NEW: φ-shape for load / IMEP and global scaling ------------

    # Location of *best BSFC* in φ-space (dimensionless).
    # Around 0.9 gives "slightly lean best BSFC" as in Pulkrabek Fig. 2-13.
    phi_best_for_bsfc: float = 0.90

    # Slopes controlling how fast indicated work degrades when lean / rich.
    # Larger numbers = stronger penalty. We choose a fairly strong lean penalty
    # so BSFC does *not* keep improving as we go very lean.
    phi_lean_slope: float = 1.5
    phi_rich_slope: float = 1.0

    # Global indicated-work calibration factor (dimensionless)
    # Wi_cycle = Wi_cycle_raw * work_scale_factor * η_ht * η_c
    # ~2.0–3.0 takes you from "BSFC ≈ 700 g/kWh" into "≈ 250–350 g/kWh".
    work_scale_factor: float = 2.3


# ----------------------------------------------------------------------
# Result container
# ----------------------------------------------------------------------


@dataclass
class SimulationResult:
    crank_deg: List[float]
    pressure_Pa: List[float]
    temperature_K: List[float]
    volume_m3: List[float]
    mass_fraction_burned: List[float]

    # performance scalars (optional, filled by EngineSimulator.run)
    imep_Pa: float | None = None
    imep_bar: float | None = None
    indicated_work_per_cycle_J: float | None = None

    # per-cylinder powers/torques
    indicated_power_per_cyl_W: float | None = None
    indicated_power_per_cyl_kW: float | None = None
    brake_power_per_cyl_W: float | None = None
    brake_power_per_cyl_kW: float | None = None
    indicated_torque_per_cyl_Nm: float | None = None
    brake_torque_per_cyl_Nm: float | None = None

    # total engine powers/torques
    indicated_power_W: float | None = None
    indicated_power_kW: float | None = None
    indicated_torque_Nm: float | None = None
    brake_power_W: float | None = None
    brake_power_kW: float | None = None
    brake_torque_Nm: float | None = None

    bmep_Pa: float | None = None
    bmep_bar: float | None = None
    friction_power_W: float | None = None
    friction_power_kW: float | None = None
    fmep_Pa: float | None = None
    fmep_bar: float | None = None
    mechanical_efficiency_effective: float | None = None

    # dyno / fuel metrics
    bsfc_g_per_kWh: float | None = None
    brake_thermal_efficiency: float | None = None
    indicated_thermal_efficiency: float | None = None

    # combustion quality / stability
    cov_imep_percent: float | None = None
    peak_pressure_Pa: float | None = None
    peak_pressure_bar: float | None = None
    crank_deg_peak_pressure: float | None = None
    mfb10_deg: float | None = None
    mfb50_deg: float | None = None
    mfb90_deg: float | None = None
    knock_index_proxy: float | None = None

    # mixture / filling info
    lambda_value: float | None = None
    volumetric_efficiency: float | None = None
    heat_transfer_eff_factor: float | None = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ----------------------------------------------------------------------
# Engine simulator core
# ----------------------------------------------------------------------


@dataclass
class EngineSimulator:
    geometry: EngineGeometry
    operating: OperatingConditions

    # ---------- construction helpers ----------

    @classmethod
    def from_dict(cls, cfg: Dict[str, Any]) -> "EngineSimulator":
        geom = utils.dataclass_from_dict(EngineGeometry, cfg.get("geometry", {}))
        op = utils.dataclass_from_dict(OperatingConditions, cfg.get("operating", {}))
        return cls(geometry=geom, operating=op)

    # ---------- grids & helpers ----------

    def _crank_grid(self, cycles: int) -> np.ndarray:
        step = self.operating.crank_step_deg
        total_deg = 720.0 * max(int(cycles), 1)
        return np.arange(-180.0, -180.0 + total_deg + step, step, dtype=float)

    # --- fuel helpers -------------------------------------------------

    @property
    def fuel(self) -> FuelProperties:
        return get_fuel(self.operating.fuel_id)

    @property
    def equivalence_ratio(self) -> float:
        afr_act = self.operating.air_fuel_ratio
        if afr_act <= 0.0:
            raise ValueError("air_fuel_ratio must be positive")
        afr_st = self.fuel.afr_stoich
        return afr_st / afr_act

    @property
    def lambda_value(self) -> float:
        """Air–fuel ratio relative to stoichiometric (λ)."""
        afr_act = self.operating.air_fuel_ratio
        afr_st = self.fuel.afr_stoich
        if afr_st <= 0.0:
            return 1.0
        return afr_act / afr_st

    # --- volumetric efficiency vs speed --------------------------------

    def volumetric_efficiency(self) -> float:
        """Return volumetric efficiency VE(N) used for trapped mass.

        - 'constant': VE = ve_base
        - 'gaussian': VE(N) with a Gaussian peak at ve_N_peak_rpm.
        """
        op = self.operating
        model = getattr(op, "ve_model", "gaussian").lower()

        if model == "constant":
            ve = float(getattr(op, "ve_base", 0.9))
        else:
            # Gaussian peak around N_peak with floor at ve_min.
            N = max(float(op.engine_speed_rpm), 0.0)
            Np = float(getattr(op, "ve_N_peak_rpm", 3500.0))
            sigma = max(float(getattr(op, "ve_sigma_N_rpm", 1500.0)), 1.0)
            ve_peak = float(getattr(op, "ve_peak", 1.0))
            ve_min = float(getattr(op, "ve_min", 0.7))

            x = (N - Np) / sigma
            ve = ve_min + (ve_peak - ve_min) * math.exp(-0.5 * x * x)

        return max(0.0, min(1.2, float(ve)))

    # --- combustion efficiency & burn duration vs φ --------------------

    def _combustion_efficiency_phi(self) -> float:
        """Combustion efficiency η_c(φ).

        Simple parabolic model around φ_opt, clipped between η_min and η_max.

        IMPORTANT:
            We no longer use this to *create* the BSFC U-shape; we keep it
            fairly soft and let the φ-load factor drive torque vs φ.
        """
        op = self.operating
        model = getattr(op, "combustion_eff_model", "parabolic").lower()
        eta_max = float(getattr(op, "combustion_efficiency", 0.98))

        if model == "none":
            return max(0.0, min(1.0, eta_max))

        phi = self.equivalence_ratio
        phi_opt = float(getattr(op, "combustion_eff_phi_opt", 1.0))
        k = float(getattr(op, "combustion_eff_k", 0.15))
        eta_min = float(getattr(op, "combustion_eff_min", 0.88))

        eta = eta_max - k * (phi - phi_opt) ** 2
        return max(eta_min, min(eta_max, eta))

    def _effective_combustion_duration_deg(self) -> float:
        """Return combustion duration in crank degrees, including φ-effects."""
        op = self.operating
        base = float(getattr(op, "combustion_duration_deg", 40.0))
        model = getattr(op, "combustion_duration_model", "parabolic").lower()
        if model == "none":
            return base

        phi = self.equivalence_ratio
        phi_opt = float(getattr(op, "combustion_duration_phi_opt", 1.0))
        k = float(getattr(op, "combustion_duration_k", 2.0))

        factor = 1.0 + k * (phi - phi_opt) ** 2
        eff = base * factor
        # clip to avoid ridiculous durations
        eff = max(0.5 * base, min(3.0 * base, eff))
        return eff

    # --- NEW: φ-dependent load / IMEP factor ---------------------------

    def _phi_load_eff_factor(self, phi: float | None = None) -> float:
        """Dimensionless factor f_φ that shapes IMEP vs equivalence ratio.

        Goal:
          - Best BSFC slightly lean (~φ ≈ phi_best_for_bsfc).
          - Torque / IMEP penalized both richer and leaner than that.

        Simple piecewise-linear model:

            if φ <= φ_best:  f = 1 - k_lean (φ_best - φ)
            else:            f = 1 - k_rich (φ - φ_best)

        Then clamped to [0.3, 1.1] to avoid silly values.

        With defaults:
            φ_best = 0.9, k_lean = 1.5, k_rich = 1.0

        Gives a BSFC minimum around φ ≈ 0.9 when you combine this with
        mf_dot ∝ φ, which is what we want from Pulkrabek Fig. 2-13.
        """
        op = self.operating
        if phi is None:
            phi = self.equivalence_ratio

        phi_best = float(getattr(op, "phi_best_for_bsfc", 0.90))
        k_lean = float(getattr(op, "phi_lean_slope", 1.5))
        k_rich = float(getattr(op, "phi_rich_slope", 1.0))

        if phi <= phi_best:
            factor = 1.0 - k_lean * (phi_best - phi)
        else:
            factor = 1.0 - k_rich * (phi - phi_best)

        # Keep it in a reasonable range
        return max(0.3, min(1.1, factor))

    # --- effective pressure rise vs fuel / φ ---------------------------

    def _effective_pressure_rise(self) -> float:
        """Scale the pressure-rise factor by fuel LHV and equivalence ratio.

        OLD BUG:
            We previously multiplied directly by φ. That made IMEP grow
            ~linearly with φ, so rich mixtures *always* looked better for
            BSFC – which is the opposite of Pulkrabek's Fig. 2-13.

        NEW:
            - Amplitude scales with LHV (so different fuels show up).
            - φ only enters through the φ-load efficiency factor, which
              peaks slightly lean and penalizes both rich and lean sides.
        """
        op = self.operating
        fuel = self.fuel
        phi = self.equivalence_ratio

        base = op.pressure_rise_factor
        gasoline_LHV = 44e6
        lhv_scale = fuel.LHV_J_per_kg / gasoline_LHV

        # clamp φ to a reasonable range, but we don't use it linearly anymore
        phi_clamped = max(0.6, min(1.4, phi))

        phi_shape = self._phi_load_eff_factor(phi_clamped)

        return base * lhv_scale * phi_shape

    # --- combustion model ---------------------------------------------

    @staticmethod
    def _wiebe(theta: float, theta0: float, duration: float, a: float, m_exp: float) -> float:
        if theta <= theta0:
            return 0.0
        if theta >= theta0 + duration:
            return 1.0
        xb = 1.0 - math.exp(-a * ((theta - theta0) / duration) ** (m_exp + 1.0))
        return xb

    # --- heat-transfer / indicated efficiency vs N ---------------------

    def _indicated_eff_heat_transfer_factor(self) -> float:
        """Return multiplicative factor η_ht(N) applied to indicated work.

        Toy parametric model:
            η_ht = 1 − k_ht · f(N) · g(bore)

        where f(N) decays with speed and g(bore) penalises small bores
        (larger area/volume ratio → more heat loss).
        """
        op = self.operating
        model = getattr(op, "heat_loss_model", "none").lower()
        if model not in {"parametric", "simple"}:
            return 1.0

        N = max(float(op.engine_speed_rpm), 1.0)
        N_ref = max(float(getattr(op, "heat_loss_ref_speed_rpm", 2500.0)), 1.0)
        k_ht = float(getattr(op, "heat_loss_k", 0.12))
        exp_ht = float(getattr(op, "heat_loss_exp", 0.5))

        # Large at low N, decays with N
        fN = (N_ref / N) ** exp_ht

        # Geometry scaling: smaller bore → larger A/V → more heat loss
        bore = max(float(getattr(self.geometry, "bore_m", 0.086)), 1e-4)
        ref_bore = float(getattr(op, "heat_loss_ref_bore_m", bore))
        geom_exp = float(getattr(op, "heat_loss_geom_exponent", 1.0))
        geom_factor = (ref_bore / bore) ** geom_exp

        penalty = k_ht * fN * geom_factor
        factor = 1.0 - penalty
        return max(0.0, min(1.0, factor))

    # --- friction presets & post-processing ---------------------------

    def _friction_coeffs_from_mode(self) -> tuple[float, float, float, float]:
        """Return (a,b,c,d) in

            FMEP_bar = a + b N_krpm + c N_krpm² + d · BMEP_bar

        Modes are intended to be *illustrative*, not production-grade maps.
        """
        op = self.operating
        mode = getattr(op, "friction_mode", "generic").lower()

        if mode == "passenger":
            # Mild SI engine at moderate speeds (e.g. 2–6 krpm)
            a, b, c, d = 1.2, 0.10, 0.004, 0.06
        elif mode == "performance":
            # Hotter cam, higher speeds, more valvetrain/splash losses
            a, b, c, d = 1.4, 0.16, 0.006, 0.08
        elif mode == "f1":
            # Very high-speed race engine (illustrative numbers)
            a, b, c, d = 1.8, 0.14, 0.008, 0.10
        else:
            # "generic" or unknown: trust the raw coefficients from the config
            a = op.fmep_base_bar
            b = op.fmep_speed_coeff_bar_per_krpm
            c = op.fmep_speed_quad_bar_per_krpm2
            d = getattr(op, "fmep_load_coeff_bar_per_bar", 0.0)
        return a, b, c, d

    def _compute_friction_from_speed(self, imep_Pa: float) -> tuple[float, float]:
        """Return (FMEP_Pa, mechanical_efficiency) using a speed/load-based model.

        Simple correlation:
            FMEP_bar = a + b N_krpm + c N_krpm² + d · BMEP_bar

        with BMEP_bar ≈ IMEP_bar − FMEP_bar, solved analytically.
        """
        op = self.operating
        N = max(op.engine_speed_rpm, 0.0)
        N_krpm = N / 1000.0
        a, b, c, d = self._friction_coeffs_from_mode()

        imep_bar = imep_Pa / 1e5
        d_eff = max(float(d), 0.0)
        # F = a + b N + c N² + d (IMEP − F)  =>  F (1 + d) = a + b N + c N² + d IMEP
        numerator = a + b * N_krpm + c * N_krpm * N_krpm + d_eff * imep_bar
        denom = 1.0 + d_eff
        fmep_bar = max(numerator / denom, 0.0)
        fmep_Pa = fmep_bar * 1e5

        if imep_Pa <= 0.0:
            eta_mech = 0.0
        else:
            eta_mech = max(0.0, min(1.0, (imep_Pa - fmep_Pa) / imep_Pa))
        return fmep_Pa, eta_mech

    # --- performance post-processing ----------------------------------

    def _compute_mfb_angle(self, crank_deg: np.ndarray, xb: np.ndarray, target: float) -> float | None:
        mask = xb >= target
        if not np.any(mask):
            return None
        idx = int(np.argmax(mask))
        return float(crank_deg[idx])

    def _compute_performance(
        self,
        crank_deg: np.ndarray,
        p: np.ndarray,
        V: np.ndarray,
        xb: np.ndarray,
        cycles: int,
    ) -> Dict[str, Any]:
        """Compute IMEP, indicated/brake power and torque from P–V data.

        All IMEP/BMEP/FMEP values are per cylinder. Powers/torques are
        returned both per cylinder and for the full engine, using the
        configured number of cylinders.
        """
        geom = self.geometry
        op = self.operating

        if len(p) < 2:
            return {}

        cycles = max(int(cycles), 1)

        # Net indicated work over whole simulation (could be multiple cycles)
        # W = ∮ p dV  [J], positive for output work.
        Wi_total_raw = float(np.trapz(p, V))
        Wi_cycle_raw = Wi_total_raw / cycles  # J per cylinder per cycle (no ht-loss / η_c)

        # Apply heat-transfer factor, φ-dependent combustion efficiency,
        # and a global calibration factor to match realistic BSFC levels.
        eta_ht = self._indicated_eff_heat_transfer_factor()
        eta_c = self._combustion_efficiency_phi()
        work_scale = float(getattr(op, "work_scale_factor", 1.0))

        Wi_cycle = Wi_cycle_raw * work_scale * eta_ht * eta_c

        Vd = geom.displacement_volume()
        if Vd <= 0.0:
            return {}

        imep_Pa = Wi_cycle / Vd
        imep_bar = imep_Pa / 1e5

        # CoV of IMEP across cycles (if cycles > 1)
        cov_imep_percent: float | None = None
        if cycles > 1:
            step = max(op.crank_step_deg, 1e-6)
            n_seg_per_cycle = int(round(720.0 / step))
            imeps: list[float] = []
            for k in range(cycles):
                i0 = k * n_seg_per_cycle
                i1 = i0 + n_seg_per_cycle
                if i1 + 1 > len(p):
                    break
                Wi_k = float(np.trapz(p[i0:i1+1], V[i0:i1+1]))
                imeps.append(Wi_k / Vd)
            if len(imeps) >= 2:
                arr = np.array(imeps, dtype=float)
                mean = float(arr.mean())
                if abs(mean) > 0.0:
                    cov_imep_percent = float(arr.std(ddof=1) / abs(mean) * 100.0)
            elif len(imeps) == 1:
                cov_imep_percent = 0.0
        else:
            cov_imep_percent = 0.0

        # speed / cycle rate
        N = max(op.engine_speed_rpm, 0.0)
        stroke = op.stroke_type.lower()
        if "two" in stroke or "2-" in stroke:
            cycles_per_sec = N / 60.0
        else:
            # default: four-stroke
            cycles_per_sec = N / 120.0

        n_cyl = max(int(op.num_cylinders), 1)

        # Indicated power – per cylinder, then total
        P_i_one = Wi_cycle * cycles_per_sec          # W per cylinder
        P_i_one_kW = P_i_one / 1000.0
        P_i_total = P_i_one * n_cyl                  # W total engine
        P_i_total_kW = P_i_total / 1000.0

        omega = 2.0 * math.pi * N / 60.0  # rad/s
        T_i_one = P_i_one / omega if omega > 0.0 else 0.0
        T_i_total = P_i_total / omega if omega > 0.0 else 0.0

        # --- friction / brake side ---
        model = getattr(op, "friction_model", "fmep-speed").lower()
        if model == "constant-eta":
            eta_mech = max(0.0, min(1.0, float(op.mechanical_efficiency)))
            fmep_Pa = imep_Pa * (1.0 - eta_mech)
        else:
            # default: speed/load-based FMEP
            fmep_Pa, eta_mech = self._compute_friction_from_speed(imep_Pa)

        fmep_bar = fmep_Pa / 1e5
        bmep_Pa = max(imep_Pa - fmep_Pa, 0.0)
        bmep_bar = bmep_Pa / 1e5

        # brake power scales with the same efficiency
        P_b_one = P_i_one * eta_mech
        P_b_one_kW = P_b_one / 1000.0
        P_b_total = P_i_total * eta_mech
        P_b_total_kW = P_b_total / 1000.0

        T_b_one = P_b_one / omega if omega > 0.0 else 0.0
        T_b_total = P_b_total / omega if omega > 0.0 else 0.0

        P_f_total = P_i_total - P_b_total
        P_f_total_kW = P_f_total / 1000.0

        # --- fuel flow, BSFC, thermal efficiencies --------------------
        fuel = self.fuel
        afr = op.air_fuel_ratio
        lambda_val = self.lambda_value

        # approximate mass of charge at IVC (index 0)
        p0 = op.intake_pressure_Pa
        T0 = op.intake_temp_K
        V0 = float(V[0])
        ve = self.volumetric_efficiency()
        m_cyl_total = ve * p0 * V0 / (R_GAS * T0)  # kg of charge per cylinder at IVC

        bsfc_g_per_kWh: float | None
        eta_b_th: float | None
        eta_i_th: float | None

        if afr > 0.0 and P_b_total > 0.0:
            mf_cycle_per_cyl = m_cyl_total / afr  # kg fuel / cycle / cylinder
            mf_dot_total = mf_cycle_per_cyl * cycles_per_sec * n_cyl  # kg/s total
            mf_dot_g_per_s = mf_dot_total * 1000.0

            if P_b_total_kW > 0.0:
                # Eq. (2-59): bsfc = m_dot_f / Ẇ_b, then converted to g/kW-hr
                bsfc_g_per_kWh = (mf_dot_g_per_s / P_b_total_kW) * 3600.0
            else:
                bsfc_g_per_kWh = None

            # Thermal efficiencies per Pulkrabek Eq. (2-64) and (2-66/2-67)
            denom = mf_dot_total * fuel.LHV_J_per_kg
            if denom > 0.0:
                eta_b_th = P_b_total / denom
                eta_i_th = P_i_total / denom
            else:
                eta_b_th = None
                eta_i_th = None
        else:
            bsfc_g_per_kWh = None
            eta_b_th = None
            eta_i_th = None

        # --- peak pressure & MFB angles --------------------------------
        peak_idx = int(np.argmax(p))
        p_peak = float(p[peak_idx])
        p_peak_bar = p_peak / 1e5
        ca_peak = float(crank_deg[peak_idx])

        mfb10 = self._compute_mfb_angle(crank_deg, xb, 0.10)
        mfb50 = self._compute_mfb_angle(crank_deg, xb, 0.50)
        mfb90 = self._compute_mfb_angle(crank_deg, xb, 0.90)

        # Toy "knock index" based on CA50 advance: earlier CA50 → higher index.
        knock_index: float | None = None
        if mfb50 is not None:
            target_ca50 = 8.0  # deg aTDC reference
            diff = target_ca50 - mfb50
            if diff > 0.0:
                knock_index = min(1.0, diff / 20.0)
            else:
                knock_index = 0.0

        return {
            "imep_Pa": imep_Pa,
            "imep_bar": imep_bar,
            "indicated_work_per_cycle_J": Wi_cycle,
            # per-cylinder
            "indicated_power_per_cyl_W": P_i_one,
            "indicated_power_per_cyl_kW": P_i_one_kW,
            "brake_power_per_cyl_W": P_b_one,
            "brake_power_per_cyl_kW": P_b_one_kW,
            "indicated_torque_per_cyl_Nm": T_i_one,
            "brake_torque_per_cyl_Nm": T_b_one,
            # totals
            "indicated_power_W": P_i_total,
            "indicated_power_kW": P_i_total_kW,
            "indicated_torque_Nm": T_i_total,
            "brake_power_W": P_b_total,
            "brake_power_kW": P_b_total_kW,
            "brake_torque_Nm": T_b_total,
            "bmep_Pa": bmep_Pa,
            "bmep_bar": bmep_bar,
            "friction_power_W": P_f_total,
            "friction_power_kW": P_f_total_kW,
            "fmep_Pa": fmep_Pa,
            "fmep_bar": fmep_bar,
            "mechanical_efficiency_effective": eta_mech,
            # extra metrics
            "bsfc_g_per_kWh": bsfc_g_per_kWh,
            "brake_thermal_efficiency": eta_b_th,
            "indicated_thermal_efficiency": eta_i_th,
            "cov_imep_percent": cov_imep_percent,
            "peak_pressure_Pa": p_peak,
            "peak_pressure_bar": p_peak_bar,
            "crank_deg_peak_pressure": ca_peak,
            "mfb10_deg": mfb10,
            "mfb50_deg": mfb50,
            "mfb90_deg": mfb90,
            "knock_index_proxy": knock_index,
            "lambda_value": lambda_val,
            "volumetric_efficiency": ve,
            "heat_transfer_eff_factor": eta_ht,
        }

    # --- main integration loop ----------------------------------------

    @utils.log_call
    def run(self, cycles: int = 1) -> SimulationResult:
        op = self.operating
        geom = self.geometry
        crank = self._crank_grid(cycles)
        V = geom.volume(crank)
        n_pts = len(crank)
        p = np.zeros(n_pts, dtype=float)
        T = np.zeros(n_pts, dtype=float)
        xb = np.zeros(n_pts, dtype=float)

        # initial conditions at IVC (index 0)
        pint = op.intake_pressure_Pa
        Tint = op.intake_temp_K
        V0 = V[0]
        ve = self.volumetric_efficiency()

        # trapped mass per cylinder at IVC including VE
        m = ve * pint * V0 / (R_GAS * Tint)

        # cylinder pressure is slightly lower than manifold due to VE
        p[0] = pint * ve
        T[0] = Tint

        theta_ign = op.crank_angle_ignition_deg
        comb_dur_deg = self._effective_combustion_duration_deg()
        theta_end_comb = theta_ign + comb_dur_deg
        n_comp = op.compression_polytropic_index
        n_exp = op.expansion_polytropic_index
        delta_factor = self._effective_pressure_rise()

        for i in range(1, n_pts):
            th = crank[i]
            if th <= theta_ign:
                # compression
                p[i] = p[0] * (V[0] / V[i]) ** n_comp
                T[i] = T[0] * (V[0] / V[i]) ** (n_comp - 1.0)
                xb[i] = 0.0
            elif th <= theta_end_comb:
                # combustion via Wiebe function
                xb[i] = self._wiebe(
                    th,
                    theta_ign,
                    comb_dur_deg,
                    op.wiebe_a,
                    op.wiebe_m,
                )
                p_comp = p[0] * (V[0] / V[i]) ** n_comp
                p[i] = p_comp * (1.0 + delta_factor * xb[i])
                T[i] = p[i] * V[i] / (m * R_GAS)
            else:
                # expansion + exhaust blowdown (relaxed to exhaust pressure)
                if i == 0:
                    p_ref, V_ref = p[0], V[0]
                else:
                    p_ref, V_ref = p[i - 1], V[i - 1]
                p_ideal = p_ref * (V_ref / V[i]) ** n_exp
                relax = 0.02
                p[i] = (1.0 - relax) * p_ideal + relax * op.exhaust_pressure_Pa
                T[i] = p[i] * V[i] / (m * R_GAS)
                xb[i] = 1.0

        # ensure consistency at index 0
        T[0] = p[0] * V[0] / (m * R_GAS)

        perf = self._compute_performance(crank, p, V, xb, cycles)

        return SimulationResult(
            crank_deg=crank.tolist(),
            pressure_Pa=p.tolist(),
            temperature_K=T.tolist(),
            volume_m3=V.tolist(),
            mass_fraction_burned=xb.tolist(),
            **perf,
        )

    # --- summary for CLI / TUI ----------------------------------------

    def summary(self, result: SimulationResult | None = None) -> Dict[str, Any]:
        op = self.operating
        geom = self.geometry
        base: Dict[str, Any] = {
            "bore_m": geom.bore_m,
            "stroke_m": geom.stroke_m,
            "compression_ratio": geom.compression_ratio,
            "speed_rpm": op.engine_speed_rpm,
            "afr": op.air_fuel_ratio,
            "fuel_id": op.fuel_id,
            "equivalence_ratio": self.equivalence_ratio,
            "lambda": self.lambda_value,
            "ignition_deg": op.crank_angle_ignition_deg,
            "combustion_duration_deg": op.combustion_duration_deg,
            "crank_step_deg": op.crank_step_deg,
            "num_cylinders": op.num_cylinders,
            "stroke_type": op.stroke_type,
            "friction_model": op.friction_model,
            "friction_mode": getattr(op, "friction_mode", "generic"),
            "volumetric_efficiency": self.volumetric_efficiency(),
        }
        if result is not None:
            if result.imep_bar is not None:
                base["imep_bar"] = result.imep_bar
            if result.bmep_bar is not None:
                base["bmep_bar"] = result.bmep_bar
            if result.indicated_power_kW is not None:
                base["indicated_power_kW_total"] = result.indicated_power_kW
            if result.brake_power_kW is not None:
                base["brake_power_kW_total"] = result.brake_power_kW
            if result.indicated_power_per_cyl_kW is not None:
                base["indicated_power_kW_per_cyl"] = result.indicated_power_per_cyl_kW
            if result.brake_power_per_cyl_kW is not None:
                base["brake_power_kW_per_cyl"] = result.brake_power_per_cyl_kW
            if result.indicated_torque_Nm is not None:
                base["indicated_torque_Nm_total"] = result.indicated_torque_Nm
            if result.brake_torque_Nm is not None:
                base["brake_torque_Nm_total"] = result.brake_torque_Nm
            if result.indicated_torque_per_cyl_Nm is not None:
                base["indicated_torque_per_cyl_Nm"] = result.indicated_torque_per_cyl_Nm
            if result.brake_torque_per_cyl_Nm is not None:
                base["brake_torque_per_cyl_Nm"] = result.brake_torque_per_cyl_Nm
            if result.fmep_bar is not None:
                base["fmep_bar"] = result.fmep_bar
            if result.mechanical_efficiency_effective is not None:
                base["mechanical_efficiency_effective"] = result.mechanical_efficiency_effective
            if result.bsfc_g_per_kWh is not None:
                base["bsfc_g_per_kWh"] = result.bsfc_g_per_kWh
            if result.brake_thermal_efficiency is not None:
                base["brake_thermal_efficiency"] = result.brake_thermal_efficiency
            if result.indicated_thermal_efficiency is not None:
                base["indicated_thermal_efficiency"] = result.indicated_thermal_efficiency
            if result.cov_imep_percent is not None:
                base["cov_imep_percent"] = result.cov_imep_percent
            if result.peak_pressure_bar is not None:
                base["peak_pressure_bar"] = result.peak_pressure_bar
            if result.crank_deg_peak_pressure is not None:
                base["crank_deg_peak_pressure"] = result.crank_deg_peak_pressure
            if result.mfb50_deg is not None:
                base["mfb50_deg"] = result.mfb50_deg
            if result.knock_index_proxy is not None:
                base["knock_index_proxy"] = result.knock_index_proxy
            if result.heat_transfer_eff_factor is not None:
                base["heat_transfer_eff_factor"] = result.heat_transfer_eff_factor
        return base
