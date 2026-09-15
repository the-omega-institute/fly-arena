from __future__ import annotations

from contextlib import asynccontextmanager
from functools import lru_cache
import json
import os
import secrets
import threading
import time

import numpy as np
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .common import DATA, ROOT, VAR, digest, write_json
from .compiler import BUDGET, Compiler
from .connectome import Connectome
from .contracts import CreateIdentity, FlySpec, MatchRequest, TournamentRequest
from .neural import PROFILE
from .runner import runtime_manifest
from .scenarios import MAPS, RULES, scenario
from .store import Store
from .worker import Worker


def create_app(*, with_worker: bool = True) -> FastAPI:
    store = Store()
    compile_lock = threading.Lock()
    registrations: dict[str, list[float]] = {}

    @lru_cache(maxsize=1)
    def compiler():
        return Compiler(Connectome())

    @asynccontextmanager
    async def lifespan(app):
        worker = Worker(store) if with_worker else None
        if worker:
            worker.start()
        yield
        if worker:
            worker.stop()

    app = FastAPI(title="Fly Arena API", version="0.1.0", lifespan=lifespan,
                  description="Published connectome designs and trusted embodied matches. All submitted flies and match replays are public in this MVP workspace.")
    app.add_middleware(GZipMiddleware, minimum_size=1000)

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
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        return JSONResponse({"detail": str(error)}, status_code=422)

    def identity(authorization: str | None):
        token = authorization[7:] if authorization and authorization.startswith("Bearer ") else ""
        result = store.authenticate(token)
        if result is None:
            raise HTTPException(401, "Create a designer identity or provide a valid Bearer token")
        return result

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "connectome_ready": (DATA / "connectome/manifest.json").exists(),
                "readout_ready": (DATA / "connectome/readout.json").exists(), "version": "0.1.0"}

    @app.get("/api/v1/season")
    def season():
        graph = compiler().graph
        return {"id": "genesis-alpha", "name": "GENESIS / 创生季", "connectome": graph.manifest,
                "model": PROFILE, "budget": BUDGET, "rules": RULES,
                "runtime_sha256": digest(runtime_manifest()),
                "readout": json.loads((DATA / "connectome/readout.json").read_text()),
                "invite_required": bool(os.environ.get("ARENA_INVITE_CODE")),
                "privacy": "Published designs and matches are public. API tokens are private."}

    @app.post("/api/v1/identities", status_code=201)
    def register(body: CreateIdentity, request: Request, x_invite_code: str = Header(default="")):
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
    def me(authorization: str | None = Header(default=None)):
        return identity(authorization)

    @app.get("/api/v1/maps")
    def maps():
        return list(MAPS.values())

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
    def validate(spec: FlySpec, authorization: str | None = Header(default=None)):
        identity(authorization)
        with compile_lock:
            return compiler().compile(spec)

    @app.post("/api/v1/flies", status_code=201)
    def publish(spec: FlySpec, authorization: str | None = Header(default=None)):
        owner = identity(authorization)
        with compile_lock:
            report = compiler().compile(spec, publish=True)
        return store.add_fly(owner["id"], spec.model_dump(), report)

    @app.get("/api/v1/matches")
    def matches():
        return store.matches()

    @app.post("/api/v1/matches", status_code=202)
    def match_create(body: MatchRequest, authorization: str | None = Header(default=None),
                     idempotency_key: str | None = Header(default=None)):
        owner = identity(authorization)
        if idempotency_key and len(idempotency_key) > 128:
            raise ValueError("Idempotency key too long")
        return store.add_match(owner["id"], body.model_dump(), digest(runtime_manifest()), key=idempotency_key)

    @app.get("/api/v1/matches/{ident}")
    def match_get(ident: str):
        result = store.match(ident)
        if result is None:
            raise HTTPException(404, "Match not found")
        return result

    @app.get("/api/v1/matches/{ident}/{artifact}")
    def evidence(ident: str, artifact: str):
        if artifact not in {"scene", "frames", "events", "receipt"}:
            raise HTTPException(404, "Unknown replay artifact")
        match = store.match(ident)
        if match is None:
            raise HTTPException(404, "Match not found")
        if match["status"] != "verified":
            raise HTTPException(409, "Verified replay is not ready")
        return FileResponse(store.result_folder(match) / f"{artifact}.json", media_type="application/json")

    @app.post("/api/v1/tournaments", status_code=202)
    def tournament_create(body: TournamentRequest, authorization: str | None = Header(default=None),
                          idempotency_key: str | None = Header(default=None)):
        owner = identity(authorization)
        if idempotency_key and len(idempotency_key) > 128:
            raise ValueError("Idempotency key too long")
        return store.add_tournament(owner["id"], body.model_dump(), digest(runtime_manifest()), idempotency_key)

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
    def leaderboard():
        return store.leaderboard()

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

    @app.get("/api/v1/connectome/neurons")
    def neurons(circuit: str = "descending", limit: int = 80):
        g = compiler().graph
        if circuit not in g.groups or limit < 1 or limit > 200:
            raise ValueError("Invalid circuit or limit")
        meta = json.loads((g.path / "neurons.json").read_text())
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
