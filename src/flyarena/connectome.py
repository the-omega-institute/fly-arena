"""Versioned import of the official MaleCNS v1.0 flat connectome.

The anatomical table remains untouched. Only Traced neurons are retained;
unknown/modulatory transmitter signs are zero in this explicitly simplified LIF
profile. Those edges remain in the structural arrays and provenance counts.
"""
from __future__ import annotations

import json
from pathlib import Path
import urllib.request

import numpy as np
import pyarrow as pa
import pyarrow.feather as feather

from .common import DATA, canonical, digest, file_sha, write_json

BASE_URL = "https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome/"
SOURCES = {
    "body-annotations.feather": "body-annotations-male-cns-v1.0-minconf-0.5.feather",
    "body-neurotransmitters.feather": "body-neurotransmitters-male-cns-v1.0.feather",
    "connectome-weights.feather": "connectome-weights-male-cns-v1.0-minconf-0.5.feather",
}
CIRCUITS = [
    ("olfactory", "嗅觉输入", "Olfactory receptors", "class", "olfactory", "#f5bb64"),
    ("projection", "嗅觉投射", "Antennal lobe projection", "class", "ALPN", "#f2df93"),
    ("local", "局部抑制", "Antennal lobe local", "class", "ALLN", "#bb9af7"),
    ("memory", "蘑菇体", "Kenyon cells", "class", "Kenyon_Cell", "#e99bce"),
    ("readout", "蘑菇体输出", "Mushroom body output", "class", "MBON", "#a6d3e8"),
    ("descending", "下行回路", "Descending neurons", "superclass", "descending_neuron", "#98dbc0"),
    ("visual", "视觉投射", "Visual projection", "superclass", "visual_projection", "#86b1ed"),
    ("motor", "运动回路", "Ventral nerve cord motor", "superclass", "vnc_motor", "#e8947c"),
]


def download(data: Path = DATA) -> None:
    raw = data / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    for local, remote in SOURCES.items():
        path = raw / local
        if path.exists():
            print(f"Already downloaded: {local}", flush=True)
            continue
        partial = path.with_suffix(".partial")
        print(f"Downloading {remote}", flush=True)
        urllib.request.urlretrieve(BASE_URL + remote, partial)
        partial.replace(path)


