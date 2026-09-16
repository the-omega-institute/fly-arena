"""Explicit bridge admission. Unqualified engineering transfers fail closed."""
from .common import DATA, ROOT
from .experiments.probes import profile_manifest
from .experiments.qualification import verify_qualification

QUALIFICATION = ROOT / "var/research-validation/qualification-v4/final/qualification.json"


def match_profiles(data=DATA):
    profile = profile_manifest(data)
    ready = False
    reason = profile.get("reason", "Motor transfer awaits source-bound closed-loop qualification")
    try:
        evidence = verify_qualification(QUALIFICATION, profile)
        if not all(value is True for value in evidence["checks"].values()):
            raise ValueError("Motor qualification gates failed")
        ready = bool(profile["ready"])
    except (OSError, ValueError, KeyError) as error:
        reason = str(error)
    return [{"id": "legacy-v1", "name": "Legacy v1 bridge", "ready": True},
            {"id": "sensorimotor-research-v2", "name": "Research v2 neural bridge",
             "ready": ready, **({} if ready else {"reason": reason})}]


def require_bridge(bridge_profile, data=DATA):
    if bridge_profile == "legacy-v1":
        return
    selected = next((p for p in match_profiles(data) if p["id"] == bridge_profile), None)
    if not selected or not selected["ready"]:
        raise ValueError(f"Bridge unavailable: {selected.get('reason') if selected else bridge_profile}")
