"""Regenerate the committed arena geometry contract fixture from this checkout."""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
# A globally installed editable checkout can otherwise win over this worktree.
sys.path.insert(0, str(SRC))

from flyarena.common import digest  # noqa: E402
from flyarena.experiments.probes import make_scene, probe_catalog  # noqa: E402
from flyarena.scenarios import MAPS, arena_scene, scenario  # noqa: E402


SEEDS = (42, 91)
PROBE_SEEDS = (42, 43)
INVALID_OBSTACLES = [{"position": [0, 0, 0], "size": [1, 1, 1], "shape": None}]


def contract_fixture() -> dict:
    maps = {
        map_id: {str(seed): scenario(map_id, seed) for seed in SEEDS}
        for map_id in sorted(MAPS)
    }
    bridge_digests = {
        profile: {
            map_id: {str(seed): arena_scene(map_id, seed, profile)["sha256"] for seed in SEEDS}
            for map_id in sorted(MAPS)
        }
        for profile in ("legacy-v1", "sensorimotor-research-v2")
    }
    probes = {
        probe["id"]: {str(seed): make_scene(probe["id"], seed) for seed in PROBE_SEEDS}
        for probe in sorted(probe_catalog(), key=lambda item: item["id"])
    }
    return {
        "invalid_obstacles": INVALID_OBSTACLES,
        "bridge_digests": bridge_digests,
        "contract": {
            "id": "arena-geometry-v1",
            "quaternion_order": "wxyz",
            "shapes": ["box", "ellipsoid"],
            "units": "mm",
            "world_axes": ["x", "y", "z-up"],
        },
        "maps": maps,
        "probe_digests": {
            probe_id: {seed: digest(scene) for seed, scene in seeds.items()}
            for probe_id, seeds in probes.items()
        },
        "probes": probes,
    }


def main() -> None:
    destination = ROOT / "tests/fixtures/geometry_contract.json"
    destination.write_text(
        json.dumps(contract_fixture(), ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
