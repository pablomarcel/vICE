from __future__ import annotations

"""Hydraulic and shaft-power helpers for pump analysis.

The pump solver may keep the curve-native flow unit in the output because
textbooks and suppliers often publish curves in different abscissa units
(gpm, L/min, m3/h, or thousands of gal/min). Power calculations, however,
must convert the operating flow to the unit expected by the formula.
"""


_FLOW_TO_GPM: dict[str, float] = {
    # US customary
    "gpm": 1.0,
    "gal_per_min": 1.0,
    "gallon_per_minute": 1.0,
    "gallons_per_minute": 1.0,
    "us_gpm": 1.0,
    # Frank White / large pump charts frequently use 10^3 gal/min.
    "1000_gal_per_min": 1000.0,
    "1000_gpm": 1000.0,
    "kgal_per_min": 1000.0,
    "kgpm": 1000.0,
    "thousand_gal_per_min": 1000.0,
    "thousand_gpm": 1000.0,
    # Common SI-ish supplier units converted to US gpm for WHP.
    "lpm": 0.2641720524,
    "liter_per_min": 0.2641720524,
    "liters_per_minute": 0.2641720524,
    "m3_per_h": 4.4028675393,
    "m^3_per_h": 4.4028675393,
    "m3/h": 4.4028675393,
}


def flow_to_gpm(flow: float, flow_unit: str) -> float:
    """Convert a flow value from a supported unit to US gal/min.

    Parameters
    ----------
    flow:
        Flow value in the native pump-curve unit.
    flow_unit:
        Unit string from the pump JSON, for example ``"gpm"`` or
        ``"1000_gal_per_min"``.

    Returns
    -------
    float
        Flow in US gal/min.

    Raises
    ------
    ValueError
        If the unit is unknown. This is intentional: silently treating a
        large-pump chart value of ``15.2`` as ``15.2 gpm`` is a thousand-fold
        error.
    """
    key = str(flow_unit).strip().lower().replace(" ", "_")
    try:
        multiplier = _FLOW_TO_GPM[key]
    except KeyError as exc:
        supported = ", ".join(sorted(_FLOW_TO_GPM))
        raise ValueError(
            f"Unsupported flow unit for horsepower calculation: {flow_unit!r}. "
            f"Supported units: {supported}"
        ) from exc
    return float(flow) * multiplier


def water_horsepower_gpm_ft(flow_gpm: float, head_ft: float, specific_gravity: float = 1.0) -> float:
    """Return hydraulic horsepower for US customary pump data.

    Formula:
        WHP = Q_gpm * H_ft * SG / 3960
    """
    return float(flow_gpm) * float(head_ft) * float(specific_gravity) / 3960.0


def water_horsepower_from_curve_flow(
    flow: float,
    flow_unit: str,
    head_ft: float,
    specific_gravity: float = 1.0,
) -> float:
    """Return water horsepower using a pump curve's native flow unit."""
    return water_horsepower_gpm_ft(
        flow_to_gpm(flow, flow_unit),
        head_ft,
        specific_gravity=specific_gravity,
    )


def brake_horsepower_from_efficiency(water_hp: float, efficiency: float | None) -> float | None:
    if efficiency is None or efficiency <= 0.0:
        return None
    return float(water_hp) / float(efficiency)


def hp_to_kw(hp: float | None) -> float | None:
    if hp is None:
        return None
    return float(hp) * 0.745699872
