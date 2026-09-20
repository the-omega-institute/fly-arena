from __future__ import annotations

from contextlib import asynccontextmanager
from functools import lru_cache
import json
import os
import subprocess
import secrets
import threading
import time
from pathlib import Path

import numpy as np
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Query
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer

from .auth import AuthBoundary, AuthConfig, NyxIDClient
from .behavior import FITNESS_OBJECTIVES

from .common import DATA, ROOT, VAR, digest, write_json
from .compiler import BUDGET, Compiler
from .connectome import Connectome
from .contracts import CreateIdentity, FlySpec, MatchRequest, TournamentRequest
from .neural import PROFILE
from .models import catalog as model_catalog, require_model_bridge
from .runner import runtime_manifest
from .experiments.embodied_sensor import catalog as sensory_catalog
from .bridge import match_profiles, require_bridge, training_profiles, require_training_bridge
from .scenarios import MAPS, RULES, scenario, arena_scene
from .store import Store
from .worker import Worker
from .research import ExperimentSpec
from .services.research_service import ResearchService
from .services.life import LifeLedger, LifeNote
from .services.training import TrainingService, TrainingSpec, ProposedCandidate


def create_app(*, with_worker: bool = True, store: Store | None = None, auth_config: AuthConfig | None = None, oidc_client: NyxIDClient | None = None, research_service: ResearchService | None = None) -> FastAPI:
    store = store or Store()
    auth = AuthBoundary(store, auth_config or AuthConfig.from_env(), oidc_client)
    compile_lock = threading.Lock()
    registrations: dict[str, list[float]] = {}

    @lru_cache(maxsize=1)
    def compiler():
        return Compiler(Connectome())

    research = research_service or ResearchService(store,compiler)

    @asynccontextmanager
    async def lifespan(app):
        worker = Worker(store) if with_worker else None
        if worker:
            worker.start()
        try:
            yield
        finally:
            if worker:
                worker.stop()
            auth.provider.close()

    release_path = ROOT / 'release.json'
    release = json.loads(release_path.read_text()) if release_path.exists() else {'release':'development'}
    app = FastAPI(title="Fly Arena API", version=release['release'].removeprefix('v'), lifespan=lifespan,
                  description="Published connectome designs and trusted embodied matches. All submitted flies and match replays are public in this MVP workspace.")
    app.state.research = research
    def match_runtime(profile='legacy-v1', sensory_profile='odor-only-v1'):
        from .services.node import configured_node
        node = configured_node()
        if node and profile == 'legacy-v1':
            try:
                return node.runtime(profile, sensory_profile)
            except (ConnectionError, subprocess.TimeoutExpired) as exc:
                raise HTTPException(503, 'Compute node is temporarily unavailable; try again shortly') from exc
        return runtime_manifest(bridge_profile=profile, sensory_profile=sensory_profile)

    training = TrainingService(store, compiler)
    app.state.training = training
    ledger = LifeLedger(store)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.include_router(auth.router())

    @app.middleware("http")
    async def limits(request: Request, call_next):
        if request.url.path.startswith("/api") and request.method in {"POST", "PUT", "PATCH"}:
            size = request.headers.get("content-length")
            if size and (not size.isdigit() or int(size) > 8_000_000):
                return JSONResponse({"detail": "Request exceeds 8 MB limit"}, status_code=413)
            body = await request.body()
            if len(body) > 8_000_000:
                return JSONResponse({"detail": "Request exceeds 8 MB limit"}, status_code=413)
        response = await call_next(request)
        if request.url.path.startswith("/api/v1/auth") or request.url.path == "/api/v1/me":
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        return JSONResponse({"detail": str(error)}, status_code=422)

    def identity(request: Request, bearer=Depends(HTTPBearer(auto_error=False))):
        return auth.identity(request)

    def registered_agent(request, owner):
        from .auth import hashed
        authorization = request.headers.get('authorization', '')
        if not authorization.startswith('Bearer '):return False
        with store.db() as db:
            return db.execute('SELECT 1 FROM agent_tokens WHERE owner=? AND hash=? AND expires>?',
                              (owner['id'], hashed(authorization[7:]), time.time())).fetchone() is not None

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "connectome_ready": (DATA / "connectome/manifest.json").exists(),
                "readout_ready": (DATA / "connectome/readout.json").exists(), "version": app.version, "commit": release.get("commit")}

    @app.get("/api/v1/agent-guide", response_class=FileResponse,
             summary="Read how an AI can design, train and compare flies")
    def agent_guide():
        return FileResponse(ROOT / "docs/AI_QUICKSTART.md", media_type="text/markdown")

    @app.get("/api/v1/season")
    def season():
        graph = compiler().graph
        profiles = match_profiles()
        playable = {p["id"]: p for p in training_profiles()}
        profiles = [p | {"sandbox_ready": playable[p["id"]]["ready"],
                         "sensory_profiles": playable[p["id"]]["sensory_profiles"]} for p in profiles]
        return {"default_bridge_profile": "sensorimotor-research-v2" if profiles[1]["ready"] else "legacy-v1",
                "match_profiles": profiles, "id": "genesis-alpha", "name": "GENESIS / 创生季", "connectome": graph.manifest,
                "model": PROFILE, "models": model_catalog(), "budget": BUDGET, "rules": RULES,
                "runtime_sha256": digest(runtime_manifest()),
                "sensory_profiles": sensory_catalog(),
                "training_sensory_profiles": sensory_catalog(),
                "training_bridge_profiles": training_profiles(),
                "training_fitness_objectives": FITNESS_OBJECTIVES,
                "gallery_copy_available": True,
                "readout": json.loads((DATA / "connectome/readout.json").read_text()),
                "invite_required": bool(os.environ.get("ARENA_INVITE_CODE")),
                "privacy": "Published designs and matches are public. API tokens are private."}

    @app.post("/api/v1/identities", status_code=201)
    def register(body: CreateIdentity, request: Request, x_invite_code: str = Header(default="")):
        if auth.config.mode != "local":
            raise HTTPException(403, "Use NyxID to sign in")
        required = os.environ.get("ARENA_INVITE_CODE", "")
        if required and not secrets.compare_digest(required, x_invite_code):
            raise HTTPException(403, "A valid beta invite code is required")
        client = request.client.host if request.client else "local"
        now = time.time()
        recent = [t for t in registrations.get(client, []) if t > now - 3600]
        if len(recent) >= 5:
            raise HTTPException(429, "Designer registration rate limit reached")
        registrations[client] = recent + [now]
        return store.identity(body.name)

    @app.get("/api/v1/me")
    def me(owner: dict = Depends(identity)):
        return owner

    def optional_identity(request: Request):
        try:return identity(request)['id']
        except HTTPException as error:
            if error.status_code==401:return None
            raise

    @app.get('/api/v1/lives')
    def life_list(owner=Depends(optional_identity)):
        return ledger.listing(owner)

    @app.get('/api/v1/lives/{ident}')
    def life_get(ident: str, owner=Depends(optional_identity)):
        result=ledger.get(ident,owner)
        if result is None:raise HTTPException(404,'Life record not found')
        return result

    @app.get('/api/v1/lives/{ident}/experiences/{mid}')
    def life_observation(ident: str, mid: str, owner=Depends(optional_identity)):
        result=ledger.observation(ident,mid,owner)
        if result is None:raise HTTPException(404,'Experience not found')
        return result

    @app.post('/api/v1/lives/{ident}/notes',status_code=201)
    def life_note(ident: str, body: LifeNote, owner: dict = Depends(identity),
                  idempotency_key: str | None = Header(default=None)):
        return {'id':ledger.annotate(ident,owner['id'],body,idempotency_key)}

    @app.get("/api/v1/maps")
    def maps():
        return list(MAPS.values())

    @app.get("/api/v1/maps/{map_id}/preview")
    def map_preview(map_id: str, seed: int = Query(default=42, ge=0, le=2147483647),
                    bridge_profile: str = "legacy-v1"):
        if map_id not in MAPS:
            raise HTTPException(404, "Unknown map")
        return arena_scene(map_id, seed, bridge_profile)

    @app.get("/api/v1/flies")
    def flies():
        return store.flies()

    @app.get("/api/v1/flies/{ident}")
    def fly(ident: str):
        result = store.fly(ident)
        if result is None:
            raise HTTPException(404, "Fly not found")
        return result

    @app.post("/api/v1/flies/validate")
    def validate(spec: FlySpec, owner: dict = Depends(identity)):
        with compile_lock:
            return compiler().compile(spec)

    @app.post("/api/v1/flies/preview")
    def neural_preview(spec: FlySpec, owner: dict = Depends(identity)):
        """Observe the submitted design and matched WT under fixed odor pulses."""
        from .neural_preview import preview_design
        with compile_lock:
            return preview_design(compiler(), spec)

    @app.post("/api/v1/flies", status_code=201)
    def publish(spec: FlySpec, request: Request, owner: dict = Depends(identity), compare: bool = Query(default=False)):
        declared_channel = request.headers.get('x-arena-submission-channel')
        if declared_channel not in (None, 'web', 'api'):
            raise ValueError('Submission channel must be web or api; it grants no reference authority')
        bearer = request.headers.get('authorization') is not None
        channel = declared_channel or ('web' if not bearer or request.headers.get('sec-fetch-site') == 'same-origin' else 'api')
        with compile_lock:
            report = compiler().compile(spec, publish=True, root=store.root)
        # Only Arena-issued agent token records assert the registered agent channel.
        agent_channel = registered_agent(request, owner)
        if agent_channel:
            channel = 'api'
        fly = store.add_fly(owner['id'],spec.model_dump(by_alias=True),report,
                            submission_channel=channel,agent_channel=agent_channel)
        return research.schedule_saved(fly) if compare else fly

    @app.get('/api/v1/research/catalog')
    def research_catalog():
        return research.catalog()

    @app.post('/api/v1/experiments',status_code=202)
    def experiment_create(body: ExperimentSpec, owner: dict = Depends(identity),
                          idempotency_key: str | None = Header(default=None)):
        return research.admit(owner['id'],body,idempotency_key)

    @app.get('/api/v1/experiments')
    def experiments(summary: bool = False):
        return research.repository.list_summaries() if summary else research.repository.list()

    @app.get('/api/v1/experiments/{ident}')
    def experiment_get(ident: str):
        result = research.repository.get(ident)
        if result is None:
            raise HTTPException(404,'Experiment not found')
        return result

    @app.post("/api/v1/training", status_code=202)
    def training_create(body: TrainingSpec, owner: dict = Depends(identity), idempotency_key: str | None = Header(default=None)):
        require_training_bridge(body.bridge_profile)
        with compile_lock:
            ids = [body.founder_id] + ([body.opponent_id] if body.mode == 'contest' else [])
            for fly_id in ids:
                fly = store.fly(fly_id)
                if fly is None:
                    raise ValueError("Starting fly or opponent does not exist")
                require_model_bridge(fly['spec']['model_profile'],body.bridge_profile)
                compiler().compile(FlySpec.model_validate(fly['spec']))
        return training.create(owner['id'], body, digest(match_runtime(body.bridge_profile, body.sensory_profile)), idempotency_key)

    @app.get("/api/v1/training")
    def training_list(owner: dict = Depends(identity)):
        return training.list(owner['id'])

    @app.get('/api/v1/training-showcase')
    def training_showcase():
        return training.showcase()

    @app.get('/api/v1/training-showcase/{ident}')
    def training_example(ident: str):
        result=training.showcase(ident)
        if result is None:raise HTTPException(404,'Published session not found')
        return result

    def owned_training(ident, owner):
        session = training.get(ident)
        if session is None or session['owner'] != owner['id']:
            raise HTTPException(404, "Training session not found")
        return session

    @app.post('/api/v1/training-showcase/{ident}/flies/{fly_id}/copy', status_code=201)
    def copy_gallery_fly(ident: str, fly_id: str, request: Request, owner: dict = Depends(identity)):
        with compile_lock:
            return training.copy_published(ident,fly_id,owner['id'],agent_channel=registered_agent(request,owner))

    @app.get("/api/v1/training/{ident}")
    def training_get(ident: str, owner: dict = Depends(identity)):
        return owned_training(ident, owner)

    @app.post("/api/v1/training/{ident}/control")
    def training_control(ident: str, body: dict, owner: dict = Depends(identity)):
        owned_training(ident, owner)
        if set(body) != {'action'} or body['action'] not in ('pause','resume','stop'):
            raise ValueError("Provide action: pause, resume or stop")
        return training.control(ident, owner['id'], body['action'])

    @app.post("/api/v1/training/{ident}/candidates", status_code=201)
    def training_propose(ident: str, body: ProposedCandidate, request: Request, owner: dict = Depends(identity)):
        owned_training(ident, owner)
        with compile_lock:
            return training.propose(ident, owner['id'], body, agent_channel=registered_agent(request, owner))

    @app.post("/api/v1/training/{ident}/save")
    def training_save(ident: str, body: dict, owner: dict = Depends(identity)):
        owned_training(ident, owner)
        if set(body) != {'fly_id'} or not isinstance(body['fly_id'], str):
            raise ValueError("Provide a training fly_id")
        return training.save(ident, owner['id'], body['fly_id'])

    @app.post('/api/v1/training/{ident}/publish')
    def training_publish(ident: str, owner: dict = Depends(identity)):
        owned_training(ident, owner)
        return training.publish(ident,owner['id'])

    def replay_designs(match):
        if match is None or 'participants' in match:
            return match
        artifacts = match.get('artifacts')
        if not isinstance(artifacts, list) or len(artifacts) != len(match['request']['fly_ids']):
            return match
        participants = []
        for slot, fly_id in enumerate(match['request']['fly_ids']):
            fly = store.fly(fly_id)
            if fly is None or fly['artifact_id'] != artifacts[slot]:
                continue
            participants.append({key: fly[key] for key in ('id', 'name', 'color', 'artifact_id', 'spec')}
                                | {'report': {key: fly['report'][key] for key in ('budget_used', 'budget_limit') if key in fly['report']}})
        return {**match, 'participants': participants}

    @lru_cache(maxsize=8)
    def compiled_neighborhood(artifact_id, spec_json, sample_ids):
        from .brain_graph import build
        with compile_lock:
            return build(compiler().graph, compiler(), {'artifact_id': artifact_id, 'spec': json.loads(spec_json)}, sample_ids, store.root)

    @app.get('/api/v1/matches/{ident}/brain/{slot}')
    def match_brain(ident: str, slot: int, ids: str = Query(min_length=1, max_length=8192)):
        match = replay_designs(store.match(ident) or training.gallery_match(ident) or training.bundled_replay_match(ident))
        if match is None:
            raise HTTPException(404, 'Match not found')
        if match['status'] != 'verified':
            raise HTTPException(409, 'Verified replay is not ready')
        if slot < 0 or slot >= len(match['request']['fly_ids']):
            raise HTTPException(404, 'Participant not found')
        samples = tuple(sorted(ids.split(',')))
        if len(samples) > 200 or len(set(samples)) != len(samples) or not all(samples):
            raise ValueError('Provide up to 200 distinct neuron IDs')
        participant = next((p for p in match.get('participants', []) if p['id'] == match['request']['fly_ids'][slot]), None)
        if participant is None:
            raise HTTPException(409, 'Recorded participant design is unavailable')
        snapshot = participant.get('brain_graph')
        if snapshot and snapshot['artifact_id'] == participant['artifact_id'] and snapshot['connectome_sha256'] == participant['spec']['connectome_sha256']:
            return snapshot
        if store.match(ident) is None:
            raise HTTPException(404, 'Bundled brain graph is unavailable')
        return compiled_neighborhood(participant['artifact_id'], json.dumps(participant['spec'], sort_keys=True), samples)

    @app.get("/api/v1/matches")
    def matches():
        result=store.matches()
        seen={item['id'] for item in result}
        # Public gallery assets are immutable read-only evidence.  Include
        # them when the deployment database does not contain their records so
        # a source-only deployment can still open its featured replay.
        for item in training.gallery_matches()+training.bundled_replay_matches():
            if item['id'] not in seen:
                result.append(item);seen.add(item['id'])
        return [replay_designs(match) for match in result]

    @app.post("/api/v1/matches", status_code=202)
    def match_create(body: MatchRequest, owner: dict = Depends(identity),
                     idempotency_key: str | None = Header(default=None)):
        if idempotency_key and len(idempotency_key) > 128:
            raise ValueError("Idempotency key too long")
        prior = store.prior_submission(owner["id"], idempotency_key, body.model_dump())
        if prior is not None:
            return prior
        (require_training_bridge if body.sandbox else require_bridge)(body.bridge_profile)
        return store.add_match(owner["id"], body.model_dump(),
                               digest(match_runtime(body.bridge_profile, body.sensory_profile)), key=idempotency_key)

    @app.get("/api/v1/matches/{ident}")
    def match_get(ident: str):
        result = store.match(ident) or training.gallery_match(ident) or training.bundled_replay_match(ident)
        if result is None:
            raise HTTPException(404, "Match not found")
        return replay_designs(result)

    @app.get("/api/v1/matches/{ident}/{artifact}")
    def evidence(ident: str, artifact: str):
        if artifact not in {"scene", "frames", "events", "receipt"}:
            raise HTTPException(404, "Unknown replay artifact")
        match = store.match(ident) or training.gallery_match(ident) or training.bundled_replay_match(ident)
        if match is None:
            raise HTTPException(404, "Match not found")
        if match["status"] != "verified":
            raise HTTPException(409, "Verified replay is not ready")
        if store.match(ident):
            path=store.result_folder(match) / f"{artifact}.json"
        else:
            path=training.gallery_artifact(ident,artifact) or training.bundled_replay_artifact(ident,artifact)
        if path is None or not path.is_file():
            raise HTTPException(404, "Replay artifact not found")
        return FileResponse(path, media_type="application/json")

    @app.post("/api/v1/tournaments", status_code=202)
    def tournament_create(body: TournamentRequest, owner: dict = Depends(identity),
                          idempotency_key: str | None = Header(default=None)):
        if idempotency_key and len(idempotency_key) > 128:
            raise ValueError("Idempotency key too long")
        prior = store.prior_submission(owner["id"], idempotency_key, body.model_dump(), tournament=True)
        if prior is not None:
            return prior
        (require_training_bridge if body.sandbox else require_bridge)(body.bridge_profile)
        return store.add_tournament(owner["id"], body.model_dump(),
                                    digest(match_runtime(body.bridge_profile, body.sensory_profile)), idempotency_key)

    @app.get("/api/v1/tournaments")
    def tournaments():
        return store.tournaments()

    @app.get("/api/v1/tournaments/{ident}")
    def tournament_get(ident: str):
        result = store.tournament(ident)
        if result is None:
            raise HTTPException(404, "Tournament not found")
        return result

    @app.get("/api/v1/leaderboard")
    def leaderboard(runtime_hash: str | None = None, scenario_id: str | None = None,
                    mode: str | None = None, season_id: str = 'genesis-alpha', bridge_profile: str | None = None):
        return store.leaderboard(runtime_hash=runtime_hash,scenario_id=scenario_id,mode=mode,season_id=season_id,bridge_profile=bridge_profile)

    @app.get("/api/v1/preview")
    def preview():
        path = VAR / "preview.json"
        if not path.exists():
            from .body import Bodies
            scene = scenario("orchard", 42)
            scene["spawns"] = [[0, 0, 0]]
            b = Bodies(scene, 1, 42)
            model = b.rendering_manifest()
            for _ in range(1000):
                b.step(np.zeros((1, 2)))
            write_json(path, {"body": model, "frame": b.snapshot(),
                              "kind": "anatomical-preview", "neural_simulation": False})
        return FileResponse(path, media_type="application/json")

    @app.get("/api/v1/connectome/annotations")
    def annotations(field: str, q: str = "", limit: int = 50):
        return compiler().annotations(field, q, limit)

    @app.get('/api/v1/connectome/anatomy')
    @lru_cache(maxsize=1)
    def anatomy():
        from .anatomy import build_anatomy
        return build_anatomy(DATA / 'connectome')

    @app.get("/api/v1/connectome/neurons")
    def neurons(circuit: str = "descending", limit: int = 80, ids: str = ""):
        g = compiler().graph
        if circuit not in g.groups or limit < 1 or limit > 200:
            raise ValueError("Invalid circuit or limit")
        meta = json.loads((g.path / "neurons.json").read_text())
        if ids:
            requested = [value for value in ids.split(",") if value]
            if len(requested) > 200 or len(set(requested)) != len(requested):
                raise ValueError("Invalid neuron ID sample")
            by_id = {str(ident): index for index, ident in enumerate(g.ids)}
            group = set(int(index) for index in g.groups[circuit])
            # A replay sample contains nodes from every circuit.  Select the
            # intersection for this circuit; the remaining IDs belong to the
            # other tabs and must not make an otherwise valid replay fail.
            indices = np.asarray([by_id[value] for value in requested
                                  if value in by_id and by_id[value] in group], dtype=np.int32)
            if not len(indices):
                indices = g.groups[circuit][:limit]
        else:
            indices = g.groups[circuit][:limit]
        chosen = {int(i) for i in indices}
        edges = []
        for i in indices:
            for e in range(g.indptr[i], g.indptr[i+1]):
                if int(g.post[e]) in chosen:
                    edges.append({"pre": str(g.ids[i]), "post": str(g.ids[g.post[e]]), "count": int(g.counts[e]), "edge": e})
        return {"neurons": [meta[i] for i in indices], "edges": edges[:1000], "scope": "display sample; full graph runs in simulation"}

    dist = ROOT / "web/dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")
    return app
