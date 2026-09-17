"""Provider-independent research contracts and same-condition comparisons."""
from __future__ import annotations

from typing import Literal
import math
import numpy as np
from pydantic import Field, StrictInt, model_validator
from .common import digest
from .contracts import StrictModel, InterventionSpec


class BackendProfile(StrictModel):
    id: str
    backend_id: str
    model_id: str
    sensor_id: str
    readout_id: str
    motor_id: str | None = None
    protocol_id: str | None = None
    actual_backend: str | None = None
    embodiment_id: str
    ready: bool
    hashes: dict[str, str]
    capabilities: list[str] | dict[str, bool | str]
    limitations: list[str] = Field(default_factory=list)
    unavailable: list[str] = Field(default_factory=list)
    quality_gates: dict[str, bool] = Field(default_factory=dict)
    reason: str | None = None


class ScenarioSpec(StrictModel):
    schema_version: Literal['scenario/v1'] = 'scenario/v1'
    geometry_id: str
    stimulus_id: str
    task_id: str
    probe_id: str
    seed: int = Field(ge=0, le=2**31-1)


class ExperimentSpec(StrictModel):
    fly_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    probe_id: str = Field(default='gradient-v2', min_length=1, max_length=80)
    seeds: list[StrictInt] = Field(default_factory=lambda: [42], min_length=1, max_length=8)
    duration_seconds: int = Field(default=3, ge=1, le=30, strict=True)

    @model_validator(mode='after')
    def distinct_seeds(self):
        if len(set(self.seeds)) != len(self.seeds) or any(type(s) is not int or s < 0 or s > 2**31-1 for s in self.seeds):
            raise ValueError('Seeds must be distinct nonnegative int32 values')
        return self


class ConditionSpec(StrictModel):
    """Full frozen conditions; deliberately contains no subject or provenance."""
    schema_version: Literal['condition/v1'] = 'condition/v1'
    probe: dict
    profile: dict
    runtime: dict
    scene: dict
    seed: int = Field(ge=0, le=2**31-1)
    duration_seconds: int = Field(ge=1, le=30)


def condition_key(condition: ConditionSpec) -> str:
    return digest(condition.model_dump(mode='json'))


def scientific_conditions(condition: ConditionSpec) -> dict:
    return {'profile':condition.profile,'runtime':condition.runtime,'scene':condition.scene,
            'seed':condition.seed,'duration_seconds':condition.duration_seconds,'probe_id':condition.probe['id'],
            'ablation':None,'stimulus':'normal','decoder_version':'v2'}


def run_key(condition: ConditionSpec | str, artifact_id: str) -> str:
    if len(artifact_id) != 64 or any(c not in '0123456789abcdef' for c in artifact_id):
        raise ValueError('Invalid artifact digest')
    key = condition_key(condition) if isinstance(condition, ConditionSpec) else condition
    if len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
        raise ValueError('Invalid condition digest')
    return digest({'condition_key': key,
                   'artifact_id': artifact_id})


class TrajectoryPoint(StrictModel):
    time: float = Field(ge=0)
    x: float
    y: float
    yaw: float


class SceneObstacle(StrictModel):
    position: list[float] = Field(min_length=3, max_length=3)
    size: list[float] = Field(min_length=3, max_length=3)


class SceneFood(StrictModel):
    id: str
    position: list[float] = Field(min_length=3, max_length=3)
    initial: float = Field(ge=0)


class ProbeScene(StrictModel):
    id: str
    size: float = Field(gt=0)
    spawns: list[list[float]]
    obstacles: list[SceneObstacle]
    food: list[SceneFood] = Field(min_length=1)
    mirror: Literal[-1, 1]
    odor_sigma_xy_mm: list[float] | None = Field(default=None, min_length=2, max_length=2)
    chemical_policy: str
    cue_on_seconds: float = Field(ge=0)
    cue_off_seconds: float | None

    @model_validator(mode='after')
    def valid_geometry(self):
        if self.odor_sigma_xy_mm is not None and min(self.odor_sigma_xy_mm) <= 0:
            raise ValueError('Chemical spread must be positive')
        if not self.spawns or any(len(s) != 3 or not all(math.isfinite(x) for x in s) for s in self.spawns):
            raise ValueError('Scene requires finite x/y/yaw spawns')
        if len({f.id for f in self.food}) != len(self.food) or any(min(o.size) <= 0 for o in self.obstacles):
            raise ValueError('Invalid scene food identities or obstacle size')
        return self


