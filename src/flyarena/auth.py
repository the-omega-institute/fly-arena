"""Optional NyxID OIDC boundary. No provider calls occur until login is requested."""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
import os
import secrets
import time
import uuid
from urllib.parse import quote, urlencode, urlsplit

import httpx
import jwt
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from .store import Store
from .services.ports import IdentityProvider

SESSION_COOKIE = '__Host-arena_session'
FLOW_COOKIE = '__Host-arena_login'
CALLBACK = '/api/v1/auth/nyxid/callback'


def hashed(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def challenge(value: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(value.encode()).digest()).rstrip(b'=').decode()


@dataclass(frozen=True)
class AuthConfig:
    mode: str = 'local'
    base_url: str = ''
    issuer: str = ''
    client_id: str = ''
    client_secret: str = ''
    origin: str = ''
    session_seconds: int = 30 * 86400

    @classmethod
    def from_env(cls):
        return cls(mode=os.getenv('ARENA_AUTH_MODE', 'local'),
                   base_url=os.getenv('ARENA_NYXID_BASE_URL', '').rstrip('/'),
                   issuer=os.getenv('ARENA_NYXID_ISSUER', ''),
                   client_id=os.getenv('ARENA_NYXID_CLIENT_ID', ''),
                   client_secret=os.getenv('ARENA_NYXID_CLIENT_SECRET', ''),
                   origin=os.getenv('ARENA_PUBLIC_ORIGIN', '').rstrip('/'))

    def __post_init__(self):
        if self.mode not in {'local', 'nyxid'}:
            raise ValueError('ARENA_AUTH_MODE must be local or nyxid')
        if self.mode == 'nyxid':
            if not all([self.base_url, self.issuer, self.client_id, self.client_secret, self.origin]):
                raise ValueError('NyxID mode requires base URL, issuer, client ID, client secret and Arena origin')
            self.safe_url(self.base_url)
            self.safe_url(self.origin, loopback=True)
            if urlsplit(self.origin).path:
                raise ValueError('Arena public origin must not include a path')
        if not 60 <= self.session_seconds <= 30 * 86400:
            raise ValueError('Session duration must be between 60 seconds and 30 days')

    @staticmethod
    def safe_url(value: str, loopback: bool = False):
        u = urlsplit(value)
        allowed_http = loopback and u.scheme == 'http' and u.hostname in {'localhost', '127.0.0.1', '::1'}
        if not u.netloc or u.username or u.password or u.query or u.fragment or (u.scheme != 'https' and not allowed_http):
            raise ValueError('Authentication URLs must use HTTPS (Arena loopback may use HTTP)')

    @property
    def callback(self):
        return self.origin + CALLBACK

    @property
    def secure(self):
        return self.origin.startswith('https://')

    @property
    def session_cookie(self):
        return SESSION_COOKIE if self.secure else 'arena_session'

    @property
    def flow_cookie(self):
        return FLOW_COOKIE if self.secure else 'arena_login'


class NyxIDClient:
    def close(self):
        self.http.close()

    def __init__(self, config: AuthConfig, http: httpx.Client | None = None):
        self.config = config
        self.http = http or httpx.Client(timeout=10, follow_redirects=False)
        self.cached_metadata = None
        self.metadata_until = 0.0

    def metadata(self):
        if self.cached_metadata is not None and time.time() < self.metadata_until:
            return self.cached_metadata
        m = self.http.get(self.config.base_url + '/.well-known/openid-configuration').raise_for_status().json()
        if m.get('issuer') != self.config.issuer:
            raise ValueError('NyxID discovery issuer mismatch')
        for key in ['authorization_endpoint', 'token_endpoint', 'jwks_uri']:
            AuthConfig.safe_url(m[key])
        if ('RS256' not in m.get('id_token_signing_alg_values_supported', []) or
            'S256' not in m.get('code_challenge_methods_supported', []) or
            not {'client_secret_basic', 'client_secret_post'}.intersection(m.get('token_endpoint_auth_methods_supported', []))):
            raise ValueError('NyxID discovery lacks the required OIDC profile')
        self.cached_metadata, self.metadata_until = m, time.time() + 300
        return m

    def authorization_url(self, flow: dict):
        return self.metadata()['authorization_endpoint'] + '?' + urlencode({
            'client_id': self.config.client_id, 'redirect_uri': self.config.callback,
            'response_type': 'code', 'scope': 'openid profile', 'state': flow['state'],
            'nonce': flow['nonce'], 'code_challenge': challenge(flow['verifier']),
            'code_challenge_method': 'S256',
            # Omit prompt=consent/login: NyxID may reuse its session and prior grant.
        })

    def exchange(self, code: str, flow: dict):
        m = self.metadata()
        data = {'grant_type': 'authorization_code', 'code': code,
                'redirect_uri': self.config.callback, 'code_verifier': flow['verifier']}
        # NyxID's authorization-code endpoint currently reads credentials from
        # the form even when discovery also advertises Basic. Use its advertised
        # POST method; retain Basic for providers that only advertise Basic.
        auth = None
        if 'client_secret_post' in m['token_endpoint_auth_methods_supported']:
            data.update(client_id=self.config.client_id, client_secret=self.config.client_secret)
        else:
            auth = (quote(self.config.client_id, safe=''), quote(self.config.client_secret, safe=''))
        tokens = self.http.post(m['token_endpoint'], auth=auth, data=data).raise_for_status().json()
        token = tokens['id_token']
        header = jwt.get_unverified_header(token)
        if header.get('alg') != 'RS256' or not header.get('kid'):
            raise ValueError('Unsupported ID token signature')
        keys = self.http.get(m['jwks_uri']).raise_for_status().json()['keys']
        keys = [k for k in keys if k.get('kid') == header['kid'] and k.get('kty') == 'RSA'
                and k.get('use', 'sig') == 'sig' and k.get('alg', 'RS256') == 'RS256']
        if len(keys) != 1:
            raise ValueError('No unambiguous ID token signing key')
        claims = jwt.decode(token, jwt.PyJWK.from_dict(keys[0], algorithm='RS256').key,
            algorithms=['RS256'], audience=self.config.client_id, issuer=self.config.issuer,
            options={'require': ['iss', 'sub', 'aud', 'exp', 'iat', 'nonce']}, leeway=30)
        if not isinstance(claims['sub'], str) or not claims['sub'] or len(claims['sub']) > 512:
            raise ValueError('Invalid OIDC subject')
        if not isinstance(claims['nonce'], str) or not secrets.compare_digest(claims['nonce'], flow['nonce']):
            raise ValueError('OIDC nonce mismatch')
        if ('azp' in claims and claims['azp'] != self.config.client_id) or (
            isinstance(claims['aud'], list) and len(claims['aud']) > 1 and claims.get('azp') != self.config.client_id):
            raise ValueError('ID token authorized party mismatch')
        if 'at_hash' in claims:
            access = tokens.get('access_token', '')
            expected = base64.urlsafe_b64encode(hashlib.sha256(access.encode()).digest()[:16]).rstrip(b'=').decode()
            if not isinstance(claims['at_hash'], str) or not secrets.compare_digest(claims['at_hash'], expected):
                raise ValueError('ID token access hash mismatch')
        # Provider access/refresh/ID tokens are discarded, never sent to JS or persisted.
        return claims


class AuthBoundary:
    def __init__(self, store: Store, config: AuthConfig, provider: IdentityProvider | None = None):
        self.store, self.config = store, config
        self.provider = provider or NyxIDClient(config)
        with store.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS external_identities(issuer TEXT NOT NULL,subject TEXT NOT NULL,owner TEXT NOT NULL,PRIMARY KEY(issuer,subject));
            CREATE TABLE IF NOT EXISTS browser_sessions(hash TEXT PRIMARY KEY,owner TEXT NOT NULL,csrf TEXT NOT NULL,expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS login_flows(hash TEXT PRIMARY KEY,browser_hash TEXT NOT NULL,payload TEXT NOT NULL,expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS agent_tokens(id TEXT PRIMARY KEY,owner TEXT NOT NULL,hash TEXT UNIQUE NOT NULL,expires REAL NOT NULL,created REAL NOT NULL);
            ''')

    def session(self, request: Request):
        if self.config.mode != 'nyxid':
            return None
        with self.store.db() as db:
            row = db.execute('SELECT s.owner AS id,i.name,s.csrf,s.expires FROM browser_sessions s JOIN identities i ON s.owner=i.id WHERE s.hash=? AND s.expires>?',
                             (hashed(request.cookies.get(self.config.session_cookie, '')), time.time())).fetchone()
        return dict(row) if row else None

    def require_session(self, request: Request):
        s = self.session(request)
        if not s:
            raise HTTPException(401, 'Sign in to Fly Arena')
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            if request.headers.get('origin') != self.config.origin or not secrets.compare_digest(request.headers.get('x-arena-csrf', ''), s['csrf']):
                raise HTTPException(403, 'Invalid session request origin or CSRF token')
        return s

    def identity(self, request: Request):
        authorization = request.headers.get('authorization')
        if authorization is not None:
            token = authorization[7:] if authorization.startswith('Bearer ') else ''
            with self.store.db() as db:
                row = db.execute('SELECT i.id,i.name FROM agent_tokens t JOIN identities i ON t.owner=i.id WHERE t.hash=? AND t.expires>?', (hashed(token), time.time())).fetchone()
            result = dict(row) if row else self.store.authenticate(token) if self.config.mode == 'local' else None
            if result is None:
                raise HTTPException(401, 'Invalid Arena agent token')
            return result
        s = self.require_session(request)
        return {'id': s['id'], 'name': s['name']}

    def consume_flow(self, state: str, binding: str):
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM login_flows WHERE hash=?', (hashed(state),)).fetchone()
            if not row or row['expires'] <= time.time() or not secrets.compare_digest(row['browser_hash'], hashed(binding)):
                raise ValueError('Login state is missing, expired or belongs to another browser')
            db.execute('DELETE FROM login_flows WHERE hash=?', (hashed(state),))
        return json.loads(row['payload'])

    def new_session(self, claims: dict):
        now = time.time()
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT owner FROM external_identities WHERE issuer=? AND subject=?', (self.config.issuer, claims['sub'])).fetchone()
            name = str(claims.get('name') or 'NyxID Designer').strip()[:48] or 'NyxID Designer'
            if row:
                owner = row['owner']
                db.execute('UPDATE identities SET name=? WHERE id=?', (name, owner))
            else:
                owner = uuid.uuid4().hex
                # Never link by display name/email. An unreachable legacy token hash
                # reserves the existing identity row without creating a browser API key.
                db.execute('INSERT INTO identities VALUES(?,?,?,?)', (owner, name, hashed(secrets.token_urlsafe(32)), now))
                db.execute('INSERT INTO external_identities VALUES(?,?,?)', (self.config.issuer, claims['sub'], owner))
            token = secrets.token_urlsafe(32)
            db.execute('DELETE FROM browser_sessions WHERE expires<=?', (now,))
            db.execute('INSERT INTO browser_sessions VALUES(?,?,?,?)', (hashed(token), owner, secrets.token_urlsafe(32), now + self.config.session_seconds))
        return token

    def router(self):
        router = APIRouter(prefix='/api/v1/auth', tags=['Authentication'])

        @router.get('/config')
        def config():
            return {'mode': self.config.mode, 'nyxid_enabled': self.config.mode == 'nyxid',
                    'login_url': '/api/v1/auth/nyxid/start' if self.config.mode == 'nyxid' else None,
                    'local_registration_enabled': self.config.mode == 'local'}

        @router.get('/session')
        def session(request: Request):
            s = self.session(request)
            return {'authenticated': bool(s), 'user': {'id': s['id'], 'name': s['name']} if s else None,
                    'csrf_token': s['csrf'] if s else None, 'expires_at': s['expires'] if s else None}

        @router.get('/nyxid/start')
        def start():
            if self.config.mode != 'nyxid':
                raise HTTPException(503, 'NyxID login is not configured')
            flow = {k: secrets.token_urlsafe(32) for k in ['state', 'nonce', 'verifier', 'binding']}
            try:
                url = self.provider.authorization_url(flow)
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                raise HTTPException(503, 'NyxID is temporarily unavailable') from None
            binding = flow.pop('binding')
            now = time.time()
            with self.store.db() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('DELETE FROM login_flows WHERE expires<=?', (now,))
                if db.execute('SELECT count(*) FROM login_flows').fetchone()[0] >= 1000:
                    raise HTTPException(429, 'Too many pending sign-ins')
                db.execute('INSERT INTO login_flows VALUES(?,?,?,?)', (hashed(flow['state']), hashed(binding), json.dumps(flow), now + 600))
            response = RedirectResponse(url, status_code=302)
            response.set_cookie(self.config.flow_cookie, binding, max_age=600, httponly=True, secure=self.config.secure, samesite='lax', path='/')
            return response

        @router.get('/nyxid/callback')
        def callback(request: Request, state: str = '', code: str = '', error: str = ''):
            if self.config.mode != 'nyxid':
                raise HTTPException(503, 'NyxID login is not configured')
            try:
                flow = self.consume_flow(state, request.cookies.get(self.config.flow_cookie, ''))
                if error or not code or len(code) > 4096:
                    raise ValueError('Authorization was not completed')
                claims = self.provider.exchange(code, flow)
                token = self.new_session(claims)
            except (httpx.HTTPError, jwt.PyJWTError, ValueError, KeyError, TypeError):
                response = RedirectResponse('/?auth_error=sign_in_failed', status_code=303)
            else:
                response = RedirectResponse('/', status_code=303)
                response.set_cookie(self.config.session_cookie, token, max_age=self.config.session_seconds, httponly=True, secure=self.config.secure, samesite='lax', path='/')
            response.delete_cookie(self.config.flow_cookie, path='/', secure=self.config.secure, httponly=True, samesite='lax')
            return response

        @router.post('/logout')
        def logout(request: Request):
            self.require_session(request)
            with self.store.db() as db:
                db.execute('DELETE FROM browser_sessions WHERE hash=?', (hashed(request.cookies.get(self.config.session_cookie, '')),))
            response = JSONResponse({'logged_out': True})
            response.delete_cookie(self.config.session_cookie, secure=self.config.secure, httponly=True, samesite='lax', path='/')
            return response

        @router.post('/agent-tokens', status_code=201)
        def create_token(request: Request):
            s = self.require_session(request)
            token, ident, now = secrets.token_urlsafe(32), uuid.uuid4().hex, time.time()
            with self.store.db() as db:
                db.execute('BEGIN IMMEDIATE')
                if db.execute('SELECT count(*) FROM agent_tokens WHERE owner=? AND expires>?', (s['id'], now)).fetchone()[0] >= 10:
                    raise HTTPException(429, 'At most 10 active agent tokens per designer')
                db.execute('INSERT INTO agent_tokens VALUES(?,?,?,?,?)', (ident, s['id'], hashed(token), now + 30 * 86400, now))
            return {'id': ident, 'token': token, 'expires_at': now + 30 * 86400}

        @router.get('/agent-tokens')
        def tokens(request: Request):
            s = self.require_session(request)
            with self.store.db() as db:
                return [dict(row) for row in db.execute('SELECT id,expires,created FROM agent_tokens WHERE owner=? AND expires>? ORDER BY created DESC', (s['id'], time.time()))]

        @router.delete('/agent-tokens/{ident}')
        def revoke(ident: str, request: Request):
            s = self.require_session(request)
            with self.store.db() as db:
                db.execute('DELETE FROM agent_tokens WHERE id=? AND owner=?', (ident, s['id']))
            return {'revoked': True}

        return router
