"""Compatible training assets and competition qualification are separate policies."""
from .common import DATA, ROOT
from .experiments.probes import profile_manifest
from .experiments.qualification import verify_qualification

QUALIFICATION = ROOT / "var/research-validation/qualification-v4/final/qualification.json"


def training_profiles(data=DATA):
    """Training can evaluate compatible assets without claiming task qualification.

    Training evaluations are already excluded from the public leaderboard by
    Store.leaderboard. Match/tournament admission remains a separate policy.
    """
    from .experiments.embodied_sensor import catalog
    from .models import PROFILES
    profile = profile_manifest(data)
    return [
        {"id": "legacy-v1", "name": "Linear readout + filtered drive", "ready": True,
         "models": list(PROFILES), "sensory_profiles": [p["id"] for p in catalog()],
         "scope": "training"},
        {"id": "sensorimotor-research-v2", "name": "Kernel readout + motor transfer",
         "ready": bool(profile["ready"]), "models": ["malecns-lif-cpu-v1"],
         "sensory_profiles": ["odor-only-v1"], "scope": "training",
         **({} if profile["ready"] else {"reason": profile.get("reason", "Readout unavailable")})},
    ]


def require_training_bridge(bridge_profile, data=DATA):
    if bridge_profile == "legacy-v1":
        return
    selected = next((p for p in training_profiles(data) if p["id"] == bridge_profile), None)
    if not selected or not selected["ready"]:
        raise ValueError(f"Training bridge unavailable: {selected.get('reason') if selected else bridge_profile}")


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
