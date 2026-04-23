from __future__ import annotations
from dataclasses import dataclass

import math

from .thermo_state import ThermoState


@dataclass
class ProgressVariableReactor:
    """Very simple 0-D reactor based on a single progress variable.

    This is *not* a detailed chemical-kinetics model. It is meant as a
    drop-in replacement for a Wiebe function when you want the burn shape
    x_b(θ) to come from an ODE rather than a closed form.

    State variables
    ---------------
    * lam : float
        Progress variable in [0, 1], analogous to mass fraction burned.
    * state : :class:`ThermoState`
        Thermodynamic state of the zone (typically the burned or unburned
        gas). In this first version we keep T fixed and only evolve lam.
    """

    lam: float
    state: ThermoState

    def rhs(self, t: float) -> float:
        """Right-hand side dλ/dt for the progress variable ODE.

        We use a simple Arrhenius-like law modulated by (1−λ):

            dλ/dt = A * exp(−E / (R T)) * λ^m * (1 − λ)

        All parameters are set through attributes and can be tuned to
        roughly match a desired CA10/50/90 at a given operating point.
        """
        A = getattr(self, "A", 1.0e3)   # 1/s
        E = getattr(self, "E", 1.5e5)   # J/mol
        m = getattr(self, "m", 1.0)
        R = 8.314462618
        T = self.state.T

        k = A * math.exp(-E / (R * max(T, 300.0)))
        return k * (self.lam ** m) * (1.0 - self.lam)

    def step(self, dt: float) -> None:
        """Advance the reactor by a small time step ``dt`` using RK4."""
        lam0 = self.lam
        k1 = self.rhs(0.0)
        k2 = self.rhs(0.0) + 0.5 * dt * k1
        k3 = self.rhs(0.0) + 0.5 * dt * k2
        k4 = self.rhs(0.0) + dt * k3

        self.lam = max(0.0, min(1.0, lam0 + dt * (k1 + 2 * k2 + 2 * k3 + k4) / 6.0))
