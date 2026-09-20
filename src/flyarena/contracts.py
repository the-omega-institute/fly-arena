from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


CircuitId = Literal["olfactory", "projection", "local", "memory", "readout", "descending", "visual", "motor"]


class Mutation(StrictModel):
    selector: CircuitId
    scale: float = Field(ge=0.5, le=2.0)


class EdgeDelta(StrictModel):
    edge: int = Field(ge=0)
    log_delta: float = Field(ge=-4, le=4)


class NeuronParameters(StrictModel):
    tau_scale: float = Field(default=1.0, ge=0.8, le=1.2)
    threshold_shift_mv: float = Field(default=0.0, ge=-1, le=1)


class NeuronSelector(StrictModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, populate_by_name=True)
    class_: str | None = Field(default=None, alias="class", min_length=1, max_length=128)
    type: str | None = Field(default=None, min_length=1, max_length=128)
    side: Literal["L", "R"] | None = None
    ids: list[str] | None = Field(default=None, min_length=1, max_length=10000)

    @model_validator(mode="after")
    def nonempty(self):
        if all(v is None for v in (self.class_, self.type, self.side, self.ids)):
            raise ValueError("Empty neuron selector")
        if self.ids is not None and (len(set(self.ids)) != len(self.ids) or
                any(not i.isascii() or not i.isdigit() or str(int(i)) != i for i in self.ids)):
            raise ValueError("Neuron IDs must be distinct canonical decimal strings")
        return self


class EdgeSelector(StrictModel):
    pre: NeuronSelector | None = None
    post: NeuronSelector | None = None

    @model_validator(mode="after")
    def nonempty(self):
        if self.pre is None and self.post is None:
            raise ValueError("Empty edge selector")
        return self


class InterventionSpec(StrictModel):
    selector: EdgeSelector
    scale: float = Field(ge=.5, le=2)


class FlySpec(StrictModel):
    schema_version: Literal["flyspec/v1"] = "flyspec/v1"
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=1000)
    color: Literal["mint", "amber", "violet", "rose", "blue"] = "mint"
    parent_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    connectome_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_profile: Literal["malecns-lif-cpu-v1", "malecns-rate-cpu-v1"] = "malecns-lif-cpu-v1"
    weight_mutations: list[Mutation] = Field(default_factory=list, max_length=64)
    edge_deltas: list[EdgeDelta] = Field(default_factory=list, max_length=100_000)
    neuron_parameters: NeuronParameters = Field(default_factory=NeuronParameters)
    plasticity: Literal["none"] = "none"
    interventions: list[InterventionSpec] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def unique_edges(self):
        ids = [d.edge for d in self.edge_deltas]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate edge delta IDs are not allowed")
        if not self.name.strip():
            raise ValueError("Fly name cannot be blank")
        return self


BridgeProfile = Literal["legacy-v1", "sensorimotor-research-v2"]
SensoryProfile = Literal["odor-only-v1", "engineered-multimodal-v1", "engineered-multimodal-v2", "engineered-touch-response-v1", "engineered-contact-context-v1", "engineered-contact-support-v1", "engineered-kernel-contact-v1"]


class MatchRequest(StrictModel):
    sandbox: bool = False
    bridge_profile: BridgeProfile = "legacy-v1"
    sensory_profile: SensoryProfile = "odor-only-v1"
    fly_ids: list[str] = Field(min_length=1, max_length=2)
    map_id: Literal["orchard", "maze", "scarcity", "ring", "terrarium", "enclosure", "canopy", "switchback", "blank", "labyrinth", "duel"] = "orchard"
    mode: Literal["forage", "contest", "sumo", "duel"] = "contest"
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    duration_seconds: int = Field(default=5, ge=1, le=300)

    @model_validator(mode="after")
    def slots(self):
        from .experiments.embodied_sensor import validate_profile
        validate_profile(self.bridge_profile, self.sensory_profile)
        if any(len(i) != 32 or any(c not in "0123456789abcdef" for c in i) for i in self.fly_ids):
            raise ValueError("Invalid fly ID")
        expected = 1 if self.mode == "forage" else 2
        if len(self.fly_ids) != expected:
            raise ValueError(f"{self.mode} requires {expected} flies")
        if self.map_id in {"labyrinth", "duel"} and not self.sandbox:
            raise ValueError("Long observation tasks are experimental sandbox runs")
        if self.map_id == "labyrinth" and self.mode != "forage":
            raise ValueError("Labyrinth is a single-fly benchmark")
        if (self.mode == "duel") != (self.map_id == "duel"):
            raise ValueError("Duel mode requires the closed duel arena")
        if self.map_id == "blank" and self.mode != "forage":
            raise ValueError("Blank control is a single-fly observation")
        if self.mode == "sumo" and self.map_id != "ring":
            raise ValueError("Sumo is played on the ring map")
        return self


class CreateIdentity(StrictModel):
    name: str = Field(min_length=1, max_length=48)


class TournamentRequest(StrictModel):
    sandbox: bool = False
    bridge_profile: BridgeProfile = "legacy-v1"
    sensory_profile: SensoryProfile = "odor-only-v1"
    name: str = Field(min_length=1, max_length=80)
    fly_ids: list[str] = Field(min_length=2, max_length=8)
    map_id: Literal["orchard", "maze", "scarcity", "ring", "terrarium", "enclosure", "canopy", "switchback", "blank", "labyrinth", "duel"] = "orchard"
    mode: Literal["contest", "sumo"] = "contest"
    seeds: list[int] = Field(default_factory=lambda: [42], min_length=1, max_length=3)
    duration_seconds: int = Field(default=5, ge=1, le=30)

    @model_validator(mode="after")
    def valid_entries(self):
        if len(set(self.fly_ids)) != len(self.fly_ids):
            raise ValueError("Tournament entries must be distinct")
        if len(set(self.seeds)) != len(self.seeds) or any(s < 0 or s > 2**31 - 1 for s in self.seeds):
            raise ValueError("Seeds must be distinct nonnegative int32 values")
        MatchRequest(fly_ids=self.fly_ids[:2], map_id=self.map_id, mode=self.mode,
                     seed=self.seeds[0], duration_seconds=self.duration_seconds,
                     bridge_profile=self.bridge_profile, sensory_profile=self.sensory_profile)
        return self
