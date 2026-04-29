from __future__ import annotations

"""Pump-analysis package for vICE."""

from .affinity import AffinityScale
from .cavitation import SuctionState, npsh_margin_ft
from .combined import (
    BepSpeedResult,
    CombinedPumpOperatingPoint,
    bep_speed_to_match_system,
    match_combined_system,
    write_combined_csv,
    write_combined_json,
)
from .curves import Curve1D
from .pump_map import DigitizedPumpFamilyMap, load_pump_family_json
from .system_curve import QuadraticSystemCurve
from .water_pump import (
    CentrifugalWaterPump,
    PumpOperatingPoint,
    load_system_json,
    match_system,
    rpm_sweep,
    write_points_csv,
    write_points_json,
)

__all__ = [
    "AffinityScale",
    "BepSpeedResult",
    "CentrifugalWaterPump",
    "CombinedPumpOperatingPoint",
    "Curve1D",
    "DigitizedPumpFamilyMap",
    "PumpOperatingPoint",
    "QuadraticSystemCurve",
    "SuctionState",
    "bep_speed_to_match_system",
    "load_pump_family_json",
    "load_system_json",
    "match_combined_system",
    "match_system",
    "npsh_margin_ft",
    "rpm_sweep",
    "write_combined_csv",
    "write_combined_json",
    "write_points_csv",
    "write_points_json",
]
