from __future__ import annotations

"""Series and parallel centrifugal-pump combinations.

The physical rules are intentionally simple and transparent:

* Parallel pumps add flow at the same head. For N identical pumps, the
  combined head at total flow Q is H_single(Q / N).
* Series pumps add head at the same flow. For N identical pumps, the
  combined head at flow Q is N * H_single(Q).

These rules are the direct computational version of Frank White's pump
combination discussion and are useful for exploratory vICE cooling-system
studies before supplier-grade pump maps are available.
"""

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Mapping
import csv
import json

from .cavitation import SuctionState, npsh_margin_ft
from .power import (
    brake_horsepower_from_efficiency,
    flow_to_gpm,
    hp_to_kw,
    water_horsepower_from_curve_flow,
)
from .system_curve import QuadraticSystemCurve
from .water_pump import CentrifugalWaterPump, _find_bracket, _bisect


@dataclass(frozen=True)
class CombinedPumpOperatingPoint:
    """Operating point for an identical-pump series/parallel arrangement."""

    pump_name: str
    arrangement: str
    number_of_pumps: int
    pump_speed_rpm: float
    engine_speed_rpm: float | None

    flow_total: float
    flow_total_gpm: float
    flow_per_pump: float
    flow_per_pump_gpm: float

    head_combined_ft: float
    head_system_ft: float
    head_per_pump_ft: float

    efficiency_per_pump: float | None
    water_hp_total: float
    brake_hp_total: float | None
    brake_kw_total: float | None
    brake_hp_per_pump: float | None
    brake_kw_per_pump: float | None

    npsha_ft: float | None
    npshr_per_pump_ft: float | None
    npsh_margin_ft: float | None

    bep_flow_per_pump: float | None
    bep_ratio_per_pump: float | None
    status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BepSpeedResult:
    """Result for the speed needed to put a pump on its scaled BEP."""

    pump_name: str
    possible: bool
    reason: str
    reference_speed_rpm: float
    target_speed_rpm: float | None
    speed_ratio: float | None
    speed_ratio_squared: float | None
    bep_flow_reference: float | None
    bep_head_reference_ft: float | None
    target_bep_flow: float | None
    target_bep_flow_gpm: float | None
    target_bep_head_ft: float | None
    system_head_at_target_bep_ft: float | None
    residual_ft: float | None
    equation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def match_combined_system(
    pump: CentrifugalWaterPump,
    system: QuadraticSystemCurve,
    pump_speed_rpm: float,
    *,
    arrangement: str,
    number_of_pumps: int = 2,
    suction: SuctionState | None = None,
    engine_speed_rpm: float | None = None,
    npsh_margin_required_ft: float = 3.0,
    preferred_bep_min: float = 0.85,
    preferred_bep_max: float = 1.10,
    acceptable_bep_min: float = 0.70,
    acceptable_bep_max: float = 1.25,
) -> CombinedPumpOperatingPoint:
    """Match identical pumps in series or parallel against a system curve."""
    n = int(number_of_pumps)
    if n < 1:
        raise ValueError("number_of_pumps must be >= 1")

    mode = str(arrangement).strip().lower()
    if mode not in {"parallel", "series"}:
        raise ValueError("arrangement must be 'parallel' or 'series'")

    q_lo_single, q_hi_single = pump.flow_bounds_at_speed(float(pump_speed_rpm))
    q_lo_single = max(q_lo_single, 0.0)
    if mode == "parallel":
        q_lo_total = q_lo_single * n
        q_hi_total = q_hi_single * n
    else:
        q_lo_total = q_lo_single
        q_hi_total = q_hi_single

    if q_hi_total <= q_lo_total:
        raise ValueError("Invalid combined-pump flow bounds")

    def per_pump_flow(q_total: float) -> float:
        return float(q_total) / n if mode == "parallel" else float(q_total)

    def combined_head(q_total: float) -> float:
        q_each = per_pump_flow(q_total)
        h_each = pump.head_ft(q_each, pump_speed_rpm)
        return h_each if mode == "parallel" else n * h_each

    def residual(q_total: float) -> float:
        return combined_head(q_total) - system.head_ft(q_total)

    bracket = _find_bracket(residual, q_lo_total, q_hi_total, n=400)
    if bracket is None:
        samples = [q_lo_total + (q_hi_total - q_lo_total) * i / 400.0 for i in range(401)]
        q_best = min(samples, key=lambda q: abs(residual(q)))
        raise ValueError(
            "Could not bracket a combined pump/system intersection. "
            f"Closest point: Q_total={q_best:.6g}, residual={residual(q_best):.6g} ft"
        )

    q_total = _bisect(residual, bracket[0], bracket[1], tol=1e-9, max_iter=120)
    q_each = per_pump_flow(q_total)
    h_each = pump.head_ft(q_each, pump_speed_rpm)
    h_comb = combined_head(q_total)
    h_sys = system.head_ft(q_total)

    eta_each = pump.efficiency(q_each, pump_speed_rpm)
    q_total_gpm = flow_to_gpm(q_total, pump.flow_unit)
    q_each_gpm = flow_to_gpm(q_each, pump.flow_unit)

    # Hydraulic power is based on total flow through the combined head.
    # This is equivalent to summing the per-pump hydraulic powers for identical pumps.
    whp_total = water_horsepower_from_curve_flow(
        q_total,
        pump.flow_unit,
        h_comb,
        specific_gravity=pump.specific_gravity,
    )
    bhp_total = brake_horsepower_from_efficiency(whp_total, eta_each)
    bkw_total = hp_to_kw(bhp_total)
    bhp_each = (bhp_total / n) if bhp_total is not None else None
    bkw_each = hp_to_kw(bhp_each)

    # Shared suction piping often sees total flow. Use total flow for NPSHA,
    # but each pump only requires NPSHR at the flow it sees.
    npsha = suction.npsha_ft(q_total) if suction is not None else None
    npshr_each = pump.npshr_ft(q_each, pump_speed_rpm)
    margin = npsh_margin_ft(npsha, npshr_each)

    bep_each = pump.bep_flow_at_speed(pump_speed_rpm)
    bep_ratio_each = (q_each / bep_each) if bep_each and bep_each > 0.0 else None

    status = _combined_status(
        bep_ratio_each,
        margin,
        npsh_margin_required_ft,
        preferred_bep_min,
        preferred_bep_max,
        acceptable_bep_min,
        acceptable_bep_max,
    )

    return CombinedPumpOperatingPoint(
        pump_name=pump.name,
        arrangement=mode,
        number_of_pumps=n,
        pump_speed_rpm=float(pump_speed_rpm),
        engine_speed_rpm=float(engine_speed_rpm) if engine_speed_rpm is not None else None,
        flow_total=q_total,
        flow_total_gpm=q_total_gpm,
        flow_per_pump=q_each,
        flow_per_pump_gpm=q_each_gpm,
        head_combined_ft=h_comb,
        head_system_ft=h_sys,
        head_per_pump_ft=h_each,
        efficiency_per_pump=eta_each,
        water_hp_total=whp_total,
        brake_hp_total=bhp_total,
        brake_kw_total=bkw_total,
        brake_hp_per_pump=bhp_each,
        brake_kw_per_pump=bkw_each,
        npsha_ft=npsha,
        npshr_per_pump_ft=npshr_each,
        npsh_margin_ft=margin,
        bep_flow_per_pump=bep_each,
        bep_ratio_per_pump=bep_ratio_each,
        status=status,
    )


