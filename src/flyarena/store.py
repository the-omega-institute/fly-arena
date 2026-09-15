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

    def add_fly(self, owner: str, spec: dict, report: dict) -> dict:
        ident = uuid.uuid4().hex
        with self.db() as db:
            if spec.get("parent_id") and not db.execute("SELECT 1 FROM flies WHERE id=?", (spec["parent_id"],)).fetchone():
                raise ValueError("Parent fly does not exist")
            if db.execute("SELECT count(*) FROM flies WHERE owner=?", (owner,)).fetchone()[0] >= 100:
                raise ValueError("This workspace allows 100 published flies per designer")
            db.execute("INSERT INTO flies VALUES(?,?,?,?,?,?,?,?)", (ident, owner, spec["name"], spec["color"], canonical(spec).decode(),
                        report["artifact_id"], canonical(report).decode(), time.time()))
        return self.fly(ident)

    def fly(self, ident: str) -> dict | None:
        with self.db() as db:
            row = db.execute("SELECT f.*,coalesce(i.name,'Arena Lab') AS designer FROM flies f LEFT JOIN identities i ON f.owner=i.id WHERE f.id=?", (ident,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["spec"], result["report"] = json.loads(result["spec"]), json.loads(result["report"])
        return result

    def flies(self) -> list[dict]:
        with self.db() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM flies ORDER BY created DESC LIMIT 200")]
        return [self.fly(i) for i in ids]

    def add_match(self, owner: str, request: dict, runtime_hash: str, *, key: str | None = None, tournament: str | None = None) -> dict:
        ident, now = uuid.uuid4().hex, time.time()
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            payload = digest(request)
            if key:
                existing = db.execute("SELECT payload,resource FROM idempotency WHERE owner=? AND key=?", (owner, key)).fetchone()
                if existing:
                    if existing["payload"] != payload:
                        raise ValueError("Idempotency key already used for a different request")
                    return self.match(existing["resource"])
            if db.execute("SELECT count(*) FROM matches WHERE owner=? AND status IN ('queued','running')", (owner,)).fetchone()[0] >= 12:
                raise ValueError("Queue quota reached: at most 12 unfinished matches per designer")
            artifacts = []
            for fly_id in request["fly_ids"]:
                fly = db.execute("SELECT artifact_id FROM flies WHERE id=?", (fly_id,)).fetchone()
                if not fly:
                    raise ValueError("Contestant does not exist")
                artifacts.append(fly[0])
            db.execute("INSERT INTO matches(id,owner,request,artifacts,runtime_hash,status,created,updated,tournament) VALUES(?,?,?,?,?,'queued',?,?,?)",
                       (ident, owner, canonical(request).decode(), canonical(artifacts).decode(), runtime_hash, now, now, tournament))
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
            row = db.execute("SELECT id,attempt FROM matches WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
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

    def leaderboard(self) -> list[dict]:
        rows = {f["id"]: {"fly": f, "wins": 0, "draws": 0, "losses": 0, "matches": 0, "food": 0.0, "points": 0} for f in self.flies()}
        with self.db() as db:
            all_ids = [r[0] for r in db.execute("SELECT id FROM matches WHERE status='verified'")]
        for match in [self.match(i) for i in all_ids]:
            if match["status"] != "verified":
                continue
            ids, verdict = match["request"]["fly_ids"], match["result"]
            if len(ids) != 2 or ids[0] == ids[1]:
                continue
            for slot, ident in enumerate(ids):
                if ident not in rows:
                    continue
                row = rows[ident]
                row["matches"] += 1
                row["food"] += verdict["scores"][slot]
                if verdict["winner_slot"] is None:
                    row["draws"] += 1
                    row["points"] += 1
                elif verdict["winner_slot"] == slot:
                    row["wins"] += 1
                    row["points"] += 3
                else:
                    row["losses"] += 1
        return sorted(rows.values(), key=lambda r: (-r["points"], -r["food"], r["fly"]["id"]))

    def add_tournament(self, owner: str, spec: dict, runtime_hash: str, key: str | None = None) -> dict:
        """Admit the complete round robin atomically, including reversed slots."""
        from itertools import combinations
        from .contracts import MatchRequest
        ident, now = uuid.uuid4().hex, time.time()
        payload = digest({'tournament': spec})
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if key:
                old = db.execute('SELECT payload,resource FROM idempotency WHERE owner=? AND key=?', (owner,key)).fetchone()
                if old:
                    if old['payload'] != payload:
                        raise ValueError('Idempotency key already used for a different request')
                    return self.tournament(old['resource'])
            artifacts = {}
            for fly in spec['fly_ids']:
                row = db.execute('SELECT artifact_id FROM flies WHERE id=?',(fly,)).fetchone()
                if not row: raise ValueError('Tournament contestant does not exist')
                artifacts[fly] = row[0]
            schedule = []
            for seed in spec['seeds']:
                for a,b in combinations(spec['fly_ids'],2):
                    for slots in [[a,b],[b,a]]:
                        schedule.append(MatchRequest(fly_ids=slots,map_id=spec['map_id'],mode=spec['mode'],seed=seed,duration_seconds=spec['duration_seconds']).model_dump())
            pending = db.execute("SELECT count(*) FROM matches WHERE owner=? AND status IN ('queued','running')",(owner,)).fetchone()[0]
            if pending+len(schedule)>12:
                raise ValueError(f'Tournament needs {len(schedule)} matches; {12-pending} queue slots available. Use fewer entrants or seeds.')
            db.execute('INSERT INTO tournaments VALUES(?,?,?,?)',(ident,owner,canonical(spec).decode(),now))
            for ordinal,request in enumerate(schedule):
                db.execute("INSERT INTO matches(id,owner,request,artifacts,runtime_hash,status,created,updated,tournament) VALUES(?,?,?,?,?,'queued',?,?,?)",(uuid.uuid4().hex,owner,canonical(request).decode(),canonical([artifacts[f] for f in request['fly_ids']]).decode(),runtime_hash,now+ordinal*.000001,now,ident))
            if key: db.execute('INSERT INTO idempotency VALUES(?,?,?,?)',(owner,key,payload,ident))
        return self.tournament(ident)

    def tournament(self, ident: str) -> dict | None:
        with self.db() as db:
            row = db.execute('SELECT * FROM tournaments WHERE id=?',(ident,)).fetchone()
            ids = [r[0] for r in db.execute('SELECT id FROM matches WHERE tournament=? ORDER BY created',(ident,))]
        if row is None: return None
        result = dict(row); result['spec'] = json.loads(result['spec'])
        matches = [self.match(i) for i in ids]
        standings = {f:{'fly_id':f,'points':0,'played':0,'wins':0,'draws':0,'losses':0} for f in result['spec']['fly_ids']}
        for match in matches:
            if match['status']!='verified': continue
            for slot,f in enumerate(match['request']['fly_ids']):
                r = standings[f]; r['played']+=1
                winner = match['result']['winner_slot']
                if winner is None: r['draws']+=1; r['points']+=1
                elif winner==slot: r['wins']+=1; r['points']+=3
                else: r['losses']+=1
        terminal = all(m['status'] in {'verified','failed'} for m in matches)
        result.update(matches=matches,standings=sorted(standings.values(),key=lambda r:(-r['points'],r['fly_id'])),status=('incomplete' if any(m['status']=='failed' for m in matches) else 'complete') if terminal else 'running')
        return result

    def tournaments(self) -> list[dict]:
        with self.db() as db:
            ids = [r[0] for r in db.execute('SELECT id FROM tournaments ORDER BY created DESC LIMIT 30')]
        return [self.tournament(i) for i in ids]
