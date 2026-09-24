"""Recoverable, schedule-bound competition evidence; never a global ranking."""
from itertools import combinations
from math import isfinite
import json
import uuid

from ..common import canonical

from .ranking import POLICY_ID, tournament_projection

PROTOCOL_ID = 'paired-series/v1'
DEFAULTS = {'bridge_profile': 'legacy-v1', 'sensory_profile': 'odor-only-v1',
            'sandbox': False, 'season_id': 'genesis-alpha'}
CONDITIONS = ('map_id', 'mode', 'duration_seconds', *DEFAULTS)


def expected_schedule(spec):
    """Use the admitted spec, never the surviving matches, to enumerate legs."""
    base = {key: spec.get(key, default) for key, default in DEFAULTS.items() if key != 'season_id'}
    base.update({key: spec[key] for key in ('map_id', 'mode', 'duration_seconds')})
    return [dict(base, seed=seed, fly_ids=slots)
            for seed in spec['seeds'] for a, b in combinations(spec['fly_ids'], 2)
            for slots in ([a, b], [b, a])]


def competition_protocol(tournament, matches):
    return schedule_report(tournament, matches, expected_schedule(tournament['spec']))


def schedule_report(tournament, matches, schedule, *, scored=True, membership='tournament', frozen=None):
    """Shared evidence checks for a complete, independently enumerated schedule."""
    spec = tournament['spec']
    buckets = {}
    for match in matches:
        request = match['request']
        key = (request.get('seed'), tuple(request.get('fly_ids', [])))
        buckets.setdefault(key, []).append(match)
    issues, rows = [], []
    runtimes = {m.get('runtime_hash') for m in matches}
    artifacts = {}
    for match in matches:
        for fly, artifact in zip(match['request'].get('fly_ids', []), match.get('artifacts') or []):
            artifacts.setdefault(fly, set()).add(artifact)
    shared_errors = []
    if frozen:
        if any(m.get('runtime_hash') != frozen['runtime_hash'] for m in matches):
            shared_errors.append('runtime_mismatch')
        if any(m.get('artifacts') != [frozen['artifacts'].get(f) for f in m['request'].get('fly_ids', [])] for m in matches):
            shared_errors.append('artifact_mismatch')
    if len(runtimes) != 1 or None in runtimes or '' in runtimes:
        shared_errors.append('runtime_mismatch')
    if any(len(values) != 1 for values in artifacts.values()):
        shared_errors.append('artifact_mismatch')
    if not spec.get('sandbox', False) and spec.get('sensory_profile', 'odor-only-v1') != 'odor-only-v1':
        shared_errors.append('unqualified_sensory')
    for ordinal, expected in enumerate(schedule):
        candidates = buckets.pop((expected['seed'], tuple(expected['fly_ids'])), [])
        reasons = list(shared_errors) if candidates else ['missing_match']
        if len(candidates) > 1:
            reasons.append('duplicate_match')
        match = candidates[0] if len(candidates) == 1 else None
        outcomes = None
        if match:
            request = match['request']
            if any(request.get(key, DEFAULTS.get(key)) != spec.get(key, DEFAULTS.get(key)) for key in CONDITIONS):
                reasons.append('condition_mismatch')
            if match.get(membership) != tournament['id'] or match.get('owner') != tournament['owner']:
                reasons.append('membership_mismatch')
            if frozen and match['id'] != frozen['match_ids'][ordinal]:
                reasons.append('membership_mismatch')
            if len(match.get('artifacts') or []) != len(expected['fly_ids']) or not all(match.get('artifacts') or []):
                reasons.append('artifact_mismatch')
            if match['status'] == 'verified':
                result = match.get('result') if isinstance(match.get('result'), dict) else {}
                scores, winner = result.get('scores'), result.get('winner_slot')
                valid_scores = isinstance(scores, list) and len(scores) == 2 and all(
                    type(score) in (int, float) and isfinite(score) for score in scores)
                if not scored:
                    if result.get('outcome') != 'solo' or 'winner_slot' not in result or result['winner_slot'] is not None:
                        reasons.append('invalid_result')
                elif 'winner_slot' not in result or not (winner is None or type(winner) is int and winner in (0, 1)) or not valid_scores:
                    reasons.append('invalid_result')
                if scored and not reasons:
                    outcomes = [{'fly_id': fly, 'score': scores[slot],
                                 'outcome': 'draw' if winner is None else 'win' if winner == slot else 'loss'}
                                for slot, fly in enumerate(expected['fly_ids'])]
            elif match['status'] == 'failed':
                reasons.append('failed_match')
            elif match['status'] not in {'queued', 'running'}:
                reasons.append('invalid_status')
        status = ('missing' if not candidates else 'failed' if match and match['status'] == 'failed'
                  else 'mismatched') if reasons else match['status']
        rows.append({'seed': expected['seed'], 'spawn_order': ordinal % 2 + 1 if scored else 1,
                     'fly_ids': expected['fly_ids'], 'status': status,
                     'match_ids': [m['id'] for m in candidates], 'outcomes': outcomes,
                     'issues': list(dict.fromkeys(reasons)),
                     'errors': [m['error'] for m in candidates if m.get('error')]})
        issues.extend(reasons)
    unexpected = [m['id'] for values in buckets.values() for m in values]
    if unexpected:
        issues.append('unexpected_match')
    if not schedule:
        issues.append('missing_match')
    status = 'incomplete' if issues else 'complete' if all(row['status'] == 'verified' for row in rows) else 'running'
    standings = tournament_projection(matches, spec['fly_ids'], scope_checked=True)['standings'] if scored and status == 'complete' else []
    return {'protocol_id': PROTOCOL_ID, 'status': status, 'schedule': rows,
            'expected_matches': len(schedule), 'verified_matches': sum(row['status'] == 'verified' for row in rows),
            'unexpected_match_ids': unexpected, 'issues': list(dict.fromkeys(issues)),
            'standings': standings, 'ranking_policy': POLICY_ID if scored else None, 'sandbox': spec.get('sandbox', False),
            'ranking_error': ', '.join(dict.fromkeys(issues)) or None}


