from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Literal

import math

from simulator.fuels import get_fuel
from .species import SPECIES_DB, Species, R_UNIVERSAL
from .thermo_state import ThermoState


# ----------------------------------------------------------------------------
# Simple stoichiometric tools
# ----------------------------------------------------------------------------

def parse_empirical_formula(formula: str) -> Dict[str, int]:
    """Parse a very small subset of chemical formulas (C_a H_b O_c N_d).

    This is intentionally limited but covers common fuels like CH4,
    C8H18, CH3OH, C2H5OH, etc.

    Examples
    --------
    >>> parse_empirical_formula("C8H18")
    {'C': 8, 'H': 18}
    """
    import re

    tokens = re.findall(r"([A-Z][a-z]*)([0-9]*)", formula)
    elems: Dict[str, int] = {}
    for sym, num in tokens:
        n = int(num) if num else 1
        elems[sym] = elems.get(sym, 0) + n
    if not elems:
        raise ValueError(f"Could not parse empirical formula: {formula!r}")
    return elems


def stoich_O2_for_complete_combustion(fuel_formula: str) -> float:
    """Return stoichiometric moles of O2 per mole of fuel.

    Assumes complete conversion of C→CO2 and H→H2O and any O in the
    fuel contributes its share.
    """
    elems = parse_empirical_formula(fuel_formula)
    a = elems.get("C", 0)
    b = elems.get("H", 0)
    c = elems.get("O", 0)
    return a + b / 4.0 - c / 2.0


# ----------------------------------------------------------------------------
# Legacy ideal complete-combustion "equilibrium" model (no dissociation)
# ----------------------------------------------------------------------------

@dataclass
class IdealEquilibriumResult:
    """Result of the simple equilibrium calculation.

    This is *not* a full Gibbs-minimisation model. It assumes:

    * One global reaction with complete combustion to CO2 and H2O.
    * No dissociation or minor species.
    * Air = O2 + 3.76 N2.
    """

    T_ad: float
    p: float
    burned_state: ThermoState
    species_moles: Dict[str, float]


def _legacy_complete_combustion_equilibrium(
    fuel_name: str,
    phi: float,
    p: float,
    T_intake: float,
    afr_stoich: float,
) -> IdealEquilibriumResult:
    """Your original constant-cp complete-combustion model.

    - Fuel species must exist in SPECIES_DB (e.g. 'C8H18', 'CH3OH').
    - Uses stoichiometric O2 requirement from empirical formula.
    - Distributes products into CO2 / H2O (+ O2 / fuel if lean/rich).
    - Uses ThermoState.from_T_p_Y to build burned/unburned states.
    """
    if fuel_name not in SPECIES_DB:
        raise KeyError(f"Fuel species {fuel_name!r} not in SPECIES_DB.")
    fuel_sp: Species = SPECIES_DB[fuel_name]

    # 1 mole of fuel
    n_fuel = 1.0
    # Stoichiometric O2 requirement (mol per mol fuel)
    nu_O2_st = stoich_O2_for_complete_combustion(fuel_sp.name)
    if nu_O2_st <= 0.0:
        raise ValueError("Non-combustible fuel formula (no C/H content).")

    # Air composition: O2 + 3.76 N2 by mol
    # Equivalence ratio:
    #   phi = (F/A)_act / (F/A)_st  =>  (A/F)_act = (A/F)_st / phi
    # Stoichiometric air moles for 1 mol fuel:
    #   n_air,st = (afr_stoich * n_fuel * M_fuel) / M_air
    M_air = 0.02897
    n_air_st = afr_stoich * n_fuel * fuel_sp.molar_mass / M_air
    n_air_act = n_air_st / max(phi, 1e-6)

    n_O2_in = 0.21 * n_air_act
    n_N2_in = 0.79 * n_air_act

    # Product composition for complete combustion (no CO, no H2, no dissociation)
    elems_fuel = parse_empirical_formula(fuel_sp.name)
    a = elems_fuel.get("C", 0)
    b = elems_fuel.get("H", 0)

    n_CO2 = a * n_fuel
    n_H2O = (b / 2.0) * n_fuel

    nu_O2_needed = nu_O2_st * n_fuel
    if n_O2_in >= nu_O2_needed:
        # Lean or stoich: all fuel burned, some O2 left.
        n_O2_out = n_O2_in - nu_O2_needed
        n_fuel_unburned = 0.0
    else:
        # Rich: all O2 consumed, some fuel left unburned.
        n_O2_out = 0.0
        burned_fraction = n_O2_in / max(nu_O2_needed, 1e-12)
        n_fuel_unburned = n_fuel * (1.0 - burned_fraction)
        n_CO2 *= burned_fraction
        n_H2O *= burned_fraction

    n_N2_out = n_N2_in

    n_prod: Dict[str, float] = {
        "CO2": n_CO2,
        "H2O": n_H2O,
        "O2": n_O2_out,
        "N2": n_N2_out,
    }
    if n_fuel_unburned > 0.0:
        n_prod[fuel_sp.name] = n_fuel_unburned

    # Convert mole fractions to mass fractions.
    def mole_to_mass_fractions(n: Dict[str, float]) -> Dict[str, float]:
        mass: Dict[str, float] = {}
        for name, ni in n.items():
            if name not in SPECIES_DB or ni <= 0.0:
                continue
            sp = SPECIES_DB[name]
            mass[name] = ni * sp.molar_mass
        total_m = sum(mass.values())
        if total_m <= 0.0:
            raise ValueError("Total mixture mass is zero in mole_to_mass_fractions.")
        return {k: v / total_m for k, v in mass.items()}

    n_react: Dict[str, float] = {
        fuel_sp.name: n_fuel,
        "O2": n_O2_in,
        "N2": n_N2_in,
    }

    Y_react = mole_to_mass_fractions(n_react)
    Y_prod = mole_to_mass_fractions(n_prod)

    st_react = ThermoState.from_T_p_Y(T_intake, p, Y_react)

    # Constant-cp adiabatic flame temperature: very crude.
    T_ref = 298.15
    cp_react = st_react.cp
    # Rough guess: products cp is ~10–15 % higher than reactants.
    cp_prod_guess = 1.12 * cp_react

    # q_release per unit mass mixture – placeholder:
    # here we mimic a ~2000 K rise at constant cp_prod.
    deltaT_nominal = 2000.0
    q_release = cp_prod_guess * deltaT_nominal

    T_ad = T_intake + q_release / max(cp_prod_guess, 1e-9)

    st_prod = ThermoState.from_T_p_Y(T_ad, p, Y_prod)

    return IdealEquilibriumResult(
        T_ad=T_ad,
        p=p,
        burned_state=st_prod,
        species_moles=n_prod,
    )


