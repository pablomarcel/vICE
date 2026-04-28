from __future__ import annotations

"""System-head models for pump/system matching."""

from dataclasses import dataclass, asdict
from typing import Any, Mapping


@dataclass(frozen=True)
class QuadraticSystemCurve:
    """System curve H = H_static + K Q^exponent.

    For turbulent piping and cooling passages, exponent=2 is the usual first
    model. Units are intentionally tied to the input data: if Q is in gpm and H
    is in ft, then K has units ft / gpm^2. For Frank White Example 11.6, Q is in
    thousands of gal/min, so K has units ft / (1000 gal/min)^2.
    """

    static_head_ft: float = 0.0
    k: float = 0.0
    exponent: float = 2.0
    flow_unit: str = "gpm"
    head_unit: str = "ft"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "QuadraticSystemCurve":
        curve = dict(data.get("system_curve", data))
        model = str(curve.get("model", "quadratic")).lower()
        if model not in {"quadratic", "power", "system_quadratic"}:
            raise ValueError(f"Unsupported system curve model: {model!r}")
        return cls(
            static_head_ft=float(curve.get("static_head_ft", curve.get("static_head", 0.0))),
            k=float(curve.get("k", curve.get("loss_coefficient", 0.0))),
            exponent=float(curve.get("exponent", 2.0)),
            flow_unit=str(curve.get("flow_unit", data.get("flow_unit", "gpm"))),
            head_unit=str(curve.get("head_unit", data.get("head_unit", "ft"))),
        )

    def head_ft(self, flow: float) -> float:
        return float(self.static_head_ft) + float(self.k) * (max(float(flow), 0.0) ** float(self.exponent))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
