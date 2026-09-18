from types import SimpleNamespace

import numpy as np
import pytest

from flyarena.backend import CPUBrainBackend
from flyarena.experiments.embodied_sensor import PROFILE, apply, sensory_groups
from flyarena.neural import Brain
from flyarena.rate import RateBrain


def graph():
    groups = {
        "olfactory": np.array([0, 1]), "olfactory_left": np.array([0]),
        "olfactory_right": np.array([1]), "visual": np.array([2, 3, 4, 5]),
        "mechanosensory_tactile": np.array([6, 7]),
    }
    return SimpleNamespace(n=8, ids=np.arange(100, 108), side=np.array([1, -1, 1, -1, 1, -1, 1, -1]),
                           groups=groups)


def test_profile_is_versioned_and_channels_are_canonical():
    g = graph()
    external = np.zeros(g.n)
    result = apply(external, g, odor_left=.2, odor_right=.4, visual_left=.7,
                   visual_right=.1, touch=.5)
    assert PROFILE["id"] == "engineered-multimodal-v1"
    assert result["profile"] == PROFILE["id"]
    assert result["group_counts"] == {
        "odor_left": 1, "odor_right": 1, "visual_left": 2,
        "visual_right": 2, "touch": 2,
    }
    np.testing.assert_array_equal(external[[0, 1]], [16, 24])
    np.testing.assert_allclose(external[[2, 4]], [8.4, 8.4])
    np.testing.assert_allclose(external[[3, 5]], [1.2, 1.2])
    np.testing.assert_allclose(external[[6, 7]], [9, 9])


def test_zero_visual_touch_is_exact_odor_only_for_all_backends():
    g = graph()
    g.pre = np.arange(8, dtype=np.int32)
    g.post = np.roll(g.pre, -1)
    g.indptr = np.arange(9, dtype=np.int64)
    g.baseline_weights = lambda: np.zeros(8, dtype=np.float32)
    lif = Brain(g)
    lif.stimulate(.3, .6)
    expected_lif = lif.external.copy()
    lif.reset()
    lif.stimulate_multimodal(.3, .6, 0, 0, 0)
    np.testing.assert_array_equal(lif.external, expected_lif)

    rate = RateBrain(g)
    rate.stimulate(.3, .6)
    expected_rate = rate.external.copy()
    rate.reset()
    rate.stimulate_multimodal(.3, .6, 0, 0, 0)
    np.testing.assert_array_equal(rate.external, expected_rate)

    backend = CPUBrainBackend(Brain(g))
    backend.stimulate(.3, .6)
    expected_backend = backend.brain.external.copy()
    backend.brain.reset()
    backend.stimulate_multimodal(.3, .6, 0, 0, 0)
    np.testing.assert_array_equal(backend.brain.external, expected_backend)


def test_missing_tactile_annotation_fails_closed_for_nonzero_touch():
    g = graph()
    del g.groups["mechanosensory_tactile"]
    with pytest.raises(ValueError, match="annotated mechanosensory"):
        apply(np.zeros(g.n), g, odor_left=0, odor_right=0, touch=.1)


def test_full_connectome_derives_tactile_group_from_official_metadata():
    from flyarena.common import DATA
    from flyarena.connectome import Connectome

    g = Connectome(DATA)
    groups = sensory_groups(g)
    assert len(groups["visual_left"]) > 0 and len(groups["visual_right"]) > 0
    assert len(groups["touch"]) == 2558
    assert set(groups["touch"]).isdisjoint(set(groups["visual_left"]))
