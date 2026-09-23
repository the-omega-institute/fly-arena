"""Pin training admission, independent of prepared connectome assets or simulation."""
from typing import get_args

import pytest
from pydantic import ValidationError

from flyarena.contracts import MatchRequest
from flyarena.services.training import EvaluationCondition, TrainingSpec


TRAINING_MAPS = ('orchard', 'maze', 'scarcity', 'ring', 'terrarium', 'enclosure',
                'canopy', 'switchback', 'blank')
BRIDGES = ('legacy-v1', 'sensorimotor-research-v2')


def test_training_map_contract_is_pinned_for_primary_and_extra_conditions():
    assert get_args(TrainingSpec.model_fields['map_id'].annotation) == TRAINING_MAPS
    assert get_args(EvaluationCondition.model_fields['map_id'].annotation) == TRAINING_MAPS
    assert get_args(TrainingSpec.model_fields['bridge_profile'].annotation) == BRIDGES
    assert set(TRAINING_MAPS) <= set(get_args(MatchRequest.model_fields['map_id'].annotation))


@pytest.mark.parametrize('bridge', BRIDGES)
@pytest.mark.parametrize('map_id', TRAINING_MAPS)
@pytest.mark.parametrize('mode', ['forage', 'contest'])
@pytest.mark.parametrize('explicit_conditions', [False, True])
def test_training_map_admission_matches_queued_match_contract(bridge, map_id, mode, explicit_conditions):
    values = dict(founder_id='a'*32, opponent_id='b'*32, bridge_profile=bridge,
                  map_id=map_id, mode=mode, population=2, generations=1, max_evaluations=8)
    if explicit_conditions:
        values.update(map_id='orchard', evaluation_conditions=[
            {'map_id': 'orchard', 'seed': 42}, {'map_id': map_id, 'seed': 43}])
    if map_id == 'blank' and mode == 'contest':
        with pytest.raises(ValidationError, match='single-fly observation'):
            TrainingSpec(**values)
        return
    plan = TrainingSpec(**values)
    assert plan.conditions[-1].map_id == map_id
    for condition in plan.conditions:
        match = MatchRequest(fly_ids=['a'*32] if mode == 'forage' else ['a'*32, 'b'*32],
                             map_id=condition.map_id, seed=condition.seed, mode=mode,
                             bridge_profile=bridge, sensory_profile=plan.sensory_profile)
        assert match.map_id == condition.map_id
        assert match.bridge_profile == bridge


@pytest.mark.parametrize('map_id', ['labyrinth', 'duel', 'unknown'])
def test_nontraining_maps_are_rejected_in_primary_and_extra_conditions(map_id):
    with pytest.raises(ValidationError):
        TrainingSpec(founder_id='a'*32, map_id=map_id)
    with pytest.raises(ValidationError):
        TrainingSpec(founder_id='a'*32, evaluation_conditions=[{'map_id': map_id, 'seed': 42}])
