from __future__ import annotations

"""Centrifugal water-pump models for vICE.

This module is the first production-style pumps package component. It focuses
on the coolant pump use case: curve-based centrifugal pump matching, affinity
law speed scaling, power absorption, BEP ratio, and NPSH/cavitation margin.
"""

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Mapping
import csv
import json

from .affinity import AffinityScale
from .cavitation import SuctionState, npsh_margin_ft
from .curves import Curve1D
from .power import brake_horsepower_from_efficiency, flow_to_gpm, hp_to_kw, water_horsepower_from_curve_flow
from .system_curve import QuadraticSystemCurve


@dataclass(frozen=True)
class CentrifugalWaterPump:
    name: str
    reference_speed_rpm: float
    flow_unit: str
    head_unit: str
    head_curve: Curve1D
    efficiency_curve: Curve1D | None = None
    npshr_curve: Curve1D | None = None
    bep_flow: float | None = None
    bep_head: float | None = None
    specific_gravity: float = 1.0
    valid_flow_min: float | None = None
    valid_flow_max: float | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CentrifugalWaterPump":
        curves = dict(data.get("curves", {}))
        if "head" not in curves:
            raise ValueError("Pump JSON must contain curves.head")
        head_curve = Curve1D.from_dict("head", curves["head"])
        efficiency_curve = Curve1D.from_dict("efficiency", curves["efficiency"]) if "efficiency" in curves else None
        npshr_curve = Curve1D.from_dict("npshr", curves["npshr"]) if "npshr" in curves else None

        flow_min = data.get("valid_flow_min")
        flow_max = data.get("valid_flow_max")
        if flow_min is None:
            flow_min = head_curve.x_min()
        if flow_max is None:
            flow_max = head_curve.x_max()

        return cls(
            name=str(data.get("name", "Unnamed centrifugal water pump")),
            reference_speed_rpm=float(data.get("reference_speed_rpm", data.get("speed_rpm", 1.0))),
            flow_unit=str(data.get("flow_unit", "gpm")),
            head_unit=str(data.get("head_unit", "ft")),
            head_curve=head_curve,
            efficiency_curve=efficiency_curve,
            npshr_curve=npshr_curve,
            bep_flow=_optional_float(data.get("bep_flow")),
            bep_head=_optional_float(data.get("bep_head")),
            specific_gravity=float(data.get("specific_gravity", 1.0)),
            valid_flow_min=_optional_float(flow_min),
            valid_flow_max=_optional_float(flow_max),
        )

    @classmethod
    def from_json(cls, path: str | Path) -> "CentrifugalWaterPump":
        with Path(path).open("r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def speed_scale(self, pump_speed_rpm: float) -> AffinityScale:
        return AffinityScale(reference_speed_rpm=self.reference_speed_rpm, target_speed_rpm=float(pump_speed_rpm))

    def head_ft(self, flow: float, pump_speed_rpm: float | None = None) -> float:
        if pump_speed_rpm is None:
            pump_speed_rpm = self.reference_speed_rpm
        scale = self.speed_scale(float(pump_speed_rpm))
        q_ref = scale.flow_to_reference(float(flow))
        return scale.head_from_reference(self.head_curve.y(q_ref))

    def efficiency(self, flow: float, pump_speed_rpm: float | None = None) -> float | None:
        if self.efficiency_curve is None:
            return None
        if pump_speed_rpm is None:
            pump_speed_rpm = self.reference_speed_rpm
        scale = self.speed_scale(float(pump_speed_rpm))
        q_ref = scale.flow_to_reference(float(flow))
        eta = self.efficiency_curve.y(q_ref)
        if eta > 1.0:
            eta = eta / 100.0
        return max(0.0, min(1.0, eta))

    def npshr_ft(self, flow: float, pump_speed_rpm: float | None = None) -> float | None:
        if self.npshr_curve is None:
            return None
        if pump_speed_rpm is None:
            pump_speed_rpm = self.reference_speed_rpm
        scale = self.speed_scale(float(pump_speed_rpm))
        q_ref = scale.flow_to_reference(float(flow))
        # Approximate scaling, useful for mock/preliminary analysis. Real supplier
        # NPSHR data at multiple speeds should replace this when available.
        return scale.head_from_reference(self.npshr_curve.y(q_ref))

    def bep_flow_at_speed(self, pump_speed_rpm: float) -> float | None:
        if self.bep_flow is None:
            return None
        return self.speed_scale(float(pump_speed_rpm)).flow_from_reference(self.bep_flow)

    def flow_bounds_at_speed(self, pump_speed_rpm: float) -> tuple[float, float]:
        scale = self.speed_scale(float(pump_speed_rpm))
        qmin = self.valid_flow_min if self.valid_flow_min is not None else 0.0
        qmax = self.valid_flow_max if self.valid_flow_max is not None else max(self.bep_flow or 1.0, 1.0) * 2.0
        return scale.flow_from_reference(float(qmin)), scale.flow_from_reference(float(qmax))

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "reference_speed_rpm": self.reference_speed_rpm,
            "flow_unit": self.flow_unit,
            "head_unit": self.head_unit,
            "bep_flow": self.bep_flow,
            "bep_head": self.bep_head,
            "specific_gravity": self.specific_gravity,
            "valid_flow_min": self.valid_flow_min,
            "valid_flow_max": self.valid_flow_max,
        }