def bep_speed_to_match_system(
    pump: CentrifugalWaterPump,
    system: QuadraticSystemCurve,
) -> BepSpeedResult:
    """Return the pump speed needed for the scaled BEP to lie on the system curve.

    This is the programmatic form of Frank White Example 11.6 part (b).
    The closed-form solution is exact for a quadratic system curve with the
    same flow unit as the pump curve:

        H_bep*r^2 = H_static + K*(Q_bep*r)^2

    where r = n_target / n_reference.
    """
    if pump.bep_flow is None or pump.bep_head is None:
        return BepSpeedResult(
            pump_name=pump.name,
            possible=False,
            reason="Pump JSON must define bep_flow and bep_head.",
            reference_speed_rpm=pump.reference_speed_rpm,
            target_speed_rpm=None,
            speed_ratio=None,
            speed_ratio_squared=None,
            bep_flow_reference=pump.bep_flow,
            bep_head_reference_ft=pump.bep_head,
            target_bep_flow=None,
            target_bep_flow_gpm=None,
            target_bep_head_ft=None,
            system_head_at_target_bep_ft=None,
            residual_ft=None,
            equation="H_bep*r^2 = H_static + K*(Q_bep*r)^2",
        )

    if abs(float(system.exponent) - 2.0) > 1e-12:
        return BepSpeedResult(
            pump_name=pump.name,
            possible=False,
            reason="Closed-form BEP-speed check currently requires system exponent = 2.",
            reference_speed_rpm=pump.reference_speed_rpm,
            target_speed_rpm=None,
            speed_ratio=None,
            speed_ratio_squared=None,
            bep_flow_reference=pump.bep_flow,
            bep_head_reference_ft=pump.bep_head,
            target_bep_flow=None,
            target_bep_flow_gpm=None,
            target_bep_head_ft=None,
            system_head_at_target_bep_ft=None,
            residual_ft=None,
            equation="H_bep*r^2 = H_static + K*(Q_bep*r)^2",
        )

    q0 = float(pump.bep_flow)
    h0 = float(pump.bep_head)
    h_static = float(system.static_head_ft)
    k = float(system.k)
    denom = h0 - k * q0 * q0

    eqn = f"{h0:g}*r^2 = {h_static:g} + {k:g}*({q0:g}*r)^2"
    if abs(denom) < 1e-15:
        reason = "No finite nonzero speed satisfies the scaled BEP/system equation; denominator is zero."
        r2 = None
    else:
        r2 = h_static / denom
        reason = "OK" if r2 > 0.0 else "No real pump speed can place the scaled BEP point on this system curve."

    if r2 is None or r2 <= 0.0:
        return BepSpeedResult(
            pump_name=pump.name,
            possible=False,
            reason=reason,
            reference_speed_rpm=pump.reference_speed_rpm,
            target_speed_rpm=None,
            speed_ratio=None,
            speed_ratio_squared=r2,
            bep_flow_reference=q0,
            bep_head_reference_ft=h0,
            target_bep_flow=None,
            target_bep_flow_gpm=None,
            target_bep_head_ft=None,
            system_head_at_target_bep_ft=None,
            residual_ft=None,
            equation=eqn,
        )

    r = r2 ** 0.5
    q_target = q0 * r
    h_target = h0 * r2
    h_system = system.head_ft(q_target)
    residual = h_target - h_system

    return BepSpeedResult(
        pump_name=pump.name,
        possible=True,
        reason="Scaled BEP point intersects the system curve.",
        reference_speed_rpm=pump.reference_speed_rpm,
        target_speed_rpm=pump.reference_speed_rpm * r,
        speed_ratio=r,
        speed_ratio_squared=r2,
        bep_flow_reference=q0,
        bep_head_reference_ft=h0,
        target_bep_flow=q_target,
        target_bep_flow_gpm=flow_to_gpm(q_target, pump.flow_unit),
        target_bep_head_ft=h_target,
        system_head_at_target_bep_ft=h_system,
        residual_ft=residual,
        equation=eqn,
    )


