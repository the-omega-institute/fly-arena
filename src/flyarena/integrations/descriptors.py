"""Honest capability discovery: no credential discovery or activation side effects."""
from dataclasses import asdict
from ..services.ports import Capability


def integration_descriptors():
    return [asdict(Capability(ident,False,(),reason)) for ident,reason in [
        ('nyxid','Optional existing OIDC adapter; no live provider configured by research integration'),
        ('chrono-bucket','Fenced storage adapter implemented; external transport disabled'),
        ('ornn','Pinned package references supported; remote skill installation unavailable'),
        ('cma','Explicit user launch descriptor supported; no published trigger configured'),
        ('heca','Outer orchestration only; integration unavailable'),
        ('aevatar','Outer orchestration only; integration unavailable'),
        ('talos','Browser operator; unavailable as a scientific simulation executor'),
        ('athena','Model-training preflight pattern only; unavailable as a neural backend'),
        ('cuda','No qualified device evidence; unavailable'),
    ]]