@dataclass(frozen=True)
class PumpOperatingPoint:
    pump_name: str
    pump_speed_rpm: float
    engine_speed_rpm: float | None
    flow: float
    flow_gpm: float
    head_pump_ft: float
    head_system_ft: float
    efficiency: float | None
    water_hp: float
    brake_hp: float | None
    brake_kw: float | None
    npsha_ft: float | None
    npshr_ft: float | None
    npsh_margin_ft: float | None
    bep_flow: float | None
    bep_ratio: float | None
    status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_system_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def match_system(
    pump: CentrifugalWaterPump,
    system: QuadraticSystemCurve,
    pump_speed_rpm: float,
    *,
    suction: SuctionState | None = None,
    engine_speed_rpm: float | None = None,
    npsh_margin_required_ft: float = 3.0,
    preferred_bep_min: float = 0.85,
    preferred_bep_max: float = 1.10,
    acceptable_bep_min: float = 0.70,
    acceptable_bep_max: float = 1.25,
) -> PumpOperatingPoint:
    q_lo, q_hi = pump.flow_bounds_at_speed(float(pump_speed_rpm))
    q_lo = max(q_lo, 0.0)
    if q_hi <= q_lo:
        raise ValueError("Invalid pump flow bounds")

    def residual(q: float) -> float:
        return pump.head_ft(q, pump_speed_rpm) - system.head_ft(q)

    bracket = _find_bracket(residual, q_lo, q_hi, n=300)
    if bracket is None:
        # Pick the closest residual as a diagnostic fallback, but fail loudly.
        samples = [(q_lo + (q_hi - q_lo) * i / 300.0) for i in range(301)]
        q_best = min(samples, key=lambda q: abs(residual(q)))
        raise ValueError(
            "Could not bracket a pump/system intersection. "
            f"Closest point: Q={q_best:.6g}, residual={residual(q_best):.6g} ft"
        )

    q = _bisect(residual, bracket[0], bracket[1], tol=1e-9, max_iter=100)
    hpump = pump.head_ft(q, pump_speed_rpm)
    hsys = system.head_ft(q)
    eta = pump.efficiency(q, pump_speed_rpm)
    q_gpm = flow_to_gpm(q, pump.flow_unit)
    whp = water_horsepower_from_curve_flow(q, pump.flow_unit, hpump, specific_gravity=pump.specific_gravity)
    bhp = brake_horsepower_from_efficiency(whp, eta)
    bkw = hp_to_kw(bhp)

    npsha = suction.npsha_ft(q) if suction is not None else None
    npshr = pump.npshr_ft(q, pump_speed_rpm)
    margin = npsh_margin_ft(npsha, npshr)

    bep_flow = pump.bep_flow_at_speed(pump_speed_rpm)
    bep_ratio = (q / bep_flow) if bep_flow and bep_flow > 0.0 else None
    status = _status(
        bep_ratio,
        margin,
        npsh_margin_required_ft,
        preferred_bep_min,
        preferred_bep_max,
        acceptable_bep_min,
        acceptable_bep_max,
    )

    return PumpOperatingPoint(
        pump_name=pump.name,
        pump_speed_rpm=float(pump_speed_rpm),
        engine_speed_rpm=float(engine_speed_rpm) if engine_speed_rpm is not None else None,
        flow=q,
        flow_gpm=q_gpm,
        head_pump_ft=hpump,
        head_system_ft=hsys,
        efficiency=eta,
        water_hp=whp,
        brake_hp=bhp,
        brake_kw=bkw,
        npsha_ft=npsha,
        npshr_ft=npshr,
        npsh_margin_ft=margin,
        bep_flow=bep_flow,
        bep_ratio=bep_ratio,
        status=status,
    )