class PhenotypeReport(StrictModel):
    schema_version: Literal['probe-report/v2']
    fly_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    artifact_id: str = Field(pattern=r'^[0-9a-f]{64}$')
    condition_key: str = Field(pattern=r'^[0-9a-f]{64}$')
    probe_id: str
    seed: int = Field(ge=0, le=2**31-1)
    duration_seconds: int = Field(ge=1, le=30)
    status: Literal['complete', 'partial', 'failed', 'error']
    trajectory: list[TrajectoryPoint]
    metrics: dict[str, float | None]
    neural_trace: list[dict[str, float | None]]
    receipt_sha256: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    profile: dict
    scene: ProbeScene
    frames: list | dict | None = None
    error: str | None = None

    @model_validator(mode='after')
    def time_order(self):
        times = [p.time for p in self.trajectory]
        if any(b <= a for a, b in zip(times, times[1:])):
            raise ValueError('Trajectory times must be strictly increasing')
        if times and times[-1] > self.duration_seconds + 1e-6:
            raise ValueError('Trajectory exceeds condition horizon')
        if self.status == 'complete' and (not self.receipt_sha256 or len(times) < 2):
            raise ValueError('Complete report requires receipt and trajectory')
        if self.status == 'complete' and (abs(times[0]) > 1e-6 or abs(times[-1]-self.duration_seconds) > 1e-6):
            raise ValueError('Complete trajectory must cover the entire condition horizon')
        BackendProfile.model_validate(self.profile)
        for point in self.neural_trace:
            if any(v is not None and not math.isfinite(v) for v in point.values()):
                raise ValueError('Nonfinite neural trace')
        return self


class PairedComparison(StrictModel):
    seed: int
    fly_id: str
    reference_fly_id: str
    deltas: dict[str, float | None]
    trajectory_divergence_mm: float | None


class ComparisonReport(StrictModel):
    schema_version: Literal['comparison/v1'] = 'comparison/v1'
    paired: list[PairedComparison]
    conditions: list[str]


class SeasonSpec(StrictModel):
    id: str
    ranking_policy: Literal['ranking/v1'] = 'ranking/v1'
    runtime_sha256: str
    scenario_id: str
    mode: Literal['forage', 'contest', 'sumo']


def compare_reports(reports: list[PhenotypeReport | dict], subjects: list[dict] | None = None) -> ComparisonReport:
    parsed = [r if isinstance(r, PhenotypeReport) else PhenotypeReport.model_validate(r) for r in reports]
    if not parsed:
        raise ValueError('Comparison requires reports')
    if any(r.status != 'complete' for r in parsed):
        raise ValueError('Comparison requires complete verified trials; partial/failed is not zero')
    ids = [s['fly_id'] for s in subjects] if subjects else list(dict.fromkeys(r.fly_id for r in parsed))
    if len(ids) != 3 or len(set(ids)) != 3:
        raise ValueError('Comparison requires independent wildtype, official and design subjects')
    paired, conditions = [], []
    for seed in sorted({r.seed for r in parsed}):
        group = [r for r in parsed if r.seed == seed]
        if len(group) != 3 or {r.fly_id for r in group} != set(ids):
            raise ValueError('Missing or duplicate subject trial')
        if len({r.condition_key for r in group}) != 1 or len({(r.probe_id, r.duration_seconds, digest(r.profile)) for r in group}) != 1:
            raise ValueError('Mismatched frozen conditions')
        conditions.append(group[0].condition_key)
        by_id = {r.fly_id: r for r in group}
        ref = by_id[ids[0]]
        times = np.array([p.time for p in ref.trajectory])
        for ident in ids[1:]:
            trial = by_id[ident]
            tt = np.array([p.time for p in trial.trajectory])
            if len(tt) != len(times) or not np.allclose(tt,times,atol=1e-10,rtol=0):
                raise ValueError('Mismatched trajectory time grids or horizons')
            grid = np.unique(np.concatenate([times, tt]))
            def xy(r):
                t = [p.time for p in r.trajectory]
                return np.column_stack([np.interp(grid, t, [getattr(p, axis) for p in r.trajectory]) for axis in ('x', 'y')])
            distances = np.linalg.norm(xy(trial)-xy(ref), axis=1)
            divergence = float(np.trapezoid(distances, grid)/(grid[-1]-grid[0]))
            deltas = {k: (trial.metrics[k]-ref.metrics[k] if trial.metrics.get(k) is not None and ref.metrics.get(k) is not None else None)
                      for k in sorted(trial.metrics.keys() | ref.metrics.keys())}
            paired.append(PairedComparison(seed=seed, fly_id=ident, reference_fly_id=ref.fly_id,
                                           deltas=deltas, trajectory_divergence_mm=divergence))
    return ComparisonReport(paired=paired, conditions=conditions)
