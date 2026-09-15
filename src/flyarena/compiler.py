from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from .common import VAR, digest, file_sha, write_json
from .connectome import Connectome
from .contracts import FlySpec
from .neural import PROFILE

BUDGET = {
    "id": "mutation-budget-v1", "points": 100.0,
    "edge_log_budget": 0.08, "multiplier_min": 0.5, "multiplier_max": 2.0,
    "cost": "mean of normalized synapse count and uniform edge cost; absolute final log delta",
    "tau_cost": "100 * abs(log(tau_scale))",
    "threshold_cost": "20 * abs(threshold_shift_mv)", "refunds": False,
}


class Compiler:
    def __init__(self, graph: Connectome):
        self.graph = graph
        self.edge_cost = .5 / graph.e + .5 * graph.counts.astype(np.float64) / graph.counts.sum()

    def compile(self, spec: FlySpec, publish: bool = False, root: Path = VAR) -> dict:
        g = self.graph
        if spec.connectome_sha256 != g.manifest["sha256"]:
            raise ValueError("Connectome version mismatch; refresh the active season")
        node_delta = np.zeros(g.n, dtype=np.float64)
        for mutation in spec.weight_mutations:
            node_delta[g.groups[mutation.selector]] += np.log(mutation.scale)
        edge_idx = np.array([d.edge for d in spec.edge_deltas], dtype=np.int64)
        edge_delta = np.array([d.log_delta for d in spec.edge_deltas], dtype=np.float64)
        if len(edge_idx) and int(edge_idx.max()) >= g.e:
            raise ValueError("Edge index is outside the canonical connectome")
        order = np.argsort(edge_idx)
        edge_idx, edge_delta = edge_idx[order], edge_delta[order]
        delta = node_delta[g.pre]
        delta[edge_idx] += edge_delta
        # Normalize tiny arithmetic residue so cancellation has a single identity.
        delta = np.round(delta, decimals=12)
        if np.max(delta) > np.log(2) + 1e-12 or np.min(delta) < np.log(.5) - 1e-12:
            raise ValueError("Combined mutations exceed the per-edge multiplier range [0.5, 2.0]")
        weight_points = float(np.sum(self.edge_cost * np.abs(delta)) / .08 * 100)
        p = spec.neuron_parameters
        intrinsic_points = 100 * abs(np.log(p.tau_scale)) + 20 * abs(p.threshold_shift_mv)
        cost = weight_points + intrinsic_points
        if cost > 100 + 1e-8:
            raise ValueError(f"Mutation budget exceeded: {cost:.2f} / 100 points")
        weights = (g.baseline_weights() * np.exp(delta)).astype(np.float32)
        weights_sha = hashlib.sha256(weights.tobytes()).hexdigest()
        phenotype = {"connectome_sha256": spec.connectome_sha256,
                     "weights_sha256": weights_sha, "neuron_parameters": p.model_dump(),
                     "model": PROFILE, "budget": BUDGET}
        artifact_id = digest(phenotype)
        report = {"artifact_id": artifact_id, "budget_used": round(cost, 6), "budget_limit": 100,
                  "weight_points": round(weight_points, 6), "intrinsic_points": round(intrinsic_points, 6),
                  "changed_edges": int(np.count_nonzero(delta)), "neuron_count": g.n, "edge_count": g.e,
                  "min_multiplier": float(np.exp(delta.min())), "max_multiplier": float(np.exp(delta.max())),
                  "weights_sha256": weights_sha, "connectome_sha256": spec.connectome_sha256}
        if publish:
            folder = root / "artifacts" / artifact_id
            folder.mkdir(parents=True, exist_ok=True)
            if not (folder / "manifest.json").exists():
                # Store the sparse/structured design, never a player executable.
                np.savez(folder / "mutations.npz", node_delta=node_delta, edge_idx=edge_idx, edge_delta=edge_delta)
                write_json(folder / "manifest.json", {"phenotype": phenotype, "report": report,
                    "mutation_sha256": file_sha(folder / "mutations.npz")})
        return report

    def load_weights(self, artifact_id: str, root: Path = VAR) -> tuple[np.ndarray, dict]:
        if len(artifact_id) != 64 or any(c not in "0123456789abcdef" for c in artifact_id):
            raise ValueError("Invalid artifact digest")
        folder = root / "artifacts" / artifact_id
        manifest = json.loads((folder / "manifest.json").read_text())
        if digest(manifest["phenotype"]) != artifact_id:
            raise ValueError("Artifact identity mismatch")
        if manifest["phenotype"]["connectome_sha256"] != self.graph.manifest["sha256"]:
            raise ValueError("Artifact belongs to a different connectome")
        if manifest["phenotype"]["model"] != PROFILE or manifest["phenotype"]["budget"] != BUDGET:
            raise ValueError("Artifact belongs to a different neural model or budget profile")
        if file_sha(folder / "mutations.npz") != manifest["mutation_sha256"]:
            raise ValueError("Mutation artifact hash mismatch")
        with np.load(folder / "mutations.npz", allow_pickle=False) as a:
            delta = a["node_delta"][self.graph.pre]
            delta[a["edge_idx"]] += a["edge_delta"]
        delta = np.round(delta, decimals=12)
        weights = (self.graph.baseline_weights() * np.exp(delta)).astype(np.float32)
        if hashlib.sha256(weights.tobytes()).hexdigest() != manifest["phenotype"]["weights_sha256"]:
            raise ValueError("Compiled weight hash mismatch")
        return weights, manifest