def rpm_sweep(
    pump: CentrifugalWaterPump,
    system: QuadraticSystemCurve,
    *,
    engine_rpm_min: float,
    engine_rpm_max: float,
    engine_rpm_step: float,
    pulley_ratio: float = 1.0,
    suction: SuctionState | None = None,
    npsh_margin_required_ft: float = 3.0,
    preferred_bep_min: float = 0.85,
    preferred_bep_max: float = 1.10,
    acceptable_bep_min: float = 0.70,
    acceptable_bep_max: float = 1.25,
) -> list[PumpOperatingPoint]:
    if engine_rpm_step <= 0.0:
        raise ValueError("engine_rpm_step must be positive")
    points: list[PumpOperatingPoint] = []
    N = float(engine_rpm_min)
    while N <= float(engine_rpm_max) + 1e-9:
        pump_rpm = N * float(pulley_ratio)
        points.append(
            match_system(
                pump,
                system,
                pump_rpm,
                suction=suction,
                engine_speed_rpm=N,
                npsh_margin_required_ft=npsh_margin_required_ft,
                preferred_bep_min=preferred_bep_min,
                preferred_bep_max=preferred_bep_max,
                acceptable_bep_min=acceptable_bep_min,
                acceptable_bep_max=acceptable_bep_max,
            )
        )
        N += float(engine_rpm_step)
    return points


def write_points_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def write_points_csv(path: str | Path, points: list[PumpOperatingPoint]) -> None:
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


def _find_bracket(func: Any, lo: float, hi: float, *, n: int) -> tuple[float, float] | None:
    q_prev = lo
    f_prev = func(q_prev)
    if abs(f_prev) < 1e-12:
        return q_prev, q_prev
    for i in range(1, n + 1):
        q = lo + (hi - lo) * i / n
        f = func(q)
        if abs(f) < 1e-12:
            return q, q
        if f_prev * f < 0.0:
            return q_prev, q
        q_prev, f_prev = q, f
    return None


def _bisect(func: Any, lo: float, hi: float, *, tol: float, max_iter: int) -> float:
    if lo == hi:
        return lo
    f_lo = func(lo)
    f_hi = func(hi)
    if f_lo * f_hi > 0.0:
        raise ValueError("Bisection requires a sign-changing bracket")
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        f_mid = func(mid)
        if abs(f_mid) < tol or abs(hi - lo) < tol:
            return mid
        if f_lo * f_mid <= 0.0:
            hi = mid
            f_hi = f_mid
        else:
            lo = mid
            f_lo = f_mid
    return 0.5 * (lo + hi)


def _status(
    bep_ratio: float | None,
    npsh_margin: float | None,
    npsh_margin_required_ft: float,
    preferred_bep_min: float,
    preferred_bep_max: float,
    acceptable_bep_min: float,
    acceptable_bep_max: float,
) -> str:
    """Return a graded engineering status for an operating point.

    The preferred BEP window marks the best operating region. The wider
    acceptable window is intentionally less alarming and is useful for textbook
    or preliminary supplier-curve studies where the pump is not exactly at BEP
    but is still operating in a defensible region.
    """
    flags: list[str] = []

    bep_flag = _bep_status(
        bep_ratio,
        preferred_bep_min=preferred_bep_min,
        preferred_bep_max=preferred_bep_max,
        acceptable_bep_min=acceptable_bep_min,
        acceptable_bep_max=acceptable_bep_max,
    )
    if bep_flag != "OK":
        flags.append(bep_flag)

    if npsh_margin is not None:
        margin = float(npsh_margin)
        required = max(float(npsh_margin_required_ft), 0.0)
        if margin < required:
            flags.append("CAVITATION_MARGIN_LOW")
        elif required > 0.0 and margin < 2.0 * required:
            flags.append("NPSH_MARGIN_WATCH")

    return "OK" if not flags else ";".join(flags)


def _bep_status(
    bep_ratio: float | None,
    *,
    preferred_bep_min: float,
    preferred_bep_max: float,
    acceptable_bep_min: float,
    acceptable_bep_max: float,
) -> str:
    """Classify an operating point relative to the best-efficiency point."""
    if bep_ratio is None:
        return "OK"

    ratio = float(bep_ratio)

    if preferred_bep_min <= ratio <= preferred_bep_max:
        return "OK"
    if acceptable_bep_min <= ratio < preferred_bep_min:
        return "ACCEPTABLE_LEFT_OF_BEP"
    if preferred_bep_max < ratio <= acceptable_bep_max:
        return "ACCEPTABLE_RIGHT_OF_BEP"
    if ratio < acceptable_bep_min:
        return "OFF_DESIGN_LOW_FLOW_BEP"
    return "OFF_DESIGN_HIGH_FLOW_BEP"


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