# ----------------------------------------------------------------------------
# New backends: simple LHV-based "ideal cp" + Cantera HP equilibrium
# ----------------------------------------------------------------------------

BackendType = Literal["legacy", "ideal", "cantera"]


def _ideal_cp_energy_balance(
    fuel_id: str,
    phi: float,
    p: float,
    T_intake: float,
) -> IdealEquilibriumResult:
    """Adiabatic flame temperature using a constant-cp, LHV-based model.

    Basis: 1 kg of air. For a given equivalence ratio φ:

        F/A_st  = 1 / AFR_st
        F/A_act = φ * F/A_st

        m_air   = 1 kg
        m_fuel  = F/A_act * m_air
        m_mix   = m_air + m_fuel

    Oxygen-limited burning for rich mixtures:
        m_fuel_burned = min(m_fuel, F/A_st * m_air)

    Q_in = m_fuel_burned * LHV

    T_ad = T_intake + Q_in / (m_mix * cp_mix)

    With a suitable cp_mix, this produces a realistic peak near φ ≈ 1 and
    lower T_ad for both lean and rich mixtures.
    """
    fuel = get_fuel(fuel_id)
    afr_st = fuel.afr_stoich              # [kg air / kg fuel]
    F_over_A_st = 1.0 / afr_st            # [kg fuel / kg air]

    # Basis: 1 kg of air
    m_air = 1.0
    F_over_A_act = phi * F_over_A_st
    m_fuel = F_over_A_act * m_air         # actual fuel in the mix
    m_mix = m_air + m_fuel

    # Oxygen-limited burning for rich mixtures (φ > 1)
    m_fuel_st_for_1kg_air = F_over_A_st * m_air
    m_fuel_burned = min(m_fuel, m_fuel_st_for_1kg_air)

    # Heat release [J]
    Q_in = m_fuel_burned * fuel.LHV_J_per_kg

    # Constant cp_mix; tuned so gasoline at φ≈1, Tin≈300 K gives ~2150–2200 K
    cp_mix = 1.5e3  # [J/(kg·K)]

    dT = Q_in / (m_mix * cp_mix)
    T_ad = T_intake + dT

    # Crude perfect-gas mixture properties (just placeholders)
    R_mix = 287.0  # J/(kg·K), air-like
    rho = p / (R_mix * T_ad)
    gamma = 1.33
    cp = cp_mix
    cv = cp / gamma
    h = cp * T_ad
    u = cv * T_ad

    burned_state = ThermoState(
        T=float(T_ad),
        p=float(p),
        rho=float(rho),
        cp=float(cp),
        cv=float(cv),
        gamma=float(gamma),
        R_mix=float(R_mix),
        h=float(h),
        u=float(u),
        mass_fractions={"mixture": 1.0},
    )

    # For this backend the species breakdown is not resolved; we just
    # expose a dummy single "mixture" species.
    return IdealEquilibriumResult(
        T_ad=T_ad,
        p=p,
        burned_state=burned_state,
        species_moles={"mixture": 1.0},
    )


