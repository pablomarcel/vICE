from __future__ import annotations

"""NPSH and cavitation-margin helpers for pump analysis."""

from dataclasses import dataclass, asdict
from typing import Any, Mapping

FT_PER_M = 3.280839895
M_PER_FT = 1.0 / FT_PER_M
G = 9.80665


@dataclass(frozen=True)
class SuctionState:
    """Suction-side state used to estimate NPSH available.

    The simplest path is to provide ``fixed_npsha_ft`` in the input JSON. If it
    is not provided, the calculation uses absolute suction pressure, vapor
    pressure, suction velocity, elevation, and suction-side losses.

    For RPM sweeps, the optional flow-dependent loss coefficients make the
    model more realistic:

    ``suction_loss_k_ft_per_flow2``
        Additional suction loss in feet: ``h_loss = K * Q**2``. The flow unit is
        the native pump/system flow unit for the run, usually gpm.

    ``suction_loss_k_m_per_flow2``
        Same idea, but coefficient is expressed in meters of loss.

    These coefficients are intentionally unit-light because the pump package is
    curve-first: if the pump/system curves use gpm, then K is ft/gpm^2 or
    m/gpm^2; if they use 1000_gal_per_min, then K follows that curve unit.
    """

    fixed_npsha_ft: float | None = None
    absolute_pressure_kPa: float | None = None
    vapor_pressure_kPa: float | None = None
    rho_kg_per_m3: float = 1000.0
    suction_velocity_m_per_s: float = 0.0
    suction_elevation_m: float = 0.0
    suction_losses_m: float = 0.0
    suction_loss_k_ft_per_flow2: float = 0.0
    suction_loss_k_m_per_flow2: float = 0.0

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "SuctionState":
        if not data:
            return cls()
        return cls(
            fixed_npsha_ft=_optional_float(data.get("fixed_npsha_ft")),
            absolute_pressure_kPa=_optional_float(data.get("absolute_pressure_kPa")),
            vapor_pressure_kPa=_optional_float(data.get("vapor_pressure_kPa")),
            rho_kg_per_m3=float(data.get("rho_kg_per_m3", data.get("density_kg_per_m3", 1000.0))),
            suction_velocity_m_per_s=float(data.get("suction_velocity_m_per_s", data.get("suction_velocity_m_s", 0.0))),
            suction_elevation_m=float(data.get("suction_elevation_m", 0.0)),
            suction_losses_m=float(data.get("suction_losses_m", data.get("z_loss_terms_m", 0.0))),
            suction_loss_k_ft_per_flow2=float(data.get("suction_loss_k_ft_per_flow2", 0.0)),
            suction_loss_k_m_per_flow2=float(data.get("suction_loss_k_m_per_flow2", 0.0)),
        )

    def npsha_ft(self, flow: float | None = None) -> float | None:
        """Return NPSH available [ft].

        Parameters
        ----------
        flow:
            Optional operating flow in the native pump/system flow unit. When
            provided, any configured ``K*Q^2`` suction-loss terms are subtracted
            from NPSHA. ``fixed_npsha_ft`` remains fixed by design and bypasses
            the calculated model.
        """
        if self.fixed_npsha_ft is not None:
            return float(self.fixed_npsha_ft)
        if self.absolute_pressure_kPa is None or self.vapor_pressure_kPa is None:
            return None

        rho = max(float(self.rho_kg_per_m3), 1e-9)
        pressure_head_m = ((float(self.absolute_pressure_kPa) - float(self.vapor_pressure_kPa)) * 1000.0) / (rho * G)
        velocity_head_m = float(self.suction_velocity_m_per_s) ** 2 / (2.0 * G)
        npsha_m = pressure_head_m + velocity_head_m - float(self.suction_elevation_m) - float(self.suction_losses_m)

        if flow is not None:
            q = max(float(flow), 0.0)
            npsha_m -= float(self.suction_loss_k_m_per_flow2) * q * q
            npsha_m -= float(self.suction_loss_k_ft_per_flow2) * q * q * M_PER_FT

        return npsha_m * FT_PER_M

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def npsh_margin_ft(npsha_ft: float | None, npshr_ft: float | None) -> float | None:
    if npsha_ft is None or npshr_ft is None:
        return None
    return float(npsha_ft) - float(npshr_ft)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
