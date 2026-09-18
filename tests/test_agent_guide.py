"""An agent can discover its instructions without an account or a simulation."""
import json
import re

from fastapi.testclient import TestClient

from flyarena.api import create_app
from flyarena.auth import AuthConfig
from flyarena.services.training import TrainingSpec, ProposedCandidate
from flyarena.store import Store


def test_public_agent_guide_is_packaged_and_examples_match_api(tmp_path):
    with TestClient(create_app(with_worker=False, store=Store(tmp_path), auth_config=AuthConfig())) as client:
        response = client.get('/api/v1/agent-guide')
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/markdown')
        examples = re.findall(r'```json\n(.*?)\n```', response.text, re.S)
        parsed = [json.loads(example) for example in examples]
        training = next(example for example in parsed if example.get('strategy') == 'external')
        training['founder_id'] = 'a' * 32
        assert TrainingSpec.model_validate(training).evaluations == 4
        candidate = next(example for example in parsed if 'generation' in example)
        candidate['spec']['parent_id'] = 'a' * 32
        candidate['spec']['connectome_sha256'] = 'b' * 64
        proposal = ProposedCandidate.model_validate(candidate)
        assert (proposal.generation, proposal.slot) == (0, 1)
        assert client.get('/api/v1/matches').json() == []
        assert '/api/v1/agent-guide' in client.get('/openapi.json').json()['paths']
