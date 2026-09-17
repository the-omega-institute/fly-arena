"""Explicitly unavailable execution adapters; no synthetic successful trials."""
from ..services.ports import Capability, require_capabilities


class UnavailableExecutor:
    def __init__(self, ident, reason):
        self.ident,self.reason = ident,reason

    def descriptor(self):
        return Capability(self.ident,False,(),self.reason)

    def execute(self,*args,**kwargs):
        raise RuntimeError(f'{self.ident} unavailable: {self.reason}')


def preflight(executor, required=()):
    return require_capabilities(executor,required)
