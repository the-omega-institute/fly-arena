"""Adversarial admission checks using evidence from a real completed run."""
import json
from pathlib import Path
import shutil
import pytest
from flyarena.common import digest, file_sha, write_json
from flyarena.judge import verify
from flyarena.store import Store


@pytest.fixture
def evidence(tmp_path):
    store=Store()
    matches=[m for m in store.matches() if m['status']=='verified' and m['request']['mode']=='contest']
    if not matches: pytest.skip('Requires a real completed contest')
    source=store.result_folder(matches[0]); target=tmp_path/'run'
    shutil.copytree(source,target)
    return target


def resign(folder, name):
    r=json.loads((folder/'receipt.json').read_text())
    if name: r['files'][name]=file_sha(folder/name)
    r['sha256']=digest({k:v for k,v in r.items() if k!='sha256'})
    write_json(folder/'receipt.json',r)


def test_valid_receipt_and_tampered_bytes(evidence):
    assert verify(evidence)['status']=='verified'
    (evidence/'frames.json').write_text('[]')
    with pytest.raises(ValueError,match='hash mismatch'): verify(evidence)


def test_missing_frames_even_when_resigned(evidence):
    frames=json.loads((evidence/'frames.json').read_text());del frames[1]
    write_json(evidence/'frames.json',frames);resign(evidence,'frames.json')
    with pytest.raises(ValueError,match='missing ticks'): verify(evidence)


def test_reject_truncated_match_even_when_resigned(evidence):
    r=json.loads((evidence/'receipt.json').read_text());r['request']['duration_seconds']+=1
    write_json(evidence/'receipt.json',r);resign(evidence,None)
    with pytest.raises(ValueError,match='required endpoint'): verify(evidence)


def test_wrong_admitted_artifact(evidence):
    with pytest.raises(ValueError,match='contestant artifacts'): verify(evidence,expected_artifacts=['b'*64,'b'*64])