def write_combined_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def write_combined_csv(path: str | Path, points: list[CombinedPumpOperatingPoint]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [p.to_dict() for p in points]
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _combined_status(
    bep_ratio: float | None,
    npsh_margin: float | None,
    npsh_margin_required_ft: float,
    preferred_bep_min: float,
    preferred_bep_max: float,
    acceptable_bep_min: float,
    acceptable_bep_max: float,
) -> str:
    flags: list[str] = []
    if bep_ratio is not None:
        r = float(bep_ratio)
        if preferred_bep_min <= r <= preferred_bep_max:
            pass
        elif acceptable_bep_min <= r < preferred_bep_min:
            flags.append("ACCEPTABLE_LEFT_OF_BEP")
        elif preferred_bep_max < r <= acceptable_bep_max:
            flags.append("ACCEPTABLE_RIGHT_OF_BEP")
        elif r < acceptable_bep_min:
            flags.append("OFF_DESIGN_LOW_FLOW_BEP")
        else:
            flags.append("OFF_DESIGN_HIGH_FLOW_BEP")

    if npsh_margin is not None:
        margin = float(npsh_margin)
        required = max(float(npsh_margin_required_ft), 0.0)
        if margin < required:
            flags.append("CAVITATION_MARGIN_LOW")
        elif required > 0.0 and margin < 2.0 * required:
            flags.append("NPSH_MARGIN_WATCH")

    return "OK" if not flags else ";".join(flags)
