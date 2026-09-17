"""Opt-in chrono-bucket transport pinned to 4087662e; no implicit network calls."""
from __future__ import annotations
import hashlib
from urllib.parse import quote, urlsplit
from ..services.ports import Capability
from ..storage.local import validate_digest


class ChronoBucketRepository:
    def __init__(self, base_url: str, bucket: str, transport=None, *, enabled=False):
        url = urlsplit(base_url)
        if url.scheme != 'https' or not url.netloc or url.username or url.password or url.query or url.fragment:
            raise ValueError('Chrono bucket requires an HTTPS service URL')
        if not bucket or '/' in bucket:
            raise ValueError('Invalid bucket')
        self.url = base_url.rstrip('/')+'/buckets/'+quote(bucket,safe='')+'/objects'
        self.transport, self.enabled = transport, enabled

    def descriptor(self):
        available = self.enabled and self.transport is not None
        return Capability('chrono-bucket/4087662e',available,('fenced-whole-artifact-transfer',) if available else (),
                          None if available else 'External transport disabled')

    def _ready(self):
        if not self.descriptor().available:
            raise RuntimeError('Chrono bucket adapter unavailable')

    def put_if_absent(self, content: bytes, sha256: str | None = None) -> str:
        self._ready()
        actual = hashlib.sha256(content).hexdigest()
        if not content or (sha256 is not None and actual != validate_digest(sha256)):
            raise ValueError('Empty content or digest mismatch')
        # Immutable content keys always have generation one. Never recreate tombstones.
        response = self.transport.post(self.url,params={'key':actual,'contentType':'application/octet-stream',
            'mutationGeneration':1,'contentSha256':actual},content=content)
        response.raise_for_status()
        payload = response.json()
        if (payload.get('error') is not None or not isinstance(payload.get('data'),dict) or
                payload['data'].get('generation') != 1):
            raise ValueError('Malformed fenced upload response')
        # Confirm exact bytes through authenticated raw download, never a returned arbitrary URL.
        if self.get_verified(actual) != content:
            raise ValueError('Upload verification mismatch')
        return actual

    def get_verified(self, sha256: str) -> bytes:
        self._ready(); validate_digest(sha256)
        response = self.transport.get(self.url+'/download',params={'key':sha256})
        response.raise_for_status()
        if hashlib.sha256(response.content).hexdigest() != sha256:
            raise ValueError('Downloaded artifact digest mismatch')
        return response.content
