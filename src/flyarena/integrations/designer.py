"""Pinned external designer inputs and user-directed CMA links, never auto-launch."""
from __future__ import annotations
from urllib.parse import urlsplit
from pydantic import Field, model_validator
from ..contracts import StrictModel
from ..storage.local import validate_digest


class OrnnPackageReference(StrictModel):
    skill_id: str = Field(min_length=1,max_length=128)
    version: str = Field(pattern=r'^\d+\.\d+(?:\.\d+)?$')
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    registry_commit: str = '0041cfe1ad08517e3407eed984138e0a187ccd7e'
    sdk_package: str = 'ornn-sdk==0.7.3'

    @model_validator(mode='after')
    def pinned(self):
        if self.registry_commit != '0041cfe1ad08517e3407eed984138e0a187ccd7e' or self.sdk_package not in {'ornn-sdk==0.7.3','@chronoai/ornn-sdk@0.7.3'}:
            raise ValueError('Unreviewed Ornn alpha package pin')
        return self

    def resolve_local(self, repository):
        return repository.get_verified(self.sha256)


class CMATriggerDescriptor(StrictModel):
    public_url: str
    badge_url: str
    label_text: str
    revision: int = Field(gt=0)
    content_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')

    @model_validator(mode='after')
    def safe_urls(self):
        urls = [urlsplit(v) for v in (self.public_url,self.badge_url)]
        if any(u.scheme!='https' or not u.netloc or u.username or u.password for u in urls) or urls[0].netloc != urls[1].netloc:
            raise ValueError('CMA descriptor requires HTTPS URLs at the same origin')
        if '/api/v1/triggers/public/' not in urls[0].path or '/open/' not in urls[0].path:
            raise ValueError('CMA descriptor must point to public trigger open route')
        return self

    def launch_link(self, *, user_requested: bool):
        if not user_requested:
            raise ValueError('CMA launch requires an explicit user action')
        return self.public_url
