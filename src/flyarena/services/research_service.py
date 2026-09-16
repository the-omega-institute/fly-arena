"""Phenotype Lab use cases. HTTP queues work; isolated workers execute it."""
from __future__ import annotations
from dataclasses import asdict
import json
from pathlib import Path
import threading
from ..common import DATA, canonical, digest, file_sha
from ..research import BackendProfile, ScenarioSpec, ConditionSpec, ExperimentSpec, PhenotypeReport, compare_reports, run_key, scientific_conditions
from ..registry.platform_references import initialize_references
from ..storage.local import LocalArtifactRepository
from .experiments import ExperimentRepository
from .executor import LocalProbeExecutor
from .ports import require_capabilities


class ResearchService:
    def __init__(self, store, compiler, *, data=DATA, probes=None, executor=None):
        self.store, self.compiler, self.data = store, compiler, data
        self.repository = ExperimentRepository(store)
        self._probes = probes
        self.executor = executor or LocalProbeExecutor(data=data,var=store.root)
        self.objects = LocalArtifactRepository(store.root / 'research' / 'objects')
        self._reference_lock = threading.Lock()
        self._references = None

    @property
    def probes(self):
        if self._probes is None:
            from ..experiments import probes
            return probes
        return self._probes

    def references(self):
        with self._reference_lock:
            if self._references is None:
                self._references = initialize_references(self.store,self.compiler())
            return self._references

    def catalog(self):
        from ..integrations.descriptors import integration_descriptors
        try:
            probes = self.probes.probe_catalog()
            profile = self.probes.profile_manifest(data=self.data)
            backend = asdict(self.executor.descriptor())
        except (ImportError, FileNotFoundError) as error:
            probes, profile = [], {'id':'unavailable','ready':False,'error':str(error)}
            backend = {'id':'local-probe-process/v1','available':False,'capabilities':[], 'reason':str(error)}
        try:
            refs = self.references()
            reference_error = None
        except (ValueError,FileNotFoundError) as error:
            refs, reference_error = {'wildtype':None,'official':None}, str(error)
        return {'schema_version':'research-catalog/v1','probes':probes,'profile':profile,
                'references':refs,'reference_error':reference_error,'backends':[backend],
                'integrations':integration_descriptors()}

    def admit(self, owner, spec, key=None):
        spec = spec if isinstance(spec,ExperimentSpec) else ExperimentSpec.model_validate(spec)
        # Resolve idempotency before checking mutable availability or freezing new references.
        if key:
            with self.store.db() as db:
                old = db.execute('SELECT * FROM experiment_keys WHERE owner=? AND key=?',(owner,key)).fetchone()
            if old:
                if old['payload'] != digest(spec.model_dump()):
                    raise ValueError('Idempotency key already used for a different experiment')
                return self.repository.get(old['resource'])
        if key is not None and (not key or len(key) > 128):
            raise ValueError('Idempotency key must contain 1 to 128 characters')
        try:
            catalog = self.probes.probe_catalog()
        except (ImportError, OSError) as error:
            raise ValueError(f'Research probes unavailable: {error}') from error
        selected = next((p for p in catalog if p['id']==spec.probe_id),None)
        if selected is None:
            raise ValueError('Unknown or unavailable research probe')
        profile = self.probes.profile_manifest(data=self.data)
        BackendProfile.model_validate(profile)
        if not profile.get('ready') or not self.executor.descriptor().available:
            raise ValueError('Research scientific profile/executor unavailable; prepare before admission')
        if profile.get('hashes',{}).get('connectome', self.compiler().graph.manifest['sha256']) != self.compiler().graph.manifest['sha256']:
            raise ValueError('Research profile graph mismatch')
        for seed in spec.seeds:
            ScenarioSpec.model_validate(selected['scenario'] | {'probe_id':spec.probe_id,'seed':seed})
        require_capabilities(self.executor,('whole-trial',))
        refs = self.references()
        design = self.store.fly(spec.fly_id)
        if not design or design['owner'] != owner:
            raise ValueError('Experiment design must belong to authenticated owner')
        flies = [refs['wildtype'],refs['official'],design]
        for fly in flies:
            if fly['spec'].get('connectome_sha256') != self.compiler().graph.manifest['sha256'] or fly['spec'].get('model_profile') != 'malecns-lif-cpu-v1':
                raise ValueError('Subject graph/profile mismatch')
            self.compiler().load_weights(fly['artifact_id'],self.store.root)
        subjects = [{'role':role,'fly_id':fly['id'],'name':fly['name'],'artifact_id':fly['artifact_id']}
                    for role,fly in zip(('wildtype','official','design'),flies)]
        runtime = self.probes.runtime_closure()
        conditions = [ConditionSpec(probe=selected,profile=profile,runtime=runtime,
                      scene=self.probes.make_scene(spec.probe_id,seed),seed=seed,duration_seconds=spec.duration_seconds).model_dump() for seed in spec.seeds]
        return self.repository.admit(owner,spec.model_dump(),subjects,conditions,key)

    def schedule_saved(self, fly):
        try:
            experiment = self.admit(fly['owner'],ExperimentSpec(fly_id=fly['id']),key='auto-gradient-v2:'+fly['id'])
            self.repository.save_schedule(fly['id'],experiment['id'])
        except Exception as error:
            self.repository.save_schedule(fly['id'],error=f'{type(error).__name__}: {error}')
        return self.store.fly(fly['id'])

    def verify_report(self, report, folder):
        parsed = PhenotypeReport.model_validate(report)
        if parsed.status != 'complete':
            raise ValueError('Trial is partial or failed')
        receipt_path = folder / 'receipt.json'
        receipt = json.loads(receipt_path.read_text())
        if receipt.get('sha256') != parsed.receipt_sha256 or digest({k:v for k,v in receipt.items() if k != 'sha256'}) != parsed.receipt_sha256:
            raise ValueError('Probe receipt digest mismatch')
        files = receipt.get('files', {})
        if not isinstance(files, dict) or 'evidence.json' not in files:
            raise ValueError('Receipt must bind evidence file digests')
        for name, expected in files.items():
            path = (folder / name).resolve()
            if not path.is_relative_to(folder.resolve()) or not isinstance(expected,str) or file_sha(path) != expected:
                raise ValueError('Probe evidence digest mismatch')
        evidence = json.loads((folder/'evidence.json').read_text())
        if any(report.get(k) != v for k,v in evidence.items()):
            raise ValueError('Report disagrees with emitted evidence')
        if digest(receipt['conditions']) != parsed.condition_key or receipt['subject']['fly_id'] != parsed.fly_id or receipt['subject']['artifact_id'] != parsed.artifact_id:
            raise ValueError('Receipt condition or subject mismatch')
        if hasattr(self.probes,'verify_evidence'):
            self.probes.verify_evidence(folder,report)
        # Store a verified, immutable application envelope separately from neural artifacts.
        envelope = canonical({'report':report,'receipt_sha256':parsed.receipt_sha256,'files':files})
        self.objects.put_if_absent(envelope)
        return parsed

    def _cached(self, key, fly, condition):
        with self.store.db() as db:
            row = db.execute('SELECT * FROM reference_run_cache WHERE key=?',(key,)).fetchone()
        if not row:
            return None
        report = json.loads(row['report'])
        try:
            if report['fly_id'] != fly['id'] or report['artifact_id'] != fly['artifact_id']:
                return None
            self.verify_report(report,Path(row['folder']))
            self._validate_condition(report,condition)
            return report
        except (ValueError, OSError, KeyError):
            # Invalid cached evidence is never used; produce a new independent trial.
            return None

    @staticmethod
    def _validate_condition(report, condition):
        if (report['scene'] != condition.scene or report['condition_key'] != digest(scientific_conditions(condition)) or report['seed'] != condition.seed or report['probe_id'] != condition.probe['id'] or
            report['duration_seconds'] != condition.duration_seconds or digest(report['profile']) != digest(condition.profile)):
            raise ValueError('Report does not match admitted frozen condition')

    def execute_claim(self, claim):
        ident,lease,generation = claim
        experiment = self.repository.get(ident)
        reports = []
        try:
            require_capabilities(self.executor,('whole-trial',))
            for frozen in experiment['conditions']:
                condition = ConditionSpec.model_validate(frozen)
                current_profile = self.probes.profile_manifest(data=self.data)
                current_probe = next((p for p in self.probes.probe_catalog() if p['id']==condition.probe['id']),None)
                if (digest(current_profile) != digest(condition.profile) or current_probe != condition.probe or
                    self.probes.runtime_closure() != condition.runtime or self.probes.make_scene(condition.probe['id'],condition.seed) != condition.scene):
                    raise ValueError('Frozen scientific conditions changed after admission')
                for subject in experiment['subjects']:
                    self.repository.heartbeat(ident,lease,generation)
                    fly = self.store.fly(subject['fly_id'])
                    if not fly or fly['artifact_id'] != subject['artifact_id']:
                        raise ValueError('Frozen subject artifact changed')
                    key = run_key(condition,subject['artifact_id'])
                    cached = self._cached(key,fly,condition) if subject['role'] != 'design' else None
                    if cached is not None:
                        reports.append(cached)
                        continue
                    folder = self.store.root/'research'/'runs'/ident/str(generation)/str(condition.seed)/subject['role']
                    folder.parent.mkdir(parents=True,exist_ok=True)
                    report = self.executor.execute(fly,condition.probe['id'],condition.seed,condition.duration_seconds,folder)
                    PhenotypeReport.model_validate(report)
                    canonical(report)  # Nonfinite/unserializable worker results fail without poisoning durable status.
                    reports.append(report)
                    self.verify_report(report,folder)
                    self._validate_condition(report,condition)
                    if report['fly_id'] != fly['id'] or report['artifact_id'] != fly['artifact_id']:
                        raise ValueError('Report subject mismatch')
                    self.repository.heartbeat(ident,lease,generation)
                    if subject['role'] != 'design':
                        with self.store.db() as db:
                            db.execute('INSERT OR REPLACE INTO reference_run_cache VALUES(?,?,?)',(key,canonical(report).decode(),str(folder)))
            comparison = compare_reports(reports,experiment['subjects']).model_dump()
            self.repository.finish(ident,lease,generation,reports,comparison)
        except Exception as error:
            self.repository.finish(ident,lease,generation,reports,error=f'{type(error).__name__}: {error}')
        return self.repository.get(ident)
