from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np

from .common import VAR, digest, file_sha, write_json
from .connectome import Connectome
from .contracts import FlySpec
from .models import profile as model_profile

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

    def _metadata(self):
        if not hasattr(self, '_annotations'):
            path = self.graph.path / 'neurons.json'
            actual = file_sha(path)
            expected = self.graph.manifest.get('files', {}).get('neurons.json')
            if expected is not None and actual != expected:
                raise ValueError('Neuron metadata digest mismatch')
            rows = json.loads(path.read_text())
            if len(rows) != self.graph.n or [r['id'] for r in rows] != [str(i) for i in self.graph.ids]:
                raise ValueError('Neuron metadata does not match canonical graph order')
            self._annotations, self._metadata_sha = rows, actual
        return self._annotations

    def annotations(self, field: str, q: str = "", limit: int = 50) -> dict:
        """Discover exact values from digest-checked canonical metadata."""
        from collections import Counter
        if field not in {"class", "type", "side"} or not 1 <= limit <= 100 or len(q) > 128:
            raise ValueError("Invalid annotation field, query or limit")
        counts = Counter(r.get(field) for r in self._metadata() if isinstance(r.get(field), str) and r[field])
        values = sorted(v for v in counts if q.casefold() in v.casefold())
        return {"field": field, "items": [{"value": v, "count": counts[v]} for v in values[:limit]],
                "metadata_sha256": self._metadata_sha, "total": len(values)}

    def _select(self, selector):
        rows = self._metadata()
        mask = np.ones(self.graph.n, dtype=bool)
        for field, value in selector.model_dump(by_alias=True, exclude_none=True).items():
            if field == 'ids':
                known = {r['id'] for r in rows}
                if not set(value) <= known:
                    raise ValueError('Unknown canonical neuron ID')
                mask &= np.array([r['id'] in set(value) for r in rows])
            else:
                if value not in {r.get(field) for r in rows}:
                    raise ValueError(f'Unknown neuron {field}: {value}')
                mask &= np.array([r.get(field) == value for r in rows])
        if not mask.any():
            raise ValueError('Neuron selector resolves to an empty set')
        return mask

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
        summaries = []
        for intervention in spec.interventions:
            selected = np.ones(g.e, dtype=bool)
            for endpoint in ('pre', 'post'):
                selector = getattr(intervention.selector, endpoint)
                if selector is not None:
                    selected &= self._select(selector)[getattr(g, endpoint)]
            if not selected.any():
                raise ValueError('Intervention resolves to no structural edges')
            delta[selected] += np.log(intervention.scale)
            effective = selected & (g.baseline_weights() != 0)
            summaries.append({'selector': intervention.selector.model_dump(by_alias=True, exclude_none=True),
                'scale': intervention.scale, 'structural_edges': int(selected.sum()),
                'effective_edges': int(effective.sum()),
                'affected_neurons': int(len(np.unique(np.r_[g.pre[selected], g.post[selected]]))),
                'synaptic_contacts': int(g.counts[selected].sum()),
                'effective_synaptic_contacts': int(g.counts[effective].sum())})
        # Normalize tiny arithmetic residue so cancellation has a single identity.
        delta = np.round(delta, decimals=12)
        if np.max(delta) > np.log(2) + 1e-12 or np.min(delta) < np.log(.5) - 1e-12:
            raise ValueError("Combined mutations exceed the per-edge multiplier range [0.5, 2.0]")
        baseline = g.baseline_weights()
        structural = delta != 0
        effective = structural & (baseline != 0)
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
                     "model": model_profile(spec.model_profile), "budget": BUDGET}
        artifact_id = digest(phenotype)
        report = {"artifact_id": artifact_id, "budget_used": round(cost, 6), "budget_limit": 100,
                  "weight_points": round(weight_points, 6), "intrinsic_points": round(intrinsic_points, 6),
                  "changed_edges": int(np.count_nonzero(delta)), "neuron_count": g.n, "edge_count": g.e,
                  "min_multiplier": float(np.exp(delta.min())), "max_multiplier": float(np.exp(delta.max())),
                  "weights_sha256": weights_sha, "connectome_sha256": spec.connectome_sha256,
                  "model_profile": spec.model_profile, "lineage_semantics": "absolute-canonical-full-spec",
                  "interventions": summaries, "metadata_sha256": getattr(self, '_metadata_sha', None),
                  "structural_changed_edges": int(structural.sum()), "effective_changed_edges": int(effective.sum()),
                  "affected_neurons": int(len(np.unique(np.r_[g.pre[structural], g.post[structural]]))),
                  "effective_affected_neurons": int(len(np.unique(np.r_[g.pre[effective], g.post[effective]]))),
                  "synaptic_contacts": int(g.counts[structural].sum()),
                  "effective_synaptic_contacts": int(g.counts[effective].sum())}
        if publish:
            repository = root / 'artifacts'
            repository.mkdir(parents=True, exist_ok=True)
            folder = repository / artifact_id
            if not folder.exists():
                temporary = Path(tempfile.mkdtemp(prefix='.compile-', dir=repository))
                try:
                    # Final sparse log deltas include every overlap, including pre/post selectors.
                    indices = np.flatnonzero(delta).astype(np.int64)
                    np.savez(temporary / 'mutations.npz', resolved_edge_idx=indices, resolved_log_delta=delta[indices])
                    write_json(temporary / 'manifest.json', {'phenotype': phenotype, 'report': report,
                        'mutation_format': 'resolved-log-delta/v2',
                        'mutation_sha256': file_sha(temporary / 'mutations.npz')})
                    try:
                        os.rename(temporary, folder)
                    except OSError:
                        if not folder.exists():
                            raise
                finally:
                    if temporary.exists():
                        shutil.rmtree(temporary)
            self.load_weights(artifact_id, root)
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
        if manifest["phenotype"]["model"] != model_profile(manifest["phenotype"]["model"]["id"]) or manifest["phenotype"]["budget"] != BUDGET:
            raise ValueError("Artifact belongs to a different neural model or budget profile")
        if file_sha(folder / "mutations.npz") != manifest["mutation_sha256"]:
            raise ValueError("Mutation artifact hash mismatch")
        with np.load(folder / "mutations.npz", allow_pickle=False) as a:
            if manifest.get('mutation_format') == 'resolved-log-delta/v2':
                delta = np.zeros(self.graph.e, dtype=np.float64)
                idx, values = a['resolved_edge_idx'], a['resolved_log_delta']
                if idx.ndim != 1 or values.shape != idx.shape or len(np.unique(idx)) != len(idx) or np.any(idx < 0) or np.any(idx >= self.graph.e) or not np.isfinite(values).all():
                    raise ValueError('Invalid resolved mutations')
                delta[idx] = values
            elif manifest.get('mutation_format') is None:
                delta = a["node_delta"][self.graph.pre]
                delta[a["edge_idx"]] += a["edge_delta"]
            else:
                raise ValueError('Unsupported mutation artifact format')
        delta = np.round(delta, decimals=12)
        weights = (self.graph.baseline_weights() * np.exp(delta)).astype(np.float32)
        if hashlib.sha256(weights.tobytes()).hexdigest() != manifest["phenotype"]["weights_sha256"]:
            raise ValueError("Compiled weight hash mismatch")
        return weights, manifest
