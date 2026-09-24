from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import time
import uuid

from .common import VAR, canonical, digest


class Store:
    def __init__(self, root: Path = VAR):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "arena.sqlite3"
        with self.db() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS identities(id TEXT PRIMARY KEY,name TEXT NOT NULL,token_hash TEXT UNIQUE NOT NULL,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS flies(id TEXT PRIMARY KEY,owner TEXT NOT NULL,name TEXT NOT NULL,color TEXT NOT NULL,spec TEXT NOT NULL,artifact_id TEXT NOT NULL,report TEXT NOT NULL,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS matches(id TEXT PRIMARY KEY,owner TEXT NOT NULL,request TEXT NOT NULL,artifacts TEXT NOT NULL,runtime_hash TEXT NOT NULL,status TEXT NOT NULL,progress REAL DEFAULT 0,attempt INTEGER DEFAULT 0,lease TEXT,expires REAL DEFAULT 0,result TEXT,error TEXT,created REAL NOT NULL,updated REAL NOT NULL,tournament TEXT);
            CREATE TABLE IF NOT EXISTS attempts(match_id TEXT NOT NULL,generation INTEGER NOT NULL,lease TEXT NOT NULL,status TEXT NOT NULL,error TEXT,PRIMARY KEY(match_id,generation));
            CREATE TABLE IF NOT EXISTS tournaments(id TEXT PRIMARY KEY,owner TEXT NOT NULL,spec TEXT NOT NULL,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS idempotency(owner TEXT NOT NULL,key TEXT NOT NULL,payload TEXT NOT NULL,resource TEXT NOT NULL,PRIMARY KEY(owner,key));
            CREATE INDEX IF NOT EXISTS match_queue ON matches(status,created);
            """)

            from .services.experiments import initialize
            initialize(db)
            from .services.training import initialize as initialize_training
            initialize_training(db)
            from .services.observation_series import initialize as initialize_observations
            initialize_observations(db)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def identity(self, name: str) -> dict:
        token, ident = secrets.token_urlsafe(32), uuid.uuid4().hex
        if not name.strip():
            raise ValueError("Name cannot be blank")
        with self.db() as db:
            db.execute("INSERT INTO identities VALUES(?,?,?,?)", (ident, name.strip(), hashlib.sha256(token.encode()).hexdigest(), time.time()))
        return {"id": ident, "name": name.strip(), "token": token}

    def authenticate(self, token: str) -> dict | None:
        with self.db() as db:
            row = db.execute("SELECT id,name FROM identities WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        return dict(row) if row else None

    def add_fly(self, owner: str, spec: dict, report: dict, *, submission_channel: str = 'web', agent_channel: bool = False, training: tuple | None = None, external_proposal: bool = False, copy_key: str | None = None) -> dict:
        if any(k in spec for k in ('provenance','scientific_version','reference_kind','release_id','submission_channel')):
            raise ValueError('Provenance is server-owned')
        if submission_channel not in {'web','api'}:
            raise ValueError('Invalid public submission channel')
        ident = uuid.uuid4().hex
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if copy_key:
                previous=db.execute('SELECT payload,resource FROM idempotency WHERE owner=? AND key=?',(owner,copy_key)).fetchone()
                if previous:
                    if previous['payload']!=canonical(spec).decode():raise ValueError('Published source changed since this copy was saved')
                    return self.fly(previous['resource'])
            if external_proposal:
                from .services.training import check_proposal
                prior = check_proposal(db, owner, training, spec)
                if prior:return self.fly(prior)
            elif training:
                old=db.execute('SELECT fly_id FROM training_members WHERE run_id=? AND generation=? AND slot=?',training).fetchone()
                if old:return self.fly(old[0])
            if spec.get('parent_id'):
                parent_row=db.execute('SELECT spec FROM flies WHERE id=?',(spec['parent_id'],)).fetchone()
                published=self.published_fly(spec['parent_id']) if parent_row is None else None
                if parent_row is None and published is None:raise ValueError('Parent fly does not exist')
                parent=json.loads(parent_row['spec']) if parent_row else published['spec']
                from .models import PROFILES
                if parent.get('connectome_sha256')!=spec.get('connectome_sha256') or spec.get('model_profile') not in PROFILES:
                    raise ValueError('Parent must use the same graph and a supported model profile')
            if not training and db.execute("SELECT count(*) FROM flies f WHERE owner=? AND NOT EXISTS(SELECT 1 FROM training_members m WHERE m.fly_id=f.id AND m.saved=0)", (owner,)).fetchone()[0] >= 100:
                raise ValueError("This workspace allows 100 published flies per designer")
            db.execute("INSERT INTO flies VALUES(?,?,?,?,?,?,?,?)", (ident, owner, spec["name"], spec["color"], canonical(spec).decode(),
                        report["artifact_id"], canonical(report).decode(), time.time()))
            db.execute('INSERT INTO fly_provenance VALUES(?,?,?,?,NULL)', (ident,'ai' if agent_channel else 'user',None,submission_channel))
            if copy_key:db.execute('INSERT INTO idempotency VALUES(?,?,?,?)',(owner,copy_key,canonical(spec).decode(),ident))
            if training:db.execute('INSERT INTO training_members(run_id,generation,slot,fly_id) VALUES(?,?,?,?)',(*training,ident))
            if external_proposal:
                db.execute("UPDATE training_runs SET status=CASE WHEN status='awaiting_candidates' THEN 'queued' ELSE status END,updated=? WHERE id=?", (time.time(), training[0]))
        return self.fly(ident)

    def fly(self, ident: str) -> dict | None:
        with self.db() as db:
            row = db.execute("SELECT f.*,coalesce(i.name,'Arena Lab') AS designer FROM flies f LEFT JOIN identities i ON f.owner=i.id WHERE f.id=?", (ident,)).fetchone()
        if row is None:
            return self.published_fly(ident)
        result = dict(row)
        result["spec"], result["report"] = json.loads(result["spec"]), json.loads(result["report"])
        with self.db() as db:
            provenance = db.execute('SELECT reference_kind,release_id,submission_channel FROM fly_provenance WHERE fly_id=?', (ident,)).fetchone()
            scheduled = db.execute('SELECT experiment_id,status,error FROM fly_experiments WHERE fly_id=?', (ident,)).fetchone()
        result.update(dict(provenance) if provenance else {'reference_kind':None,'release_id':None,'submission_channel':None})
        result.update(experiment_id=scheduled['experiment_id'] if scheduled else None,
                      experiment_status=scheduled['status'] if scheduled else None,
                      experiment_error=scheduled['error'] if scheduled else None)
        if scheduled and scheduled['experiment_id']:
            from .services.experiments import ExperimentRepository
            experiment = ExperimentRepository(self).get(scheduled['experiment_id'])
            if experiment:
                result.update(experiment_status=experiment['status'],experiment_error=experiment['error'])
        return result

    def published_fly(self, ident: str) -> dict | None:
        """Resolve a public specimen without importing its account or weights."""
        from .services.training import TrainingService
        from .contracts import FlySpec
        candidates=[]
        for run in TrainingService(self,None)._bundled_showcase():
            for member in run.get('members',[]):
                sample=member.get('fly',{})
                if member.get('fly_id')!=ident or sample.get('id')!=ident:continue
                try:spec=FlySpec.model_validate(sample.get('spec')).model_dump(by_alias=True)
                except ValueError:continue
                if not isinstance(sample.get('artifact_id'),str) or not isinstance(sample.get('report'),dict):continue
                candidates.append(dict(id=ident,owner=None,designer='Published sample',name=spec['name'],color=spec['color'],
                    spec=spec,report=sample['report'],artifact_id=sample['artifact_id'],created=sample.get('created',run.get('created',0)),
                    reference_kind=None,submission_channel=None,release_id=None,
                    source={'kind':'published-training','run_id':run['id'],'generation':member['generation'],
                            'slot':member['slot'],'fitness':member.get('fitness'),'evaluation_context':run.get('evaluation_context'),
                            'plan':run['spec']}))
        if not candidates:return None
        first=candidates[0]
        if any(c['spec']!=first['spec'] or c['artifact_id']!=first['artifact_id'] for c in candidates[1:]):
            raise ValueError('Conflicting published snapshots for this fly')
        return first

    def flies(self) -> list[dict]:
        with self.db() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM flies f WHERE NOT EXISTS(SELECT 1 FROM training_members m WHERE m.fly_id=f.id AND m.saved=0) ORDER BY created DESC LIMIT 200")]
        return [self.fly(i) for i in ids]

    def prior_submission(self, owner: str, key: str | None, request: dict, *, tournament: bool = False):
        """Resolve immutable retries before mutable runtime availability checks.

        Normalizing additive defaults preserves legacy keys whose stored payload
        predates bridge_profile. A key cannot cross resource kinds or semantics.
        """
        if not key:
            return None
        with self.db() as db:
            row = db.execute("SELECT resource FROM idempotency WHERE owner=? AND key=?", (owner,key)).fetchone()
        if row is None:
            return None
        from .contracts import MatchRequest, TournamentRequest
        prior = self.tournament(row[0]) if tournament else self.match(row[0])
        model = TournamentRequest if tournament else MatchRequest
        field = "spec" if tournament else "request"
        if prior is None or model.model_validate(prior[field]).model_dump() != model.model_validate(request).model_dump():
            raise ValueError("Idempotency key already used for a different request")
        return prior

    def add_match(self, owner: str, request: dict, runtime_hash: str, *, key: str | None = None, tournament: str | None = None, training: tuple | None = None) -> dict | None:
        ident, now = uuid.uuid4().hex, time.time()
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if training:
                old=db.execute('SELECT match_id FROM training_evaluations WHERE run_id=? AND generation=? AND slot=? AND trial=?',training).fetchone()
                if old:return self.match(old[0])
                run=db.execute('SELECT control,status FROM training_runs WHERE id=?',(training[0],)).fetchone()
                if run is None or run['control']!='run' or run['status'] in {'complete','failed','stopped'}:return None
            payload = digest(request)
            if key:
                existing = db.execute("SELECT payload,resource FROM idempotency WHERE owner=? AND key=?", (owner, key)).fetchone()
                if existing:
                    return self.prior_submission(owner, key, request)
            from .contracts import MatchRequest
            MatchRequest.model_validate(request).validate_admission()
            if db.execute("SELECT count(*) FROM matches WHERE owner=? AND status IN ('queued','running')", (owner,)).fetchone()[0] >= 12:
                if training:return None
                raise ValueError("Queue quota reached: at most 12 unfinished matches per designer")
            artifacts = []
            for fly_id in request["fly_ids"]:
                fly = db.execute("SELECT artifact_id,spec FROM flies WHERE id=?", (fly_id,)).fetchone()
                if not fly:
                    raise ValueError("Contestant does not exist")
                from .models import require_model_bridge
                require_model_bridge(json.loads(fly[1]).get('model_profile','malecns-lif-cpu-v1'),request.get('bridge_profile','legacy-v1'))
                artifacts.append(fly[0])
            db.execute("INSERT INTO matches(id,owner,request,artifacts,runtime_hash,status,created,updated,tournament) VALUES(?,?,?,?,?,'queued',?,?,?)",
                       (ident, owner, canonical(request).decode(), canonical(artifacts).decode(), runtime_hash, now, now, tournament))
            if training:db.execute("INSERT INTO training_evaluations VALUES(?,?,?,?,?)",(*training,ident))
            if key:
                db.execute("INSERT INTO idempotency VALUES(?,?,?,?)", (owner, key, payload, ident))
        return self.match(ident)

    def match(self, ident: str) -> dict | None:
        with self.db() as db:
            row = db.execute("SELECT * FROM matches WHERE id=?", (ident,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        for key in ["request", "artifacts", "result"]:
            result[key] = json.loads(result[key]) if result[key] else None
        result.pop("lease", None)
        result.pop("expires", None)
        return result

    def matches(self) -> list[dict]:
        with self.db() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM matches ORDER BY created DESC LIMIT 100")]
        return [self.match(i) for i in ids]

    def claim(self) -> tuple[str, str, int] | None:
        now = time.time()
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            for row in db.execute("SELECT id,attempt FROM matches WHERE status='running' AND expires<?", (now,)).fetchall():
                db.execute("UPDATE attempts SET status='infra_failed',error='Lease expired' WHERE match_id=? AND generation=?", (row["id"], row["attempt"]))
                db.execute("UPDATE matches SET status=?,error='Worker lease expired',updated=? WHERE id=?", ("queued" if row["attempt"] < 2 else "failed", now, row["id"]))
            if db.execute("SELECT 1 FROM matches WHERE status='running' LIMIT 1").fetchone():
                return None
            from .services.queue_status import queue_order
            training = {r[0] for r in db.execute('SELECT match_id FROM training_evaluations')}
            pending = db.execute("SELECT id,attempt,status,created FROM matches WHERE status='queued'").fetchall()
            row = min(pending, key=lambda r: queue_order(r, training, now)) if pending else None
            if row is None:
                return None
            lease, generation = uuid.uuid4().hex, row["attempt"] + 1
            db.execute("UPDATE matches SET status='running',progress=0,attempt=?,lease=?,expires=?,updated=?,error=NULL WHERE id=?",
                       (generation, lease, now + 120, now, row["id"]))
            db.execute("INSERT INTO attempts VALUES(?,?,?,'running',NULL)", (row["id"], generation, lease))
            return row["id"], lease, generation

    def heartbeat(self, ident: str, lease: str, progress: float):
        now = time.time()
        with self.db() as db:
            changed = db.execute("UPDATE matches SET progress=?,expires=?,updated=? WHERE id=? AND lease=? AND status='running' AND expires>=?",
                                (progress, now + 120, now, ident, lease, now)).rowcount
            if not changed:
                raise RuntimeError("Worker lease is no longer active")

    def finish(self, ident: str, lease: str, result: dict | None, error: str | None = None):
        now = time.time()
        status = "verified" if result else "failed"
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute("UPDATE matches SET status=?,progress=?,result=?,error=?,updated=? WHERE id=? AND lease=? AND status='running' AND expires>=?",
                                (status, 1 if result else 0, canonical(result).decode() if result else None, error, now, ident, lease, now)).rowcount
            if not changed:
                raise RuntimeError("Rejected stale worker result")
            db.execute("UPDATE attempts SET status=?,error=? WHERE match_id=? AND lease=?", (status, error, ident, lease))

    def result_folder(self, match: dict) -> Path:
        return self.root / "runs" / match["id"] / str(match["attempt"])

    def leaderboard(self, *, runtime_hash=None, scenario_id=None, mode=None, season_id='genesis-alpha', bridge_profile=None) -> list[dict]:
        from .services.ranking import rank
        with self.db() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM matches WHERE status='verified' AND id NOT IN (SELECT match_id FROM training_evaluations)")]
        return rank(self.flies(), [self.match(i) for i in ids], runtime_hash=runtime_hash,
                    scenario_id=scenario_id, mode=mode, season_id=season_id, bridge_profile=bridge_profile)

    def add_tournament(self, owner: str, spec: dict, runtime_hash: str, key: str | None = None) -> dict:
        """Admit the complete round robin atomically, including reversed slots."""
        from .services.competition_protocol import expected_schedule, admit_schedule
        ident, now = uuid.uuid4().hex, time.time()
        payload = digest({'tournament': spec})
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if key:
                old = db.execute('SELECT payload,resource FROM idempotency WHERE owner=? AND key=?', (owner,key)).fetchone()
                if old:
                    return self.prior_submission(owner, key, spec, tournament=True)
            from .contracts import TournamentRequest
            TournamentRequest.model_validate(spec).validate_admission()
            schedule = expected_schedule(spec)
            db.execute('INSERT INTO tournaments VALUES(?,?,?,?)',(ident,owner,canonical(spec).decode(),now))
            admit_schedule(db, owner, spec, schedule, runtime_hash, now, tournament=ident)
            if key: db.execute('INSERT INTO idempotency VALUES(?,?,?,?)',(owner,key,payload,ident))
        return self.tournament(ident)

    def tournament(self, ident: str) -> dict | None:
        with self.db() as db:
            row = db.execute('SELECT * FROM tournaments WHERE id=?',(ident,)).fetchone()
            ids = [r[0] for r in db.execute('SELECT id FROM matches WHERE tournament=? ORDER BY created',(ident,))]
        if row is None: return None
        result = dict(row); result['spec'] = json.loads(result['spec'])
        matches = [self.match(i) for i in ids]
        from .services.competition_protocol import competition_protocol
        result.update(matches=matches, **competition_protocol(result, matches))
        return result

    def tournaments(self, owner: str | None = None) -> list[dict]:
        with self.db() as db:
            ids = [r[0] for r in db.execute('SELECT id FROM tournaments WHERE (? IS NULL OR owner=?) ORDER BY created DESC LIMIT 30', (owner, owner))]
        return [self.tournament(i) for i in ids]