def admit_schedule(db, owner, spec, schedule, runtime_hash, now, *, tournament=None):
    """Queue an entire schedule in the caller's transaction, sharing quota and artifact checks."""
    from ..contracts import MatchRequest
    from ..models import require_model_bridge
    artifacts = {}
    for fly in spec['fly_ids']:
        row = db.execute('SELECT artifact_id,spec FROM flies WHERE id=?', (fly,)).fetchone()
        if not row:
            raise ValueError('Series contestant does not exist')
        require_model_bridge(json.loads(row[1]).get('model_profile', 'malecns-lif-cpu-v1'), spec.get('bridge_profile', 'legacy-v1'))
        artifacts[fly] = row[0]
    pending = db.execute("SELECT count(*) FROM matches WHERE owner=? AND status IN ('queued','running')", (owner,)).fetchone()[0]
    if pending + len(schedule) > 12:
        raise ValueError(f'Series needs {len(schedule)} matches; {12-pending} queue slots available. Use fewer entrants or seeds.')
    ids = []
    for ordinal, request in enumerate(schedule):
        MatchRequest.model_validate(request).validate_admission()
        ident = uuid.uuid4().hex
        db.execute("INSERT INTO matches(id,owner,request,artifacts,runtime_hash,status,created,updated,tournament) VALUES(?,?,?,?,?,'queued',?,?,?)",
                   (ident, owner, canonical(request).decode(), canonical([artifacts[f] for f in request['fly_ids']]).decode(), runtime_hash, now+ordinal*.000001, now, tournament))
        ids.append(ident)
    return {'runtime_hash': runtime_hash, 'artifacts': artifacts, 'match_ids': ids}
