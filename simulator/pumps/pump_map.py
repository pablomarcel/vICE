from __future__ import annotations

"""Pump-family map helpers for digitized supplier/textbook charts.

A supplier pump datasheet often looks more like a complete map than a single
curve: several impeller diameter head curves, efficiency contours, brake-power
lines, and an NPSHR curve. This module loads that richer JSON format and can
extract an individual impeller diameter as a ``CentrifugalWaterPump`` for the
existing operating-point solvers.
"""

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Mapping
import json

from .curves import Curve1D
from .water_pump import CentrifugalWaterPump


@dataclass(frozen=True)
class DigitizedPumpFamilyMap:
    """Digitized multi-curve pump-family map."""

    name: str
    source_note: str
    reference_speed_rpm: float
    flow_unit: str
    head_unit: str
    npsh_unit: str
    diameter_head_curves: dict[str, Curve1D]
    npshr_curve: Curve1D | None
    efficiency_contours: dict[str, tuple[tuple[float, float], ...]]
    brake_hp_lines: dict[str, tuple[tuple[float, float], ...]]
    raw: dict[str, Any]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DigitizedPumpFamilyMap":
        curves = dict(data.get("diameter_head_curves", {}))
        if not curves:
            raise ValueError("Pump-family map requires diameter_head_curves")

        diameter_head_curves = {
            str(key): Curve1D.from_dict(str(key), value)
            for key, value in curves.items()
        }

        npsh_data = data.get("npshr")
        npshr_curve = Curve1D.from_dict("npshr", npsh_data) if npsh_data else None

        eff = _clean_path_map(data.get("efficiency_contours", {}))
        bhp = _clean_path_map(data.get("brake_hp_lines", {}))

        return cls(
            name=str(data.get("name", "Digitized pump-family map")),
            source_note=str(data.get("source_note", "")),
            reference_speed_rpm=float(data.get("reference_speed_rpm", data.get("speed_rpm", 1.0))),
            flow_unit=str(data.get("flow_unit", "gpm")),
            head_unit=str(data.get("head_unit", "ft")),
            npsh_unit=str(data.get("npsh_unit", "ft")),
            diameter_head_curves=diameter_head_curves,
            npshr_curve=npshr_curve,
            efficiency_contours=eff,
            brake_hp_lines=bhp,
            raw=dict(data),
        )

    @classmethod
    def from_json(cls, path: str | Path) -> "DigitizedPumpFamilyMap":
        with Path(path).open("r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def available_diameters(self) -> list[str]:
        return sorted(self.diameter_head_curves.keys())

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source_note": self.source_note,
            "reference_speed_rpm": self.reference_speed_rpm,
            "flow_unit": self.flow_unit,
            "head_unit": self.head_unit,
            "npsh_unit": self.npsh_unit,
            "diameters": self.available_diameters(),
            "efficiency_contours": sorted(self.efficiency_contours.keys()),
            "brake_hp_lines": sorted(self.brake_hp_lines.keys()),
            "has_npshr": self.npshr_curve is not None,
        }

    def extract_pump(
        self,
        diameter_key: str,
        *,
        name: str | None = None,
        bep_flow: float | None = None,
        bep_head: float | None = None,
        efficiency_curve: Curve1D | None = None,
        npshr_curve: Curve1D | None = None,
        specific_gravity: float = 1.0,
    ) -> CentrifugalWaterPump:
        """Extract one impeller head curve as a normal solver pump.

        Efficiency contours are not automatically converted into an efficiency
        curve because they are 2-D paths. For solver work, pass a dedicated
        efficiency curve or use a separate single-pump JSON with an eta(Q) cut.
        """
        key = str(diameter_key)
        if key not in self.diameter_head_curves:
            available = ", ".join(self.available_diameters())
            raise KeyError(f"Unknown diameter {key!r}. Available: {available}")
        head = self.diameter_head_curves[key]
        return CentrifugalWaterPump(
            name=name or f"{self.name} - {key}",
            reference_speed_rpm=self.reference_speed_rpm,
            flow_unit=self.flow_unit,
            head_unit=self.head_unit,
            head_curve=head,
            efficiency_curve=efficiency_curve,
            npshr_curve=npshr_curve or self.npshr_curve,
            bep_flow=bep_flow,
            bep_head=bep_head,
            specific_gravity=specific_gravity,
            valid_flow_min=head.x_min(),
            valid_flow_max=head.x_max(),
        )


def _clean_path_map(data: Mapping[str, Any]) -> dict[str, tuple[tuple[float, float], ...]]:
    out: dict[str, tuple[tuple[float, float], ...]] = {}
    for key, value in dict(data).items():
        pts = value.get("points", value) if isinstance(value, Mapping) else value
        cleaned: list[tuple[float, float]] = []
        for p in pts:
            if len(p) != 2:
                raise ValueError(f"Path {key!r} point {p!r} is not [x, y]")
            cleaned.append((float(p[0]), float(p[1])))
        out[str(key)] = tuple(cleaned)
    return out


def load_pump_family_json(path: str | Path) -> DigitizedPumpFamilyMap:
    return DigitizedPumpFamilyMap.from_json(path)
