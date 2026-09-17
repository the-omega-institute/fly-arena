"""Versioned, observation-only replay policy.

The policy changes recording cadence only; simulation and event clocks remain
bound to the frozen scenario rules.
"""
from __future__ import annotations

LEGACY_RECEIPTS = {"run-receipt/v1", "run-receipt/v2"}
REPLAY_RECEIPT = "run-receipt/v3"
POLICY = {
    "id": "pose-100hz-events-20hz-v1",
    "physics_dt": 0.0001,
    "pose_ticks": 100,
    "event_ticks": 500,
    "terminal": "initial-and-unique-final",
}

def policy_metadata() -> dict:
    return dict(POLICY)

def validate_policy(value: object, rules: dict) -> None:
    if (type(value) is not dict or value.keys() != POLICY.keys() or
            any(type(value[k]) is not type(v) or value[k] != v for k, v in POLICY.items())):
        raise ValueError("Unsupported or conflicting replay policy")
    if (type(rules.get("physics_dt")) is not float or
            type(rules.get("snapshot_ticks")) is not int or
            value["physics_dt"] != rules["physics_dt"] or value["event_ticks"] != rules["snapshot_ticks"]):
        raise ValueError("Replay policy is incompatible with frozen scenario rules")
