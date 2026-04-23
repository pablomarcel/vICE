"""Thermochemistry support package for the engine simulator.

This subpackage is intentionally small and self-contained. It does **not**
try to be a full replacement for Cantera or NASA CEA. Instead it provides:

* Basic species and mixture property calculations (cp, R, gamma, h, u).
* A `ThermoState` container that the engine core can use instead of
  passing around bare (p, T, Y) tuples.
* Skeletons for equilibrium and finite-rate chemistry models that can be
  filled in incrementally.

Design goals
------------
* Pure-Python + NumPy only. No compiled extensions or external chemistry
  libraries are required.
* All heavy-duty numerics are isolated behind small, testable functions
  so that you can later swap in more advanced solvers (or a Cantera
  wrapper) without touching the engine cycle code.
* Data driven: species properties live in a small in-code database which
  you can extend or replace from JSON generated from NASA / JANAF tables.

IMPORTANT
---------
The default species database ships with **placeholder** NASA-style
polynomials with constant-cp behaviour. They are numerically reasonable
for a first cut, but they are **not** authoritative NASA coefficients.
To run serious studies you should replace them with real data extracted
from NASA CEA / JANAF.

See :mod:`simulator.thermo.species` for details.
"""

from .thermo_state import ThermoState
from .species import Species, NasaPoly7, SPECIES_DB, register_species
from . import equilibrium
from . import reactor0d

__all__ = [
    "ThermoState",
    "Species",
    "NasaPoly7",
    "SPECIES_DB",
    "register_species",
    "equilibrium",
    "reactor0d",
]
