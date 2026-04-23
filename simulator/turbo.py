from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import math
import numpy as np

from .core import EngineSimulator
from . import io


@dataclass
class TurboConfig:
    """Mean‑value turbocharger configuration parsed from JSON.

    This is intentionally simple and algebraic. It represents a *single*
    turbocharger feeding the intake manifold of the engine.

    The key design decision for v0 is that **boost is prescribed** via a
    smooth schedule vs RPM (to mimic wastegate / VGT behaviour), rather
    than solved from a turbine/compressor power balance.
    """

    enabled: bool = True

    # Ambient / reference conditions
    p_amb_bar: float = 1.013
    T_amb_K: float = 298.15

    # Boost schedule parameters (piecewise‑linear in RPM)
    p_manifold_target_bar: float = 2.0
    N_idle_rpm: float = 1000.0
    N_full_boost_rpm: float = 2000.0

    # Compressor model (single‑zone, constant efficiency)
    compressor_efficiency: float = 0.72
    gamma_air: float = 1.40
    cp_air_J_per_kgK: float = 1005.0
    R_air_J_per_kgK: float = 287.0

    # Intercooler model (effectiveness ε)
    intercooler_effectiveness: float = 0.70

    # Volumetric efficiency used for mass‑flow estimate
    volumetric_efficiency: float = 0.90

    @classmethod
    def from_config(cls, cfg: Mapping[str, Any]) -> "TurboConfig":
        """Build from a full engine JSON dict (top‑level).

        Looks for a ``turbo`` block; falls back to ``operating`` for
        volumetric efficiency if not present there.
        """
        tcfg = dict(cfg.get("turbo", {}))
        op = cfg.get("operating", {})

        if "volumetric_efficiency" not in tcfg:
            ve = op.get("volumetric_efficiency", 0.90)
            tcfg["volumetric_efficiency"] = float(ve)

        return cls(**tcfg)

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def boost_pressure_ratio(self, N_rpm: float) -> float:
        """Return compressor pressure ratio PR = p2/p1 at a given RPM.

        We use a simple piecewise‑linear schedule:

            * N <= N_idle    → PR = 1.0 (no boost)
            * N >= N_full    → PR = p_manifold_target / p_amb
            * otherwise      → linear interpolation between 1.0 and PR_full
        """
        N = float(max(N_rpm, 0.0))
        p1_bar = float(self.p_amb_bar)
        p2_target_bar = float(self.p_manifold_target_bar)
        if p1_bar <= 0.0:
            return 1.0

        PR_full = max(p2_target_bar / p1_bar, 1.0)
        if N <= self.N_idle_rpm:
            return 1.0
        if N >= self.N_full_boost_rpm:
            return PR_full

        # Linear ramp between idle and full‑boost
        frac = (N - self.N_idle_rpm) / max(self.N_full_boost_rpm - self.N_idle_rpm, 1e-6)
        return 1.0 + frac * (PR_full - 1.0)

    def manifold_state_from_PR(self, PR: float) -> Tuple[float, float]:
        """Return (p2_bar, T2_ic_K) from a given PR using a simple model.

        Steps:

        1. Compressor isentropic outlet temperature:
               T2s = T1 * PR^{(γ−1)/γ}
        2. Actual compressor outlet temperature:
               T2  = T1 + (T2s − T1) / η_c
        3. Intercooler with effectiveness ε:
               T3  = T2 − ε (T2 − T1)
                   = T1 + (1 − ε) (T2 − T1)
        """
        PR = max(float(PR), 1.0)
        T1 = float(self.T_amb_K)
        p1_bar = float(self.p_amb_bar)
        gamma = float(self.gamma_air)
        eta_c = max(min(float(self.compressor_efficiency), 1.0), 1e-3)
        eps_ic = max(min(float(self.intercooler_effectiveness), 1.0), 0.0)

        if PR <= 1.0:
            return p1_bar, T1

        expn = (gamma - 1.0) / gamma
        T2s = T1 * PR**expn
        T2 = T1 + (T2s - T1) / eta_c
        T3 = T2 - eps_ic * (T2 - T1)

        p2_bar = p1_bar * PR
        return p2_bar, T3


