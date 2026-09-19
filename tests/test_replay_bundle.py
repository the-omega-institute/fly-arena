"""A portable replay keeps the actual contestant designs without account data."""
import json
from pathlib import Path
import runpy
import sys

import pytest

from flyarena.common import digest, file_sha, write_json
from flyarena.store import Store

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'bundle_replay.py'


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    store = Store(tmp_path / 'source')
    ident, fly_id, artifact_id = 'a' * 32, 'b' * 32, 'c' * 64
    spec = {'weight_mutations': [{'selector': 'olfactory', 'scale': 1.1}], 'parent_id': 'd' * 32}
    report = {'artifact_id': artifact_id, 'budget_used': 12, 'budget_limit': 100}
    request = {'fly_ids': [fly_id], 'map_id': 'orchard', 'mode': 'forage', 'duration_seconds': 30}
    folder = store.root / 'runs' / ident / '2'
    folder.mkdir(parents=True)
    for name, value in {'scene': {'flies': [{'id': fly_id}]}, 'frames': [{'time': 30}], 'events': []}.items():
        write_json(folder / f'{name}.json', value)
    receipt = {'request': request, 'flies': [{'id': fly_id, 'name': 'Nectar', 'color': 'mint', 'artifact_id': artifact_id}],
               'files': {name: file_sha(folder / name) for name in ('scene.json', 'frames.json', 'events.json')}}
    receipt['sha256'] = digest(receipt)
    write_json(folder / 'receipt.json', receipt)
    with store.db() as db:
        db.execute('INSERT INTO flies VALUES(?,?,?,?,?,?,?,?)',
                   (fly_id, 'private-owner', 'Nectar', 'mint', json.dumps(spec), artifact_id, json.dumps(report), 1))
        db.execute('INSERT INTO matches(id,owner,request,artifacts,runtime_hash,status,attempt,result,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?)',
                   (ident, 'private-owner', json.dumps(request), json.dumps([artifact_id]), 'runtime', 'verified', 2,
                    json.dumps({'receipt_sha256': receipt['sha256']}), 1, 2))
    output = tmp_path / 'output'
    monkeypatch.setattr(sys, 'argv', [str(SCRIPT), '--match-id', ident, '--db', str(store.path),
                                    '--runs', str(store.root / 'runs'), '--output', str(output)])
    return store, folder, output, ident, fly_id, receipt


def export():
    runpy.run_path(str(SCRIPT), run_name='__main__')


def test_replay_bundle_retains_design_and_original_artifacts_without_accounts(bundle):
    _, source, output, ident, _, receipt = bundle
    export()
    match = json.loads((output / f'{ident}-match.json').read_text())
    assert match['participants'][0]['spec']['weight_mutations'][0]['scale'] == 1.1
    assert match['participants'][0]['report'] == {'budget_used': 12, 'budget_limit': 100}
    assert 'private-owner' not in json.dumps(match)
    assert match['source']['receipt_sha256'] == receipt['sha256']
    for name in ('scene', 'frames', 'events', 'receipt'):
        assert (output / f'{ident}-{name}.json').read_bytes() == (source / f'{name}.json').read_bytes()
    assert len(list(output.iterdir())) == 5


def test_bundle_rejects_design_from_different_artifact(bundle):
    store, _, output, _, fly_id, _ = bundle
    with store.db() as db:
        db.execute('UPDATE flies SET artifact_id=? WHERE id=?', ('e' * 64, fly_id))
    with pytest.raises(SystemExit, match='differs from the replay'):
        export()
    assert not output.exists()


def test_bundle_requires_every_browser_file_in_receipt(bundle):
    _, folder, output, _, _, receipt = bundle
    del receipt['files']['frames.json']
    write_json(folder / 'receipt.json', receipt)
    with pytest.raises(SystemExit, match='Receipt does not match this attempt'):
        export()
    assert not output.exists()


def test_bundle_rejects_receipt_from_another_match(bundle):
    _, folder, output, _, _, receipt = bundle
    receipt['request']['map_id'] = 'scarcity'
    receipt['sha256'] = digest({k: v for k, v in receipt.items() if k != 'sha256'})
    write_json(folder / 'receipt.json', receipt)
    with pytest.raises(SystemExit, match='Receipt does not match the verified match result'):
        export()
    assert not output.exists()
