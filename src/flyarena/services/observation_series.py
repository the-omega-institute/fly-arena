"""Durable sandbox observations: frozen admission, ordinary worker matches, no invented evidence."""
import json
import time
import uuid
from typing import Literal

from pydantic import Field, StrictInt, model_validator

from ..common import canonical, digest
from ..contracts import MatchRequest, TournamentRequest
from .competition_protocol import DEFAULTS, admit_schedule, expected_schedule, schedule_report

PROTOCOL_ID = 'observation-series/v1'


class ObservationSeriesRequest(TournamentRequest):
    sandbox: Literal[True] = True
    mode: Literal['forage', 'duel'] = 'forage'
    fly_ids: list[str] = Field(min_length=1, max_length=2)
    seeds: list[StrictInt] = Field(default_factory=lambda: [42], min_length=1, max_length=3)
    duration_seconds: StrictInt = Field(default=5, ge=1, le=300)

    @model_validator(mode='after')
    def valid_entries(self):
        if len(set(self.fly_ids)) != len(self.fly_ids):
            raise ValueError('Series entries must be distinct')
        if len(set(self.seeds)) != len(self.seeds) or any(s < 0 or s > 2**31 - 1 for s in self.seeds):
            raise ValueError('Seeds must be distinct nonnegative int32 values')
        for request in observation_schedule(self.model_dump()):
            MatchRequest.model_validate(request).validate_admission()
        return self


def observation_schedule(spec):
    if spec['mode'] == 'duel':
        # Validate cardinality before combinations could conceal a missing opponent.
        MatchRequest(**{k: v for k, v in spec.items() if k not in {'name', 'seeds'}}, seed=spec['seeds'][0])
        return expected_schedule(spec)
    base = {key: spec.get(key, value) for key, value in DEFAULTS.items() if key != 'season_id'}
    base.update({key: spec[key] for key in ('map_id', 'mode', 'duration_seconds', 'fly_ids')})
    return [dict(base, seed=seed) for seed in spec['seeds']]


def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS observation_series(id TEXT PRIMARY KEY,owner TEXT NOT NULL,spec TEXT NOT NULL,schedule TEXT NOT NULL,frozen TEXT NOT NULL,created REAL NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS observation_legs(series_id TEXT NOT NULL,match_id TEXT UNIQUE NOT NULL,PRIMARY KEY(series_id,match_id))')


def prior_submission(store, owner, key, spec):
    if not key:
        return None
    with store.db() as db:
        row = db.execute('SELECT payload,resource FROM idempotency WHERE owner=? AND key=?', (owner, key)).fetchone()
    if row is None:
        return None
    prior = get_series(store, row['resource'])
    if prior is None or row['payload'] != digest({'observation': spec}):
        raise ValueError('Idempotency key already used for a different request')
    return prior


def create_series(store, owner, spec, runtime_hash, key=None):
    spec = ObservationSeriesRequest.model_validate(spec).model_dump()
    ident, now = uuid.uuid4().hex, time.time()
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        prior = prior_submission(store, owner, key, spec)
        if prior is not None:
            return prior
        schedule = observation_schedule(spec)
        frozen = admit_schedule(db, owner, spec, schedule, runtime_hash, now)
        db.execute('INSERT INTO observation_series VALUES(?,?,?,?,?,?)',
                   (ident, owner, canonical(spec).decode(), canonical(schedule).decode(), canonical(frozen).decode(), now))
        db.executemany('INSERT INTO observation_legs VALUES(?,?)', [(ident, mid) for mid in frozen['match_ids']])
        if key:
            db.execute('INSERT INTO idempotency VALUES(?,?,?,?)', (owner, key, digest({'observation': spec}), ident))
    return get_series(store, ident)


def get_series(store, ident):
    with store.db() as db:
        row = db.execute('SELECT * FROM observation_series WHERE id=?', (ident,)).fetchone()
        ids = [r[0] for r in db.execute('SELECT match_id FROM observation_legs WHERE series_id=?', (ident,))]
    if row is None:
        return None
    series = dict(row)
    for key in ('spec', 'schedule', 'frozen'):
        series[key] = json.loads(series[key])
    matches = [dict(match, observation=ident) for mid in ids if (match := store.match(mid)) is not None]
    scored = series['spec']['mode'] == 'duel'
    report = schedule_report(series, matches, series['schedule'], scored=scored, membership='observation', frozen=series['frozen'])
    # Keep the frozen request list as well as the evidence projection of every leg.
    series['expected_schedule'] = series.pop('schedule')
    return dict(series, **dict(report, protocol_id=PROTOCOL_ID), matches=matches, observation_only=not scored)


def list_series(store, owner=None):
    with store.db() as db:
        ids = [row[0] for row in db.execute('SELECT id FROM observation_series WHERE (? IS NULL OR owner=?) ORDER BY created DESC LIMIT 30', (owner, owner))]
    return [get_series(store, ident) for ident in ids]
