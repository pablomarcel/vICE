from __future__ import annotations
from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class FuelProperties:
    """Basic fuel properties for simple heat-release scaling.

    This is *not* a full chemical-equilibrium model, just enough to:
    - define a stoichiometric AFR reference, and
    - scale heat release by LHV across fuels.
    """

    id: str
    name: str
    afr_stoich: float       # stoichiometric AFR by mass
    LHV_J_per_kg: float     # lower heating value
    rho_kg_per_m3: float    # liquid (or reference) density


FUEL_DB: Dict[str, FuelProperties] = {
    "gasoline": FuelProperties(
        id="gasoline",
        name="Gasoline (reference)",
        afr_stoich=14.7,
        LHV_J_per_kg=44e6,
        rho_kg_per_m3=740.0,
    ),
    "methanol": FuelProperties(
        id="methanol",
        name="Methanol",
        afr_stoich=6.4,
        LHV_J_per_kg=19.9e6,
        rho_kg_per_m3=790.0,
    ),
    "e85": FuelProperties(
        id="e85",
        name="E85 (85% ethanol, 15% gasoline)",
        afr_stoich=9.8,
        LHV_J_per_kg=30e6,
        rho_kg_per_m3=780.0,
    ),
    # Optional extras for thermochemistry work
    "ethanol": FuelProperties(
        id="ethanol",
        name="Ethanol",
        afr_stoich=9.0,
        LHV_J_per_kg=26.8e6,
        rho_kg_per_m3=790.0,
    ),
    "methane": FuelProperties(
        id="methane",
        name="Methane (CH4)",
        afr_stoich=17.2,
        LHV_J_per_kg=50e6,
        rho_kg_per_m3=0.656,  # approx gas density at STP
    ),
}


def get_fuel(fuel_id: str) -> FuelProperties:
    try:
        return FUEL_DB[fuel_id]
    except KeyError as exc:  # pragma: no cover - defensive
        available = ", ".join(sorted(FUEL_DB.keys()))
        raise KeyError(
            f"Unknown fuel_id {fuel_id!r}. Available: {available}"
        ) from exc
