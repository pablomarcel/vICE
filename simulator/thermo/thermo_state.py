from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping
import math

import numpy as np

from .species import SPECIES_DB, Species, R_UNIVERSAL


@dataclass
class ThermoState:
    """Thermodynamic state for a gas mixture.

    The dataclass stores temperature, pressure, species mass fractions,
    density, specific heats, mixture gas constant, enthalpy, and internal
    energy for a gas mixture.

    Use :meth:`from_T_p_Y` when the mixture is described by species names in
    the internal species database. Use :meth:`from_cantera` when the state is
    supplied by a Cantera ``Solution`` object.

    The field annotations below are intentionally left as the source of truth
    for autodoc. Avoiding a separate ``Attributes`` section prevents duplicate
    object-description warnings for dataclass fields in Sphinx.
    """

    T: float
    p: float
    mass_fractions: Dict[str, float]
    rho: float
    cp: float
    cv: float
    gamma: float
    R_mix: float
    h: float
    u: float

    # ------------------------------------------------------------------
    # Path 1: our internal NASA/species model
    # ------------------------------------------------------------------

    @classmethod
    def from_T_p_Y(cls, T: float, p: float, Y: Mapping[str, float]) -> "ThermoState":
        """Build a mixture state from temperature, pressure, and mass fractions.

        Species keys must exist in :data:`SPECIES_DB`. Unknown species are
        ignored, and the remaining positive fractions are renormalized before
        mixture properties are computed.
        """
        # Filter to known species and renormalise
        Y_eff: Dict[str, float] = {}
        for name, y in Y.items():
            if name in SPECIES_DB and y > 0.0:
                Y_eff[name] = float(y)

        total = sum(Y_eff.values())
        if total <= 0.0:
            raise ValueError("No positive mass fractions supplied for known species.")

        for k in list(Y_eff.keys()):
            Y_eff[k] /= total

        # Mixture molar mass and cp, cv, h, u
        inv_M = 0.0
        cp_mix = 0.0
        cv_mix = 0.0
        h_mix = 0.0
        u_mix = 0.0

        for name, yk in Y_eff.items():
            sp: Species = SPECIES_DB[name]
            inv_M += yk / sp.molar_mass
            cp_k = sp.cp_mass(T)
            cv_k = cp_k - R_UNIVERSAL / sp.molar_mass
            h_k = sp.h_mass(T)
            u_k = h_k - R_UNIVERSAL * T / sp.molar_mass
            cp_mix += yk * cp_k
            cv_mix += yk * cv_k
            h_mix += yk * h_k
            u_mix += yk * u_k

        M_mix = 1.0 / inv_M
        R_mix = R_UNIVERSAL / M_mix

        rho = p / (R_mix * T)
        gamma = cp_mix / cv_mix if cv_mix > 0.0 else math.inf

        return cls(
            T=float(T),
            p=float(p),
            mass_fractions=dict(Y_eff),
            rho=float(rho),
            cp=float(cp_mix),
            cv=float(cv_mix),
            gamma=float(gamma),
            R_mix=float(R_mix),
            h=float(h_mix),
            u=float(u_mix),
        )

    # ------------------------------------------------------------------
    # Path 2: from a Cantera Solution object
    # ------------------------------------------------------------------

    @classmethod
    def from_cantera(cls, gas) -> "ThermoState":
        """Build a mixture state from a Cantera ``Solution`` object.

        Cantera provides the thermodynamic properties directly. The mixture
        gas constant is computed from the ideal-gas identity
        ``R_mix = cp_mass - cv_mass`` so the method does not depend on
        version-specific Cantera attributes.
        """
        T = float(gas.T)
        p = float(gas.P)
        rho = float(gas.density)

        cp = float(gas.cp_mass)        # [J/kg-K]
        cv = float(gas.cv_mass)        # [J/kg-K]
        gamma = cp / cv if cv > 0.0 else 1.4
        R_mix = cp - cv                # ideal-gas identity

        h = float(gas.enthalpy_mass)       # [J/kg]
        u = float(gas.int_energy_mass)     # [J/kg]

        Y = np.asarray(gas.Y, dtype=float)
        mass_fractions: Dict[str, float] = {}
        for name, yk in zip(gas.species_names, Y):
            if abs(yk) > 1e-12:
                mass_fractions[name] = float(yk)

        return cls(
            T=T,
            p=p,
            mass_fractions=mass_fractions,
            rho=rho,
            cp=cp,
            cv=cv,
            gamma=gamma,
            R_mix=R_mix,
            h=h,
            u=u,
        )

    # ------------------------------------------------------------------
    # Convenience updaters
    # ------------------------------------------------------------------

    def copy_with_T_p(self, T: float | None = None, p: float | None = None) -> "ThermoState":
        """Return a new state with updated temperature and/or pressure.

        The new state is recomputed through :meth:`from_T_p_Y` using the
        existing mass fractions. If the original state came from Cantera and
        contains species that are not present in :data:`SPECIES_DB`, those
        species are ignored during recomputation.
        """
        T_new = self.T if T is None else float(T)
        p_new = self.p if p is None else float(p)
        return ThermoState.from_T_p_Y(T_new, p_new, self.mass_fractions)

    def copy_with(self, **changes: Any) -> "ThermoState":
        """Return a shallow copy with arbitrary field overrides.

        This helper does not recompute thermodynamic properties. It simply
        replaces selected dataclass fields, which is useful for diagnostics or
        small reporting tweaks.

        Example::

            state2 = state.copy_with(T=2100.0, p=4e6)
        """
        data = {
            "T": self.T,
            "p": self.p,
            "mass_fractions": dict(self.mass_fractions),
            "rho": self.rho,
            "cp": self.cp,
            "cv": self.cv,
            "gamma": self.gamma,
            "R_mix": self.R_mix,
            "h": self.h,
            "u": self.u,
        }
        data.update(changes)
        return ThermoState(**data)