@dataclass
class TurboMatchPoint:
    """One steady‑state operating point for NA and turbocharged cases."""

    speed_rpm: float

    # NA baseline
    na_bmep_bar: float | None = None
    na_torque_Nm: float | None = None
    na_power_kW: float | None = None
    na_bsfc_g_per_kWh: float | None = None
    na_eta_b_th: float | None = None

    # Turbocharged
    pr_c: float | None = None
    p_int_bar: float | None = None
    T_int_K: float | None = None
    m_dot_air_kg_per_s: float | None = None

    tb_bmep_bar: float | None = None
    tb_torque_Nm: float | None = None
    tb_power_kW: float | None = None
    tb_bsfc_g_per_kWh: float | None = None
    tb_eta_b_th: float | None = None

    # Corrected flow for compressor operating line
    m_dot_corr_kg_per_s: float | None = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ----------------------------------------------------------------------
# Core helper functions
# ----------------------------------------------------------------------

def _deep_copy_cfg(cfg: Mapping[str, Any]) -> Dict[str, Any]:
    """Deep copy via JSON round‑trip to keep behaviour consistent."""
    import json
    return json.loads(json.dumps(cfg))


def _engine_displacement_total(sim: EngineSimulator) -> Tuple[float, int]:
    """Return (Vd_total_m3, n_cyl) from an EngineSimulator instance."""
    Vd_cyl = sim.geometry.displacement_volume()
    n_cyl = max(int(getattr(sim.operating, "num_cylinders", 1)), 1)
    return Vd_cyl * n_cyl, n_cyl


def _estimate_mass_flow(
    cfg: Mapping[str, Any],
    speed_rpm: float,
    p_int_bar: float,
    T_int_K: float,
    ve: float,
    R_air: float,
) -> float:
    """Crude estimate of total air mass flow [kg/s].

    We use a standard 4‑stroke formula with a VE factor. Stroke type is
    inferred from ``operating.stroke_type`` if present; otherwise we
    assume 4‑stroke.

    ṁ_air ≈ ρ_int V_d_total η_vol * N_cycle

    where ``N_cycle`` is the number of intake events per second, which is:

    *  N/120 for 4‑stroke (per cylinder)
    *  N/60  for 2‑stroke
    """
    sim0 = EngineSimulator.from_dict(_deep_copy_cfg(cfg))
    Vd_total_m3, n_cyl = _engine_displacement_total(sim0)

    op = cfg.get("operating", {})
    stroke = str(op.get("stroke_type", "4-stroke")).lower()
    two_stroke = ("two" in stroke) or ("2-" in stroke) or ("2stroke" in stroke)

    N = float(speed_rpm)
    if two_stroke:
        cycles_per_sec_per_cyl = N / 60.0
    else:
        cycles_per_sec_per_cyl = N / 120.0

    p_int_Pa = float(p_int_bar) * 1e5
    rho_int = p_int_Pa / (R_air * float(T_int_K))

    m_dot = rho_int * Vd_total_m3 * float(ve) * cycles_per_sec_per_cyl
    return float(m_dot)


def _corrected_mass_flow(
    m_dot: float,
    p_in_bar: float,
    T_in_K: float,
    p_ref_bar: float = 1.0,
    T_ref_K: float = 288.15,
) -> float:
    """Return compressor corrected mass flow [kg/s].

    Standard convention:

        ṁ_corr = ṁ * sqrt(T_in / T_ref) / (p_in / p_ref)
    """
    p_in_bar = max(float(p_in_bar), 1e-6)
    T_in_K = max(float(T_in_K), 1e-6)
    return float(m_dot * math.sqrt(T_in_K / T_ref_K) / (p_in_bar / p_ref_bar))