def _cantera_hp_equilibrium(
    fuel_species: str,
    phi: float,
    p: float,
    T_intake: float,
    mechanism: str,
) -> IdealEquilibriumResult:
    """Use Cantera to compute HP-equilibrium adiabatic flame.

    Parameters
    ----------
    fuel_species:
        Name of the fuel species in the Cantera mechanism (e.g. 'CH4').
    phi:
        Equivalence ratio.
    p:
        Pressure [Pa].
    T_intake:
        Unburned gas temperature [K].
    mechanism:
        Cantera mechanism YAML file (e.g. 'gri30.yaml').
    """
    try:
        import cantera as ct
    except Exception as exc:  # pragma: no cover - runtime env issue
        raise RuntimeError(
            "Cantera is not available. Install cantera>=3 and ensure it is "
            "importable in this environment."
        ) from exc

    gas = ct.Solution(mechanism)
    gas.TP = T_intake, p
    # Explicit air composition to avoid 'air' parseCompString error
    gas.set_equivalence_ratio(phi, fuel_species, "O2:1.0, N2:3.76")

    # HP-equilibrium (constant enthalpy, pressure)
    gas.equilibrate("HP")
    state = ThermoState.from_cantera(gas)

    # For completeness, expose species mole numbers (up to a common factor).
    X = gas.X  # mole fractions
    species_moles: Dict[str, float] = {}
    for name, x in zip(gas.species_names, X):
        if x > 1e-12:
            species_moles[name] = float(x)

    return IdealEquilibriumResult(
        T_ad=state.T,
        p=state.p,
        burned_state=state,
        species_moles=species_moles,
    )


# ----------------------------------------------------------------------------
# Top-level API (backwards compatible + new backends)
# ----------------------------------------------------------------------------

def ideal_adiabatic_flame(
    fuel_name: str,
    phi: float,
    p: float,
    T_intake: float,
    afr_stoich: float,
    backend: BackendType = "legacy",
    mechanism: str | None = None,
    fuel_species: str | None = None,
) -> IdealEquilibriumResult:
    """Adiabatic flame at given φ, p, T with selectable backend.

    Parameters
    ----------
    fuel_name:
        For backend='legacy': Species key in SPECIES_DB (e.g. 'C8H18', 'CH3OH').
        For backend='ideal':  Fuel key in simulator.fuels.FUEL_DB
                              (e.g. 'gasoline', 'methanol', 'e85').
        For backend='cantera': label only (not used directly).
    phi:
        Equivalence ratio.
    p:
        Pressure [Pa].
    T_intake:
        Unburned-gas temperature [K].
    afr_stoich:
        Stoichiometric AFR by mass (used by backend='legacy'; for 'ideal'
        we pull the AFR from simulator.fuels and this can be a consistency
        check / unused).
    backend:
        'legacy'  -> original complete-combustion, no dissociation, species
                     breakdown using SPECIES_DB.
        'ideal'   -> simple LHV + cp energy balance using simulator.fuels.
        'cantera' -> Cantera HP equilibrium at (p, h, composition).
    mechanism:
        Cantera mechanism file (e.g. 'gri30.yaml'), required for
        backend='cantera' (defaults to 'gri30.yaml' if None).
    fuel_species:
        Fuel species name in the Cantera mechanism (e.g. 'CH4'),
        required for backend='cantera'.
    """
    if backend == "legacy":
        return _legacy_complete_combustion_equilibrium(
            fuel_name=fuel_name,
            phi=phi,
            p=p,
            T_intake=T_intake,
            afr_stoich=afr_stoich,
        )

    if backend == "ideal":
        # Here fuel_name is interpreted as a FUEL_DB key.
        return _ideal_cp_energy_balance(
            fuel_id=fuel_name,
            phi=phi,
            p=p,
            T_intake=T_intake,
        )

    if backend == "cantera":
        if mechanism is None:
            mechanism = "gri30.yaml"
        if fuel_species is None:
            raise ValueError(
                "backend='cantera' requires fuel_species (e.g. 'CH4') "
                "matching the species name in the chosen mechanism."
            )
        return _cantera_hp_equilibrium(
            fuel_species=fuel_species,
            phi=phi,
            p=p,
            T_intake=T_intake,
            mechanism=mechanism,
        )

    raise ValueError(f"Unknown backend={backend!r}. Use 'legacy', 'ideal' or 'cantera'.")
