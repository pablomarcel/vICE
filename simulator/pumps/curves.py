from __future__ import annotations

"""Curve utilities for pump and system analysis.

The pump package is deliberately curve-first. Supplier data, textbook data,
and mock data should be represented as JSON curves and then consumed by the
solver without hardcoding a specific pump.
"""

from dataclasses import dataclass
from typing import Any, Mapping, Sequence
import bisect


Number = float | int


@dataclass(frozen=True)
class Curve1D:
    """One-dimensional curve with either tabulated points or a polynomial.

    Supported JSON forms
    --------------------
    Point curve::

        {"kind": "points", "points": [[0, 55], [20, 52], [40, 45]]}

    Polynomial curve, coefficients in descending powers::

        {"kind": "polynomial", "coefficients_desc": [-0.26, 0.0, 490.0]}

    Notes
    -----
    Point curves use linear interpolation. Values outside the point range are
    clamped by default because supplier maps are normally not valid outside
    their tested range. Set ``extrapolate=true`` in JSON to allow endpoint-slope
    extrapolation.
    """

    name: str
    kind: str
    points: tuple[tuple[float, float], ...] = ()
    coefficients_desc: tuple[float, ...] = ()
    extrapolate: bool = False

    @classmethod
    def from_dict(cls, name: str, data: Mapping[str, Any] | Sequence[Sequence[Number]]) -> "Curve1D":
        if isinstance(data, Mapping):
            kind = str(data.get("kind", "points")).lower()
            extrapolate = bool(data.get("extrapolate", False))
            if kind in {"poly", "polynomial"}:
                coeffs = data.get("coefficients_desc", data.get("coefficients", []))
                if not coeffs:
                    raise ValueError(f"Curve {name!r} polynomial has no coefficients")
                return cls(
                    name=name,
                    kind="polynomial",
                    coefficients_desc=tuple(float(c) for c in coeffs),
                    extrapolate=extrapolate,
                )
            pts = data.get("points", [])
            return cls(
                name=name,
                kind="points",
                points=_clean_points(pts, name=name),
                extrapolate=extrapolate,
            )

        return cls(name=name, kind="points", points=_clean_points(data, name=name))

    def x_min(self) -> float | None:
        if self.points:
            return self.points[0][0]
        return None

    def x_max(self) -> float | None:
        if self.points:
            return self.points[-1][0]
        return None

    def y(self, x: float) -> float:
        x = float(x)
        if self.kind == "polynomial":
            return _polyval(self.coefficients_desc, x)
        if not self.points:
            raise ValueError(f"Curve {self.name!r} has no points")
        return _interp_linear(self.points, x, extrapolate=self.extrapolate)

    def sample(self, n: int = 101, *, x_min: float | None = None, x_max: float | None = None) -> list[dict[str, float]]:
        if n < 2:
            n = 2
        if x_min is None:
            x_min = self.x_min()
        if x_max is None:
            x_max = self.x_max()
        if x_min is None or x_max is None:
            raise ValueError(f"Curve {self.name!r} needs explicit sample bounds")
        dx = (float(x_max) - float(x_min)) / float(n - 1)
        return [{"x": float(x_min) + i * dx, "y": self.y(float(x_min) + i * dx)} for i in range(n)]


def _clean_points(points: Sequence[Sequence[Number]], *, name: str) -> tuple[tuple[float, float], ...]:
    if not points:
        raise ValueError(f"Curve {name!r} has no tabulated points")
    clean: list[tuple[float, float]] = []
    for pair in points:
        if len(pair) != 2:
            raise ValueError(f"Curve {name!r} point {pair!r} is not [x, y]")
        clean.append((float(pair[0]), float(pair[1])))
    clean.sort(key=lambda p: p[0])
    for i in range(1, len(clean)):
        if clean[i][0] <= clean[i - 1][0]:
            raise ValueError(f"Curve {name!r} has duplicate or non-increasing x values")
    return tuple(clean)


def _polyval(coefficients_desc: Sequence[float], x: float) -> float:
    y = 0.0
    for c in coefficients_desc:
        y = y * x + float(c)
    return float(y)


def _interp_linear(points: Sequence[tuple[float, float]], x: float, *, extrapolate: bool = False) -> float:
    xs = [p[0] for p in points]
    if x <= xs[0]:
        if not extrapolate or len(points) == 1:
            return float(points[0][1])
        return _line(points[0], points[1], x)
    if x >= xs[-1]:
        if not extrapolate or len(points) == 1:
            return float(points[-1][1])
        return _line(points[-2], points[-1], x)

    j = bisect.bisect_left(xs, x)
    return _line(points[j - 1], points[j], x)


def _line(p0: tuple[float, float], p1: tuple[float, float], x: float) -> float:
    x0, y0 = p0
    x1, y1 = p1
    if x1 == x0:
        return float(y0)
    t = (float(x) - x0) / (x1 - x0)
    return float(y0 + t * (y1 - y0))
