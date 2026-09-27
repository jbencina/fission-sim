"""Smoke tests for the CoolProp wrapper module.

These confirm CoolProp returns sane numbers at primary-loop and
pressurizer conditions. They are NOT exhaustive thermodynamic tests —
the wrapper is a thin pass-through and CoolProp itself is well-tested
upstream. We verify the wrapper API and unit conventions.
"""

import CoolProp.CoolProp as CP
import pytest

from fission_sim.physics import coolprop
from fission_sim.physics.domain import ModelDomainError


@pytest.mark.parametrize(
    ("output", "name1", "value1", "name2", "value2", "fluid"),
    [
        ("T", "P", 1.55e7, "Q", 0.0, coolprop._FLUID_FAST),
        ("D", "P", 1.55e7, "T", 583.0, coolprop._FLUID_DOME),
    ],
    ids=["IF97-saturation", "HEOS-subcooled-density"],
)
def test_cached_property_lookup_matches_direct_coolprop(output, name1, value1, name2, value2, fluid):
    """The cache returns CoolProp's exact float, not a rounded or recomputed value."""
    coolprop.clear_cache()
    direct = CP.PropsSI(output, name1, value1, name2, value2, fluid)
    cached = coolprop._props(output, name1, value1, name2, value2, fluid)
    assert cached == direct


def test_failing_state_lookup_is_not_cached():
    """Repeated domain failures still call CoolProp and raise ModelDomainError."""
    coolprop.clear_cache()
    P = 1.55e7
    T_on_line = CP.PropsSI("T", "P", P, "Q", 0.0, coolprop._FLUID_DOME)

    for _ in range(2):
        with pytest.raises(ModelDomainError):
            coolprop.density_PT(P=P, T=T_on_line)

    info = coolprop.cache_info()
    assert info.misses == 2
    assert info.currsize == 0


def test_cache_hits_increase_on_repeated_lookup():
    """A second identical property request is served from the LRU cache."""
    coolprop.clear_cache()
    first = coolprop.T_sat(P=1.55e7)
    after_first = coolprop.cache_info()
    second = coolprop.T_sat(P=1.55e7)
    after_second = coolprop.cache_info()

    assert second == first
    assert after_first.misses == 1
    assert after_first.hits == 0
    assert after_second.hits == after_first.hits + 1


def test_subcooled_density_at_primary_conditions():
    """Subcooled water at 583 K, 15.5 MPa is ~715 kg/m³."""
    rho = coolprop.density_PT(P=1.55e7, T=583.0)
    assert 700.0 < rho < 730.0


def test_subcooled_enthalpy_at_primary_conditions():
    """Specific enthalpy of subcooled water at primary conditions
    is in the 1.3–1.5 MJ/kg range."""
    h = coolprop.enthalpy_PT(P=1.55e7, T=583.0)
    assert 1.3e6 < h < 1.5e6


def test_saturation_temperature_at_design_pressure():
    """T_sat at 15.5 MPa is ~618 K (345 °C)."""
    T_sat = coolprop.T_sat(P=1.55e7)
    assert 615.0 < T_sat < 622.0


def test_saturated_liquid_density_at_design_pressure():
    """Saturated liquid density at 15.5 MPa is ~595 kg/m³."""
    rho_l = coolprop.sat_liquid_density(P=1.55e7)
    assert 580.0 < rho_l < 610.0


def test_saturated_vapor_density_at_design_pressure():
    """Saturated vapor density at 15.5 MPa is ~102 kg/m³."""
    rho_v = coolprop.sat_vapor_density(P=1.55e7)
    assert 95.0 < rho_v < 110.0


def test_saturated_liquid_internal_energy_at_design_pressure():
    """u_l at 15.5 MPa is ~1.58 MJ/kg."""
    u_l = coolprop.sat_liquid_internal_energy(P=1.55e7)
    assert 1.5e6 < u_l < 1.65e6


def test_saturated_vapor_internal_energy_at_design_pressure():
    """u_v at 15.5 MPa is ~2.46 MJ/kg."""
    u_v = coolprop.sat_vapor_internal_energy(P=1.55e7)
    assert 2.4e6 < u_v < 2.55e6


def test_isobaric_expansion_coefficient_at_design():
    """β_T at primary design conditions is ~3.3e-3 /K (3.26e-3 with CoolProp 7.2.0)."""
    beta = coolprop.beta_T(P=1.55e7, T=583.0)
    assert 3.0e-3 < beta < 3.5e-3


def test_saturation_state_from_DU_round_trip():
    """Build a saturated mixture's (M, U) from (P, level, V),
    invert back via the (D, U) closure, recover same P."""
    P_in = 1.55e7
    level = 0.5
    V = 51.0
    rho_l = coolprop.sat_liquid_density(P=P_in)
    rho_v = coolprop.sat_vapor_density(P=P_in)
    u_l = coolprop.sat_liquid_internal_energy(P=P_in)
    u_v = coolprop.sat_vapor_internal_energy(P=P_in)
    M_l = level * V * rho_l
    M_v = (1 - level) * V * rho_v
    M = M_l + M_v
    U = M_l * u_l + M_v * u_v
    P_out = coolprop.P_from_DU(D=M / V, U=U / M)
    assert P_out == pytest.approx(P_in, rel=1e-3)


def test_property_failure_is_reported_as_model_domain_error():
    """A (P, T) pair exactly on the saturation line cannot be evaluated.

    Inside the solver that failure ends the step, so the wrapper reports it
    as a ModelDomainError (still a ValueError) that the runtime can explain,
    keeping CoolProp's own error as the cause.
    """
    P = 1.55e7
    T_on_line = CP.PropsSI("T", "P", P, "Q", 0.0, coolprop._FLUID_DOME)
    with pytest.raises(ModelDomainError) as exc_info:
        coolprop.density_PT(P=P, T=T_on_line)
    assert exc_info.value.limit == "property_lookup"
    assert isinstance(exc_info.value.__cause__, ValueError)


def test_malformed_property_call_stays_a_plain_value_error():
    """A misspelled property name is a coding mistake, not a physics limit."""
    with pytest.raises(ValueError, match="parsing failed") as exc_info:
        coolprop._props("Dx", "P", 1.55e7, "T", 583.0, coolprop._FLUID_DOME)
    assert not isinstance(exc_info.value, ModelDomainError)
