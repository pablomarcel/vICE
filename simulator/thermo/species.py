from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Sequence
import math
import numpy as np

# Universal gas constant [J/(mol·K)]
R_UNIVERSAL: float = 8.314462618


@dataclass
class NasaPoly7:
    """NASA 7-coefficient polynomial for one temperature range.

    This follows the common form used in NASA CEA reports:

        cp/R = a1 + a2 T + a3 T² + a4 T³ + a5 T⁴
        h/(R T) = a1 + a2 T/2 + a3 T²/3 + a4 T³/4 + a5 T⁴/5 + a6/T
        s/R = a1 ln T + a2 T + a3 T²/2 + a4 T³/3 + a5 T⁴/4 + a7

    Parameters
    ----------
    t_low, t_high : float
        Valid temperature bounds [K]. The polynomial is not extrapolated
        outside this range except in very narrow margins for robustness.
    coeffs : Sequence[float]
        The 7 polynomial coefficients [a1..a7].
    """

    t_low: float
    t_high: float
    coeffs: Sequence[float]

    def _clamp_T(self, T: float | np.ndarray) -> float | np.ndarray:
        """Clamp T to a safe range around [t_low, t_high]."""
        Tmin = max(self.t_low * 0.8, 200.0)
        Tmax = min(self.t_high * 1.2, 6000.0)
        return np.clip(T, Tmin, Tmax)

    def cp_R(self, T: float | np.ndarray) -> float | np.ndarray:
        """Dimensionless cp/R at temperature T."""
        T = self._clamp_T(T)
        a1, a2, a3, a4, a5, a6, a7 = self.coeffs
        return a1 + a2 * T + a3 * T**2 + a4 * T**3 + a5 * T**4

    def h_RT(self, T: float | np.ndarray) -> float | np.ndarray:
        """Dimensionless h/(R T) at temperature T."""
        T = self._clamp_T(T)
        a1, a2, a3, a4, a5, a6, a7 = self.coeffs
        return (
            a1
            + a2 * T / 2.0
            + a3 * T**2 / 3.0
            + a4 * T**3 / 4.0
            + a5 * T**4 / 5.0
            + a6 / T
        )

    def s_R(self, T: float | np.ndarray) -> float | np.ndarray:
        """Dimensionless entropy s/R at temperature T."""
        T = self._clamp_T(T)
        a1, a2, a3, a4, a5, a6, a7 = self.coeffs
        return (
            a1 * np.log(T)
            + a2 * T
            + a3 * T**2 / 2.0
            + a4 * T**3 / 3.0
            + a5 * T**4 / 4.0
            + a7
        )


@dataclass
class Species:
    """Basic thermodynamic model for a single chemical species.

    Parameters
    ----------
    name : str
        Identifier (e.g. "O2", "CO2", "CH4").
    molar_mass : float
        Molar mass [kg/mol].
    elements : Dict[str, int]
        Elemental composition (e.g. {"C": 1, "O": 2}).
    thermo : NasaPoly7 | None
        NASA-style polynomial data. If this is ``None`` a constant-cp
        approximation is used instead.
    cp_R_const : float
        Constant cp/R used when ``thermo`` is ``None``. For many gases
        3.5 is a reasonable ballpark (diatomic ideal gas).

    NOTE
    ----
    The default species defined in :data:`SPECIES_DB` use simple constant
    cp/R values via ``cp_R_const``. They are **not** authoritative NASA
    polynomials; they are provided only so that the rest of the code runs
    out-of-the-box. You should replace them with genuine NASA CEA / JANAF
    data for serious work.
    """

    name: str
    molar_mass: float
    elements: Dict[str, int]
    thermo: NasaPoly7 | None = None
    cp_R_const: float = 3.5

    # ---- per-species properties ----

    def cp_mass(self, T: float) -> float:
        """Return cp [J/(kg·K)] at temperature ``T``."""
        if self.thermo is not None:
            cp_R = self.thermo.cp_R(T)
        else:
            cp_R = self.cp_R_const
        return float(cp_R * R_UNIVERSAL / self.molar_mass)

    def h_mass(self, T: float) -> float:
        """Very simple sensible enthalpy model [J/kg].

        If NASA data are present we integrate the polynomial; otherwise we
        use cp_const * (T − T_ref) with T_ref = 298 K.
        """
        T_ref = 298.15
        if self.thermo is not None:
            # h(T) - h(T_ref) via dimensionless h/RT
            h_RT = self.thermo.h_RT(T) - self.thermo.h_RT(T_ref)
            return float(h_RT * R_UNIVERSAL * T / self.molar_mass)
        else:
            cp = self.cp_mass(0.5 * (T + T_ref))
            return float(cp * (T - T_ref))


# ----------------------------------------------------------------------------
# Simple in-code species database
# ----------------------------------------------------------------------------

SPECIES_DB: Dict[str, Species] = {}


def register_species(sp: Species) -> None:
    """Register a species in the global SPECIES_DB."""
    SPECIES_DB[sp.name] = sp


def get_species(name: str) -> Species:
    """Lookup helper with a clearer error message."""
    try:
        return SPECIES_DB[name]
    except KeyError as exc:
        available = ", ".join(sorted(SPECIES_DB.keys()))
        raise KeyError(
            f"Unknown species {name!r}. Available: {available}"
        ) from exc


# Minimal default set. These use constant-cp behaviour via cp_R_const.
# Values are ballpark only (cp/R ≈ 3.5 for diatomic, 4.0 for triatomic etc.)

register_species(
    Species(
        name="O2",
        molar_mass=0.031998,
        elements={"O": 2},
        thermo=None,
        cp_R_const=3.5,
    )
)

register_species(
    Species(
        name="N2",
        molar_mass=0.028014,
        elements={"N": 2},
        thermo=None,
        cp_R_const=3.5,
    )
)

register_species(
    Species(
        name="CO2",
        molar_mass=0.04401,
        elements={"C": 1, "O": 2},
        thermo=None,
        cp_R_const=4.0,
    )
)

register_species(
    Species(
        name="H2O",
        molar_mass=0.018015,
        elements={"H": 2, "O": 1},
        thermo=None,
        cp_R_const=4.0,
    )
)

register_species(
    Species(
        name="CO",
        molar_mass=0.02801,
        elements={"C": 1, "O": 1},
        thermo=None,
        cp_R_const=3.6,
    )
)

register_species(
    Species(
        name="H2",
        molar_mass=0.002016,
        elements={"H": 2},
        thermo=None,
        cp_R_const=3.5,
    )
)

register_species(
    Species(
        name="CH4",
        molar_mass=0.016043,
        elements={"C": 1, "H": 4},
        thermo=None,
        cp_R_const=3.5,
    )
)

# Simple surrogate for gasoline as iso-octane C8H18.
register_species(
    Species(
        name="C8H18",
        molar_mass=0.114232,
        elements={"C": 8, "H": 18},
        thermo=None,
        cp_R_const=4.0,
    )
)

# Alcohol fuels
register_species(
    Species(
        name="CH3OH",
        molar_mass=0.032042,
        elements={"C": 1, "H": 4, "O": 1},
        thermo=None,
        cp_R_const=4.0,
    )
)

register_species(
    Species(
        name="C2H5OH",
        molar_mass=0.046069,
        elements={"C": 2, "H": 6, "O": 1},
        thermo=None,
        cp_R_const=4.0,
    )
)
