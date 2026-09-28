import numpy as np

from fission_sim.control.feedwater_controller import FeedwaterController, FeedwaterControllerParams


def test_feedwater_matches_total_steam_out():
    c = FeedwaterController(FeedwaterControllerParams())
    assert c.state_size == 0 and c.outputs_require_inputs is True
    out = c.outputs(np.empty(0), inputs={"m_steam": 1500.0, "m_dump": 169.0})
    assert out["m_fw"] == 1669.0


def test_telemetry_without_inputs_is_none():
    c = FeedwaterController(FeedwaterControllerParams())
    assert c.telemetry(np.empty(0)) == {"m_fw": None, "m_steam": None, "m_dump": None}
