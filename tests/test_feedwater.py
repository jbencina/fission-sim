import numpy as np
import pytest

from fission_sim.physics.feedwater import FeedwaterParams, FeedwaterSystem
from fission_sim.physics.sg_secondary import SGSecondaryParams


def test_layout_and_design_state():
    fw = FeedwaterSystem(FeedwaterParams())
    sg = SGSecondaryParams()
    assert fw.state_size == 1
    assert fw.state_labels == ("m_fw",)
    assert fw.input_ports == ("m_fw_demand",)
    assert fw.output_ports == ("m_fw",)
    assert fw.outputs_require_inputs is False
    assert fw.initial_state()[0] == pytest.approx(sg.m_steam_design)
    assert fw.params.m_fw_max == pytest.approx(1.2 * sg.m_steam_design)
    assert fw.params.m_fw_initial == pytest.approx(sg.m_steam_design)


def test_first_order_response_to_demand():
    fw = FeedwaterSystem(FeedwaterParams())
    d = fw.derivatives(np.array([1000.0]), {"m_fw_demand": 1500.0})
    assert d[0] == pytest.approx(500.0 / 5.0)


def test_demand_is_clipped_to_actuator_range():
    fw = FeedwaterSystem(FeedwaterParams())
    p = fw.params
    d = fw.derivatives(np.array([p.m_fw_max]), {"m_fw_demand": 10.0 * p.m_fw_max})
    assert d[0] == pytest.approx(0.0)
    d = fw.derivatives(np.array([0.0]), {"m_fw_demand": -500.0})
    assert d[0] == pytest.approx(0.0)


def test_nonfinite_demand_is_rejected():
    fw = FeedwaterSystem(FeedwaterParams())
    with pytest.raises(ValueError, match="m_fw_demand must be finite"):
        fw.derivatives(fw.initial_state(), {"m_fw_demand": np.nan})


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"tau_fw": 0.0}, "tau_fw must be finite and > 0"),
        ({"tau_fw": -1.0}, "tau_fw must be finite and > 0"),
        ({"tau_fw": np.inf}, "tau_fw must be finite and > 0"),
        ({"m_fw_max_frac": 0.0}, "m_fw_max_frac must be finite and > 0"),
        ({"m_fw_max_frac": np.nan}, "m_fw_max_frac must be finite and > 0"),
        ({"m_fw_max": -1.0}, "m_fw_max must be finite and > 0"),
        ({"m_fw_initial": -1.0}, "m_fw_initial must be finite and within"),
        ({"m_fw_max_frac": 0.5}, "m_fw_initial must be finite and within"),
    ],
)
def test_invalid_params_raise_learner_readable_value_error(kwargs, message):
    with pytest.raises(ValueError, match=message):
        FeedwaterParams(**kwargs)


def test_output_is_state():
    fw = FeedwaterSystem(FeedwaterParams())
    assert fw.outputs(np.array([1234.0]))["m_fw"] == 1234.0
    tele = fw.telemetry(np.array([1234.0]))
    assert tele["m_fw"] == 1234.0
    assert tele["m_fw_demand"] is None
    assert tele["m_fw_max"] == pytest.approx(fw.params.m_fw_max)


def test_telemetry_reports_finite_demand_when_inputs_are_available():
    fw = FeedwaterSystem(FeedwaterParams())
    tele = fw.telemetry(np.array([1234.0]), {"m_fw_demand": 1400.0})
    assert tele["m_fw_demand"] == pytest.approx(1400.0)