def import_connectome(data: Path = DATA) -> dict:
    raw, out = data / "raw", data / "connectome"
    out.mkdir(parents=True, exist_ok=True)
    annotations = feather.read_table(raw / "body-annotations.feather").to_pylist()
    rows = sorted((r for r in annotations if r["status"] == "Traced"), key=lambda r: r["bodyId"])
    ids = np.array([r["bodyId"] for r in rows], dtype=np.int64)
    if len(np.unique(ids)) != len(ids):
        raise ValueError("Duplicate source neuron IDs")
    n = len(ids)
    nt = feather.read_table(raw / "body-neurotransmitters.feather",
                            columns=["body", "consensus_nt", "predicted_nt_confidence"])
    nt_ids = nt["body"].to_numpy()
    nt_keep = np.isin(nt_ids, ids)
    nt_rows = nt.filter(pa.array(nt_keep)).to_pylist()
    nt_lookup = {r["body"]: r for r in nt_rows}
    signs = np.array([{"acetylcholine": 1, "gaba": -1, "glutamate": -1}.get(
        nt_lookup.get(int(i), {}).get("consensus_nt"), 0) for i in ids], dtype=np.int8)
    print(f"Retaining {n:,} Traced neurons; reading structural edges", flush=True)
    pre_parts, post_parts, weight_parts = [], [], []
    raw_edges = 0
    with pa.memory_map(str(raw / "connectome-weights.feather"), "r") as source:
        reader = pa.ipc.open_file(source)
        for bi in range(reader.num_record_batches):
            batch = reader.get_batch(bi)
            a = batch.column(0).to_numpy()
            b = batch.column(1).to_numpy()
            w = batch.column(2).to_numpy()
            raw_edges += len(a)
            ai, bj = np.searchsorted(ids, a), np.searchsorted(ids, b)
            keep = (ai < n) & (bj < n)
            keep &= ids[np.minimum(ai, n - 1)] == a
            keep &= ids[np.minimum(bj, n - 1)] == b
            if np.any(w < 0):
                raise ValueError("Negative anatomical synapse counts")
            keep &= w > 0
            pre_parts.append(ai[keep].astype(np.int32))
            post_parts.append(bj[keep].astype(np.int32))
            weight_parts.append(w[keep].astype(np.int32))
    pre, post, count = map(np.concatenate, (pre_parts, post_parts, weight_parts))
    del pre_parts, post_parts, weight_parts
    keys = pre.astype(np.int64) * n + post
    order = np.argsort(keys, kind="stable")
    keys, count = keys[order], count[order]
    # One canonical edge per ordered neuron pair, including self-connections.
    starts = np.r_[0, np.flatnonzero(np.diff(keys)) + 1]
    count = np.add.reduceat(count.astype(np.int64), starts)
    keys = keys[starts]
    pre, post = (keys // n).astype(np.int32), (keys % n).astype(np.int32)
    if int(count.max()) > np.iinfo(np.int32).max:
        raise ValueError("Synapse count exceeds int32")
    count = count.astype(np.int32)
    indptr = np.r_[0, np.cumsum(np.bincount(pre, minlength=n))].astype(np.int64)
    groups, catalog = {}, []
    for key, label, en, column, value, color in CIRCUITS:
        node_idx = np.array([i for i, r in enumerate(rows) if r.get(column) == value], dtype=np.int32)
        groups[key] = node_idx
        edge_count = int(np.sum(indptr[node_idx + 1] - indptr[node_idx]))
        catalog.append(dict(id=key, label=label, name=en, color=color,
                            neuron_count=len(node_idx), edge_count=edge_count,
                            selector={column: value, "edges": "outgoing"},
                            neuron_ids_sha256=digest(ids[node_idx].tolist())))
    side = np.array([1 if (r.get("rootSide") or r.get("somaSide")) == "L" else
                     -1 if (r.get("rootSide") or r.get("somaSide")) == "R" else 0 for r in rows], dtype=np.int8)
    for key in ["olfactory", "projection", "descending"]:
        for letter, sign in [("left", 1), ("right", -1)]:
            g = groups[key]
            groups[f"{key}_{letter}"] = g[side[g] == sign]
    arrays = {"ids": ids, "pre": pre, "post": post, "counts": count, "indptr": indptr,
              "signs": signs, "side": side}
    for name, a in arrays.items():
        np.save(out / f"{name}.npy", a, allow_pickle=False)
    np.savez(out / "groups.npz", **groups)
    # Compact metadata powers the browser's real-neuron explorer.
    metadata = [{"id": str(r["bodyId"]), "type": r["type"], "side": r.get("rootSide") or r.get("somaSide"),
                 "class": r["class"], "superclass": r["superclass"], "position": r["somaLocation"],
                 "nt": nt_lookup.get(r["bodyId"], {}).get("consensus_nt")} for r in rows]
    write_json(out / "neurons.json", metadata)
    manifest = {
        "id": "male-cns-v1.0-traced", "release": "MaleCNS v1.0", "importer": "arena-import-v1",
        "scope": "All Traced neurons; all positive-count edges between retained neurons",
        "subset": False, "neuron_count": n, "edge_count": len(post),
        "synaptic_contacts": int(count.sum()), "raw_edge_rows": raw_edges,
        "unknown_or_modulatory_neurons": int(np.sum(signs == 0)),
        "zero_effective_edges": int(np.sum(signs[pre] == 0)),
        "sign_policy": "ACh +1; GABA/Glu -1; other/unknown 0. Simplified model, not receptor-specific physiology.",
        "license": "CC-BY-4.0", "citation": "Male CNS Connectome, Berg et al., Cell (2026)",
        "source_url": "https://male-cns.janelia.org/", "circuits": catalog,
        "sources": [{"file": local, "url": BASE_URL + remote, "sha256": file_sha(raw / local)}
                    for local, remote in SOURCES.items()],
        "files": {name: file_sha(out / name) for name in sorted(
            [f"{k}.npy" for k in arrays] + ["groups.npz", "neurons.json"])},
    }
    manifest["sha256"] = digest(manifest)
    write_json(out / "manifest.json", manifest)
    print(f"Imported {n:,} neurons / {len(post):,} edges / {int(count.sum()):,} synaptic contacts", flush=True)
    return manifest


class Connectome:
    def __init__(self, data: Path = DATA, verify: bool = False):
        self.path = data / "connectome"
        self.manifest = json.loads((self.path / "manifest.json").read_text())
        check = {k: v for k, v in self.manifest.items() if k != "sha256"}
        if digest(check) != self.manifest["sha256"]:
            raise ValueError("Connectome manifest digest mismatch")
        if verify:
            for name, sha in self.manifest["files"].items():
                if file_sha(self.path / name) != sha:
                    raise ValueError(f"Connectome integrity failure: {name}")
        for name in ["ids", "pre", "post", "counts", "indptr", "signs", "side"]:
            setattr(self, name, np.load(self.path / f"{name}.npy", mmap_mode="r", allow_pickle=False))
        self.groups = dict(np.load(self.path / "groups.npz", allow_pickle=False))
        self.n, self.e = len(self.ids), len(self.post)

    def baseline_weights(self) -> np.ndarray:
        return (self.counts.astype(np.float32) * self.signs[self.pre] * np.float32(0.275))

    def edge_indices(self, selector: str) -> np.ndarray:
        if selector not in {r[0] for r in CIRCUITS}:
            raise ValueError(f"Unknown circuit {selector}")
        node_mask = np.zeros(self.n, dtype=bool)
        node_mask[self.groups[selector]] = True
        return np.flatnonzero(node_mask[self.pre])


if __name__ == "__main__":
    import_connectome()
