import time
import pytest
from flyarena.store import Store
from flyarena.contracts import MatchRequest
from flyarena.services.queue_status import queue_status


def setup_queue(tmp_path):
    store = Store(tmp_path)
    fly = store.add_fly('u', {'name': 'WT', 'color': 'mint'}, {'artifact_id': 'a'*64})
    request = MatchRequest(fly_ids=[fly['id']], mode='forage').model_dump()
    training = store.add_match('u', request, 'r')['id']
    interactive = store.add_match('u', request, 'r')['id']
    with store.db() as db:
        db.execute('INSERT INTO training_evaluations VALUES(?,0,0,0,?)', ('run', training))
    return store, training, interactive


def test_claim_and_visible_queue_prioritize_interactive(tmp_path):
    store, training, interactive = setup_queue(tmp_path)
    queue = queue_status(store)
    assert queue[interactive]['position'] == 1
    assert queue[training]['position'] == 2
    assert queue[training]['estimated_wait_seconds'] is None
    assert store.claim()[0] == interactive
    assert queue_status(store)[interactive]['position'] == 0
    assert store.claim() is None


def test_old_training_cannot_starve(tmp_path):
    store, training, interactive = setup_queue(tmp_path)
    with store.db() as db:
        db.execute('UPDATE matches SET created=? WHERE id=?', (time.time()-601, training))
    assert queue_status(store)[training]['position'] == 1
    assert store.claim()[0] == training


def test_estimate_uses_history_and_running_progress(tmp_path):
    store, training, interactive = setup_queue(tmp_path)
    ident, lease, _ = store.claim()
    store.finish(ident, lease, {'status': 'verified'})
    with store.db() as db:
        db.execute('UPDATE matches SET updated=created+100 WHERE id=?', (ident,))
    ident, lease, _ = store.claim()
    store.heartbeat(ident, lease, .4)
    queue = queue_status(store)[training]
    assert queue['estimated_remaining_seconds'] == 60
    assert queue['estimate_samples'] == 1


def test_blank_control_rejects_competition():
    with pytest.raises(ValueError, match='single-fly'):
        MatchRequest(map_id='blank', fly_ids=['a'*32, 'b'*32])
    assert MatchRequest(map_id='blank', mode='forage', fly_ids=['a'*32]).map_id == 'blank'
