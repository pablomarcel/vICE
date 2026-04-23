from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Mapping, Any
import math

import numpy as np

from .species import SPECIES_DB, Species, R_UNIVERSAL

@dataclass
class ThermoState:
    """Thermodynamic state for a gas mixture.

    Two main construction paths:

    1) from_T_p_Y(T, p, Y):
       Uses our internal NASA/species database (SPECIES_DB, Species) to
       compute cp, cv, h, u, rho, gamma, R_mix from T, p and mass fractions.

    2) from_cantera(gas):
       Builds the same fields from a Cantera Solution object, using
       Cantera's own thermo. This does *not* require SPECIES_DB to
       contain the same species – it just records the mass fractions.

    Attributes
    ----------
    T : float
        Temperature [K].
    p : float
        Pressure [Pa].
    mass_fractions : Dict[str, float]
        Mass fractions Y_k for each species.
    rho : float
        Density [kg/m³].
    cp : float
        Mass-based specific heat at constant pressure [J/(kg·K)].
    cv : float
        Mass-based specific heat at constant volume [J/(kg·K)].
    gamma : float
        cp / cv for the mixture (dimensionless).
    R_mix : float
        Gas constant of the mixture [J/(kg·K)].
    h : float
        Mixture specific enthalpy [J/kg].
    u : float
        Mixture specific internal energy [J/kg].
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
        """Build a mixture state from T, p and species mass fractions.

        The species keys must exist in :data:`SPECIES_DB`. Any missing
        species are ignored; the provided fractions are renormalised.
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
        """Build a mixture state from a Cantera Solution object.

        Uses Cantera's own thermo to populate cp, cv, h, u, rho.

        For the mixture gas constant we use the ideal-gas identity:

            R_mix = cp_mass - cv_mass

        which is valid regardless of Cantera version (no need for
        gas.gas_constant / gas.mean_molecular_weight).
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
        """Return a new state with updated T and/or p, recomputing properties.

        This *recomputes* cp, cv, etc. using the internal NASA/species
        path (from_T_p_Y) with the existing mass_fractions.

        If this ThermoState originally came from Cantera and contains
        species not in SPECIES_DB, those species will be ignored in the
        recomputation. In that case, prefer constructing a fresh state
        from Cantera instead of using this method.
        """
        T_new = self.T if T is None else float(T)
        p_new = self.p if p is None else float(p)
        return ThermoState.from_T_p_Y(T_new, p_new, self.mass_fractions)

    def copy_with(self, **changes: Any) -> "ThermoState":
        """Shallow copy with arbitrary field overrides.

        This does *not* recompute thermo; it simply changes fields.
        Useful when you want to tweak e.g. p or T for diagnostics
        without going back through NASA/Cantera.

        Example:
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
