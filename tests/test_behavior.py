"""Behavioral selection from measured posture and event timing, independent of scores."""
import math
import pytest


from flyarena.behavior import behavior_metrics, selection_score, SUSTAINED_FORAGING
from test_replay import receipt_factory, change


def observations():
    # A fixed mesh rotation must not look like the animal is inverted.
    q0 = [math.cos(.6), math.sin(.6), 0, 0]
    flipped = [-q0[1], q0[0], 0, 0]
    scene = {'body': {'geoms': [{'slot': 0, 'name': 'fly-0/c_thorax'}]}}
    frames = [{'time': t, 'poses': [[0, 0, 0, *q]]}
              for t, q in [(0, q0), (1, flipped), (3, q0), (4, q0)]]
    events = [{'type': 'intake', 'slot': 0, 'tick': tick, 'amount': amount}
              for tick, amount in [(10, 2), (20, 3), (30, 4)]]
    return scene, frames, events


def test_time_weighted_posture_recovery_mesh_rotation_and_event_midpoint():
    scene, frames, events = observations()
    metric = behavior_metrics(scene, frames, events, 1, .1)[0]
    assert metric == dict(schema=SUSTAINED_FORAGING, food=9, latter_half_food=4,
                         upright_fraction=.5, recorded_seconds=4,
                         first_inversion_s=1, fitness=6.5)
    # q and -q represent the same rotation; scaling recorded quaternions is harmless.
    for f in frames:
        f['poses'][0][3:] = [-2*x for x in f['poses'][0][3:]]
    assert behavior_metrics(scene, frames, events, 1, .1)[0] == metric
    assert behavior_metrics(scene, frames, [], 1, .1)[0]['fitness'] == 0


def test_missing_posture_stays_unavailable_and_default_food_is_unchanged():
    scene, frames, events = observations()
    frames[2]['poses'] = []
    assert behavior_metrics(scene, frames, events, 1, .1) == [None]
    assert behavior_metrics({}, frames, events, 2, .1) == [None, None]
    assert selection_score({'scores': [9]}, 0, 'food') == 9
    assert selection_score({'scores': [9]}, 0, SUSTAINED_FORAGING) is None


def test_judge_exposes_behavior_without_changing_match_winner(receipt_factory):
    from flyarena.judge import verify
    folder = receipt_factory()
    before = verify(folder)
    assert before['behavior'] == [None]  # Fixture has no named thorax.
    change(folder, 'scene.json', lambda s:s['body']['geoms'][0].update(name='fly-0/c_thorax'))
    after = verify(folder)
    assert after['winner_slot'] == before['winner_slot']
    assert after['scores'] == before['scores']
    assert after['behavior'][0]['fitness'] == 0
    assert after['behavior'][0]['upright_fraction'] == pytest.approx(1)
