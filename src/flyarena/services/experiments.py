"""Durable admission and generation-fenced experiment repository (no HTTP/providers)."""
from __future__ import annotations
import json
import time
import uuid
from ..common import canonical, digest
from ..research import ExperimentSpec


def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS fly_provenance(fly_id TEXT PRIMARY KEY,reference_kind TEXT NOT NULL,release_id TEXT,submission_channel TEXT NOT NULL,attestation TEXT);
    CREATE TABLE IF NOT EXISTS research_references(release_id TEXT NOT NULL,role TEXT NOT NULL,fly_id TEXT NOT NULL,definition TEXT NOT NULL,PRIMARY KEY(release_id,role));
    CREATE TABLE IF NOT EXISTS experiments(id TEXT PRIMARY KEY,owner TEXT NOT NULL,spec TEXT NOT NULL,subjects TEXT NOT NULL,conditions TEXT NOT NULL,status TEXT NOT NULL,error TEXT,reports TEXT NOT NULL DEFAULT '[]',comparison TEXT,created REAL NOT NULL,updated REAL NOT NULL,generation INTEGER NOT NULL DEFAULT 0,lease TEXT,expires REAL NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS experiment_keys(owner TEXT NOT NULL,key TEXT NOT NULL,payload TEXT NOT NULL,resource TEXT NOT NULL,PRIMARY KEY(owner,key));
    CREATE TABLE IF NOT EXISTS experiment_attempts(experiment_id TEXT NOT NULL,generation INTEGER NOT NULL,lease TEXT NOT NULL,status TEXT NOT NULL,error TEXT,PRIMARY KEY(experiment_id,generation));
    CREATE TABLE IF NOT EXISTS reference_run_cache(key TEXT PRIMARY KEY,report TEXT NOT NULL,folder TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS fly_experiments(fly_id TEXT PRIMARY KEY,experiment_id TEXT,status TEXT NOT NULL,error TEXT);
    CREATE INDEX IF NOT EXISTS research_queue ON experiments(status,created);
    ''')


class ExperimentRepository:
    def __init__(self, store):
        self.store = store

    def get(self, ident):
        with self.store.db() as db:
            row = db.execute('SELECT * FROM experiments WHERE id=?', (ident,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        for k in ('spec', 'subjects', 'conditions', 'reports', 'comparison'):
            result[k] = json.loads(result[k]) if result[k] else None
        result.pop('lease'); result.pop('expires')
        return result

    def list(self, owner=None):
        with self.store.db() as db:
            ids = [r[0] for r in db.execute('SELECT id FROM experiments WHERE (? IS NULL OR owner=?) ORDER BY created DESC LIMIT 100', (owner, owner))]
        return [self.get(i) for i in ids]

    def admit(self, owner, spec, subjects, conditions, key=None):
        spec = ExperimentSpec.model_validate(spec).model_dump()
        if key is not None and (not key or len(key) > 128):
            raise ValueError('Idempotency key must contain 1 to 128 characters')
        payload = digest(spec)
        ident, now = uuid.uuid4().hex, time.time()
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if key:
                old = db.execute('SELECT * FROM experiment_keys WHERE owner=? AND key=?', (owner, key)).fetchone()
                if old:
                    if old['payload'] != payload:
                        raise ValueError('Idempotency key already used for a different experiment')
                    return self.get(old['resource'])
            design = db.execute('SELECT owner FROM flies WHERE id=?', (spec['fly_id'],)).fetchone()
            if design is None or design['owner'] != owner:
                raise ValueError('Experiment design must belong to authenticated owner')
            pending = db.execute("SELECT count(*) FROM experiments WHERE owner=? AND status IN ('queued','running')", (owner,)).fetchone()[0]
            if pending >= 12:
                raise ValueError('Experiment queue quota reached: 12 unfinished experiments')
            if [s['role'] for s in subjects] != ['wildtype', 'official', 'design'] or subjects[2]['fly_id'] != spec['fly_id']:
                raise ValueError('Invalid frozen subject triplet')
            for subject in subjects:
                row = db.execute('SELECT artifact_id FROM flies WHERE id=?', (subject['fly_id'],)).fetchone()
                if row is None or row[0] != subject['artifact_id']:
                    raise ValueError('Frozen artifact mismatch')
            db.execute("INSERT INTO experiments(id,owner,spec,subjects,conditions,status,created,updated) VALUES(?,?,?,?,?,'queued',?,?)",
                       (ident, owner, canonical(spec).decode(), canonical(subjects).decode(), canonical(conditions).decode(), now, now))
            if key:
                db.execute('INSERT INTO experiment_keys VALUES(?,?,?,?)', (owner,key,payload,ident))
        return self.get(ident)

    def claim(self):
        now = time.time()
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            for row in db.execute("SELECT id,generation FROM experiments WHERE status='running' AND expires<?", (now,)).fetchall():
                status = 'queued' if row['generation'] < 2 else 'failed'
                db.execute("UPDATE experiment_attempts SET status='failed',error='Lease expired' WHERE experiment_id=? AND generation=?", (row['id'], row['generation']))
                db.execute("UPDATE experiments SET status=?,error='Worker lease expired',updated=? WHERE id=?", (status,now,row['id']))
            if db.execute("SELECT 1 FROM experiments WHERE status='running'").fetchone():
                return None
            row = db.execute("SELECT id,generation FROM experiments WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if row is None:
                return None
            lease, generation = uuid.uuid4().hex, row['generation']+1
            db.execute("UPDATE experiments SET status='running',generation=?,lease=?,expires=?,updated=?,error=NULL WHERE id=?", (generation,lease,now+120,now,row['id']))
            db.execute("INSERT INTO experiment_attempts VALUES(?,?,?,'running',NULL)", (row['id'],generation,lease))
            return row['id'],lease,generation

    def heartbeat(self, ident, lease, generation):
        now = time.time()
        with self.store.db() as db:
            count = db.execute("UPDATE experiments SET expires=?,updated=? WHERE id=? AND lease=? AND generation=? AND status='running' AND expires>=?", (now+120,now,ident,lease,generation,now)).rowcount
        if not count:
            raise RuntimeError('Experiment lease is no longer active')

    def finish(self, ident, lease, generation, reports, comparison=None, error=None):
        now = time.time()
        status = 'failed' if error or comparison is None else 'complete'
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            count = db.execute("UPDATE experiments SET status=?,reports=?,comparison=?,error=?,updated=? WHERE id=? AND lease=? AND generation=? AND status='running' AND expires>=?",
                (status,canonical(reports).decode(),canonical(comparison).decode() if comparison is not None else None,error,now,ident,lease,generation,now)).rowcount
            if not count:
                raise RuntimeError('Rejected stale experiment result')
            db.execute('UPDATE experiment_attempts SET status=?,error=? WHERE experiment_id=? AND generation=? AND lease=?', (status,error,ident,generation,lease))

    def save_schedule(self, fly_id, experiment_id=None, error=None):
        with self.store.db() as db:
            db.execute('INSERT INTO fly_experiments VALUES(?,?,?,?) ON CONFLICT(fly_id) DO UPDATE SET experiment_id=excluded.experiment_id,status=excluded.status,error=excluded.error',
                       (fly_id,experiment_id,'error' if error else 'queued',error))
