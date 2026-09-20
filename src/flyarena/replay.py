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

LONG_POLICY = {**POLICY, "id": "pose-20hz-events-20hz-v1", "pose_ticks": 500}
POLICIES = [POLICY, LONG_POLICY]

def recording_policy(duration_seconds: int) -> dict:
    return dict(LONG_POLICY if duration_seconds > 30 else POLICY)

def policy_metadata() -> dict:
    return dict(POLICY)

def validate_policy(value: object, rules: dict) -> None:
    if not any(type(value) is dict and value.keys() == policy.keys() and
               all(type(value[k]) is type(v) and value[k] == v for k, v in policy.items())
               for policy in POLICIES):
        raise ValueError("Unsupported or conflicting replay policy")
    if (type(rules.get("physics_dt")) is not float or
            type(rules.get("snapshot_ticks")) is not int or
            value["physics_dt"] != rules["physics_dt"] or value["event_ticks"] != rules["snapshot_ticks"]):
        raise ValueError("Replay policy is incompatible with frozen scenario rules")
