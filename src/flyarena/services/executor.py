"""Local whole-trial adapter; scientific imports happen only when requested."""
from ..common import DATA, VAR
from .ports import Capability


class LocalProbeExecutor:
    def __init__(self, *, data=DATA, var=VAR):
        self.data, self.var = data, var

    def descriptor(self):
        from ..experiments.probes import profile_manifest
        profile = profile_manifest(data=self.data)
        return Capability('local-probe-process/v1', bool(profile['ready']), ('whole-trial', 'cpu'),
                          None if profile['ready'] else 'Scientific profile is not prepared')

    def execute(self, fly, probe_id, seed, duration_seconds, output):
        if not self.descriptor().available:
            raise ValueError('Local scientific executor unavailable; prepare the profile first')
        from ..experiments.probes import run_probe
        return run_probe(fly, probe_id, seed, duration_seconds, output, data=self.data, var=self.var)
