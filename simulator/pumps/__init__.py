from __future__ import annotations

"""Pump analysis tools for vICE.

Initial scope:
- curve-based centrifugal water-pump model
- pump/system operating point matching
- affinity-law speed scaling
- RPM sweeps
- hydraulic/shaft power
- NPSH margin checks
"""

from .system_curve import QuadraticSystemCurve
from .cavitation import SuctionState
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
    "CentrifugalWaterPump",
    "PumpOperatingPoint",
    "QuadraticSystemCurve",
    "SuctionState",
    "load_system_json",
    "match_system",
    "rpm_sweep",
    "write_points_csv",
    "write_points_json",
]
