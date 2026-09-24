"""Pure validation for the public ``arena-geometry-v1`` scene contract.

The validators deliberately preserve the input representation.  In particular,
omitted quaternions remain omitted and existing floating point values are not
rounded or rewritten; this keeps historical scene digests stable.  A separate
normalizer is provided for consumers that need a unit quaternion.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

CONTRACT_ID = "arena-geometry-v1"
WORLD_AXES = ("x", "y", "z-up")
SHAPES = frozenset(("box", "ellipsoid"))
MATERIALS = frozenset(("leaf", "rock", "fruit"))


class GeometryError(ValueError):
    """Raised when a scene cannot be represented by the geometry contract."""


def _number(value: Any, field: str) -> float:
    # bool is an int subclass, but it is never a meaningful coordinate.
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise GeometryError(f"{field} must contain finite numbers")
    return float(value)


def _vector(value: Any, length: int, field: str) -> list[float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != length:
        raise GeometryError(f"{field} must contain exactly {length} numbers")
    return [_number(item, field) for item in value]


def normalize_quaternion_wxyz(value: Sequence[float]) -> list[float]:
    """Return a unit MuJoCo-order quaternion without changing scene payloads."""
    q = _vector(value, 4, "quaternion")
    norm = math.sqrt(sum(component * component for component in q))
    if norm <= 1e-12:
        raise GeometryError("quaternion must be non-zero")
    return [component / norm for component in q]


def validate_obstacle(value: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate and return one obstacle, retaining optional fields verbatim."""
    if not isinstance(value, Mapping):
        raise GeometryError("obstacle must be an object")
    position = _vector(value.get("position"), 3, "obstacle.position")
    size = _vector(value.get("size"), 3, "obstacle.size")
    if any(component <= 0 for component in size):
        raise GeometryError("obstacle.size must be positive")
    shape = value.get("shape", "box")
    if shape not in SHAPES:
        raise GeometryError(f"unsupported obstacle shape: {shape!r}")
    quaternion = value.get("quaternion")
    if quaternion is not None:
        normalize_quaternion_wxyz(quaternion)
    material = value.get("material")
    if material is not None and material not in MATERIALS:
        raise GeometryError(f"unsupported obstacle material: {material!r}")
    color = value.get("color")
    if color is not None and (not isinstance(color, str) or not color):
        raise GeometryError("obstacle.color must be a non-empty string")
    # Validate the required values even when callers pass numpy scalar values;
    # do not write converted values back into the returned mapping.
    _ = position, size
    return value


def normalize_obstacle(value: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate an obstacle and preserve its serialized representation.

    The no-rewrite rule is intentional: normalizing a quaternion in a scene
    payload would alter historical receipt hashes. Renderers can use
    :func:`normalize_quaternion_wxyz` when constructing a matrix.
    """
    return validate_obstacle(value)


def validate_spawn(value: Any, field: str = "spawn") -> None:
    """Validate ``[x, y, yaw]``; the third coordinate is never altitude."""
    _vector(value, 3, field)


def validate_arena_scene(scene: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate a serialized arena scene and return it unchanged."""
    if not isinstance(scene, Mapping):
        raise GeometryError("scene must be an object")
    size = _number(scene.get("size"), "scene.size")
    if size <= 0:
        raise GeometryError("scene.size must be positive")
    spawns = scene.get("spawns")
    if not isinstance(spawns, Sequence) or isinstance(spawns, (str, bytes)) or not spawns:
        raise GeometryError("scene.spawns must be a non-empty list")
    for index, spawn in enumerate(spawns):
        validate_spawn(spawn, f"scene.spawns[{index}]")
    obstacles = scene.get("obstacles")
    if not isinstance(obstacles, Sequence) or isinstance(obstacles, (str, bytes)):
        raise GeometryError("scene.obstacles must be a list")
    for obstacle in obstacles:
        validate_obstacle(obstacle)
    food = scene.get("food")
    if not isinstance(food, Sequence) or isinstance(food, (str, bytes)):
        raise GeometryError("scene.food must be a list")
    for index, item in enumerate(food):
        if not isinstance(item, Mapping):
            raise GeometryError(f"scene.food[{index}] must be an object")
        _vector(item.get("position"), 3, f"scene.food[{index}].position")
        amount = _number(item.get("initial"), f"scene.food[{index}].initial")
        if amount < 0:
            raise GeometryError(f"scene.food[{index}].initial must be non-negative")
        if not isinstance(item.get("id"), str) or not item["id"]:
            raise GeometryError(f"scene.food[{index}].id must be a non-empty string")
    return scene


def normalize_arena_scene(scene: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate and return a scene without changing its historical encoding."""
    return validate_arena_scene(scene)


def validate_probe_scene(scene: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate a research probe scene using the same world geometry rules."""
    validate_arena_scene(scene)
    if scene.get("mirror") not in (-1, 1):
        raise GeometryError("probe scene mirror must be -1 or 1")
    for key in ("chemical_policy",):
        if not isinstance(scene.get(key), str) or not scene[key]:
            raise GeometryError(f"probe scene {key} must be a non-empty string")
    _number(scene.get("cue_on_seconds"), "probe scene cue_on_seconds")
    cue_off = scene.get("cue_off_seconds")
    if cue_off is not None and _number(cue_off, "probe scene cue_off_seconds") < 0:
        raise GeometryError("probe scene cue_off_seconds must be non-negative")
    sigma = scene.get("odor_sigma_xy_mm")
    if sigma is not None and any(v <= 0 for v in _vector(sigma, 2, "odor_sigma_xy_mm")):
        raise GeometryError("odor_sigma_xy_mm must be positive")
    return scene