def match_turbo_over_speeds(
    base_cfg_path: str | os.PathLike[str],
    speeds_rpm: Sequence[float],
    compare_na: bool = True,
) -> Dict[str, Any]:
    """Run NA and turbocharged sweeps over a list of speeds.

    Parameters
    ----------
    base_cfg_path:
        Path to your existing engine JSON (geometry + operating + optional turbo block).
    speeds_rpm:
        List of engine speeds [rpm].
    compare_na:
        If True, we also run a baseline NA case at each speed using the
        original intake conditions from the JSON.

    Returns
    -------
    A dict with:
        * "config" → a copy of the turbo config used
        * "speeds_rpm" → list of speeds
        * "points" → list of :class:`TurboMatchPoint`.to_dict()
    """
    cfg = io.load_json(base_cfg_path)
    tcfg = TurboConfig.from_config(cfg)
    points: List[TurboMatchPoint] = []

    # Baseline intake conditions (NA)
    op0 = cfg.get("operating", {})
    p_int_na_Pa = float(op0.get("intake_pressure_Pa", tcfg.p_amb_bar * 1e5))
    T_int_na_K = float(op0.get("intake_temperature_K", tcfg.T_amb_K))

    for N in speeds_rpm:
        N = float(N)
        pt = TurboMatchPoint(speed_rpm=N)

        # 1) Baseline NA point (optional)
        if compare_na:
            cfg_na = _deep_copy_cfg(cfg)
            op_na = cfg_na.setdefault("operating", {})
            op_na["engine_speed_rpm"] = N
            op_na["intake_pressure_Pa"] = p_int_na_Pa
            op_na["intake_temperature_K"] = T_int_na_K

            sim_na = EngineSimulator.from_dict(cfg_na)
            res_na = sim_na.run(cycles=1)

            pt.na_bmep_bar = res_na.bmep_bar
            pt.na_torque_Nm = res_na.brake_torque_Nm
            pt.na_power_kW = res_na.brake_power_kW
            pt.na_bsfc_g_per_kWh = res_na.bsfc_g_per_kWh
            pt.na_eta_b_th = res_na.brake_thermal_efficiency

        # 2) Turbo operating point
        if not tcfg.enabled:
            points.append(pt)
            continue

        PR = tcfg.boost_pressure_ratio(N)
        p2_bar, T2_int = tcfg.manifold_state_from_PR(PR)

        # Estimate mass flow
        m_dot = _estimate_mass_flow(
            cfg=cfg,
            speed_rpm=N,
            p_int_bar=p2_bar,
            T_int_K=T2_int,
            ve=tcfg.volumetric_efficiency,
            R_air=tcfg.R_air_J_per_kgK,
        )
        m_corr = _corrected_mass_flow(
            m_dot=m_dot,
            p_in_bar=tcfg.p_amb_bar,
            T_in_K=tcfg.T_amb_K,
        )

        # Run engine at boosted intake state
        cfg_tb = _deep_copy_cfg(cfg)
        op_tb = cfg_tb.setdefault("operating", {})
        op_tb["engine_speed_rpm"] = N
        op_tb["intake_pressure_Pa"] = p2_bar * 1e5
        op_tb["intake_temperature_K"] = T2_int

        sim_tb = EngineSimulator.from_dict(cfg_tb)
        res_tb = sim_tb.run(cycles=1)

        pt.pr_c = PR
        pt.p_int_bar = p2_bar
        pt.T_int_K = T2_int
        pt.m_dot_air_kg_per_s = m_dot
        pt.m_dot_corr_kg_per_s = m_corr

        pt.tb_bmep_bar = res_tb.bmep_bar
        pt.tb_torque_Nm = res_tb.brake_torque_Nm
        pt.tb_power_kW = res_tb.brake_power_kW
        pt.tb_bsfc_g_per_kWh = res_tb.bsfc_g_per_kWh
        pt.tb_eta_b_th = res_tb.brake_thermal_efficiency

        points.append(pt)

    return {
        "turbo_config": asdict(tcfg),
        "speeds_rpm": [float(N) for N in speeds_rpm],
        "points": [p.to_dict() for p in points],
    }
