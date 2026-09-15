"""Offline OIDC integration: real RSA signatures and an HTTP mock provider."""
import base64
import json
import time
from urllib.parse import parse_qs, urlsplit

from cryptography.hazmat.primitives.asymmetric import rsa
import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

from flyarena.api import create_app
from flyarena.auth import AuthConfig, NyxIDClient, SESSION_COOKIE, challenge
from flyarena.store import Store


@pytest.fixture
def oidc(tmp_path):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key())) | {'kid': 'test-key', 'alg': 'RS256', 'use': 'sig'}
    config = AuthConfig(mode='nyxid',base_url='https://nyx.example',issuer='nyxid-test',client_id='arena-test',client_secret='test-only-secret',origin='https://arena.example')
    state = {'overrides':{}, 'calls':[], 'private':private}
    metadata = {'issuer':config.issuer,'authorization_endpoint':config.base_url+'/oauth/authorize','token_endpoint':config.base_url+'/oauth/token','jwks_uri':config.base_url+'/.well-known/jwks.json','id_token_signing_alg_values_supported':['RS256'],'code_challenge_methods_supported':['S256'],'token_endpoint_auth_methods_supported':['client_secret_basic']}
    def respond(request):
        state['calls'].append(request.url.path)
        if request.url.path=='/.well-known/openid-configuration': return httpx.Response(200,json=metadata)
        if request.url.path=='/.well-known/jwks.json': return httpx.Response(200,json={'keys':[jwk]})
        if request.url.path=='/oauth/token':
            body=parse_qs(request.content.decode())
            assert body['redirect_uri']==[config.callback]
            assert challenge(body['code_verifier'][0])==state['authorization']['code_challenge'][0]
            assert request.headers['Authorization']=='Basic '+base64.b64encode(b'arena-test:test-only-secret').decode()
            claims={'iss':config.issuer,'sub':'user-1','aud':config.client_id,'iat':int(time.time()),'exp':int(time.time())+3600,'nonce':state['authorization']['nonce'][0],'name':'Test Designer','email':'same@example.test'}|state['overrides']
            token=jwt.encode(claims,state['private'],algorithm='RS256',headers={'kid':'test-key'})
            return httpx.Response(200,json={'id_token':token,'access_token':'never-stored','refresh_token':'never-stored-either'})
        raise AssertionError(request.url)
    store=Store(tmp_path)
    provider=NyxIDClient(config,httpx.Client(transport=httpx.MockTransport(respond)))
    app=create_app(with_worker=False,store=store,auth_config=config,oidc_client=provider)
    client=TestClient(app,base_url=config.origin,follow_redirects=False)
    def begin():
        r=client.get('/api/v1/auth/nyxid/start');assert r.status_code==302
        params=parse_qs(urlsplit(r.headers['location']).query);state['authorization']=params
        return params,r
    def finish():
        return client.get('/api/v1/auth/nyxid/callback',params={'state':state['authorization']['state'][0],'code':'test-code'})
    return client,store,config,state,begin,finish,provider


def test_disabled_mode_preserves_existing_mvp(tmp_path):
    c=TestClient(create_app(with_worker=False,store=Store(tmp_path),auth_config=AuthConfig()))
    assert c.get('/api/v1/auth/config').json()['nyxid_enabled'] is False
    assert c.get('/api/v1/auth/nyxid/start').status_code==503
    u=c.post('/api/v1/identities',json={'name':'Legacy'}).json()
    assert c.get('/api/v1/me',headers={'Authorization':'Bearer '+u['token']}).json()['id']==u['id']
    assert c.get('/api/v1/auth/session').json()['authenticated'] is False


def test_pkce_session_restore_and_single_consent_request(oidc):
    c,store,config,state,begin,finish,provider=oidc
    assert c.get('/api/v1/auth/config').json()['nyxid_enabled']
    assert state['calls']==[]  # app/config/session creation never contacts live NyxID
    p,r=begin()
    assert p['scope']==['openid profile'] and 'prompt' not in p
    assert p['code_challenge_method']==['S256']
    assert 'HttpOnly' in r.headers['set-cookie'] and 'Secure' in r.headers['set-cookie']
    result=finish();assert result.status_code==303 and result.headers['location']=='/'
    assert 'HttpOnly' in result.headers['set-cookie'] and 'never-stored' not in result.text
    session=c.get('/api/v1/auth/session');assert session.headers['cache-control']=='no-store'
    user=session.json()['user'];assert user['name']=='Test Designer' and 'token' not in user
    assert c.get('/api/v1/me').json()==user
    # Cookie auth survives recreating the entire app/process on the same DB.
    restarted=TestClient(create_app(with_worker=False,store=Store(store.root),auth_config=config,oidc_client=provider),base_url=config.origin)
    restarted.cookies.update(c.cookies)
    assert restarted.get('/api/v1/me').json()==user
    with store.db() as db:
        assert db.execute('SELECT count(*) FROM external_identities').fetchone()[0]==1
        row=db.execute('SELECT * FROM browser_sessions').fetchone()
        assert row['hash']!=c.cookies[SESSION_COOKIE]
        assert db.execute('SELECT count(*) FROM login_flows').fetchone()[0]==0
    # New login reuses issuer+sub without trusting email/name for ownership.
    begin();finish();assert c.get('/api/v1/me').json()['id']==user['id']
    state['overrides']={'sub':'user-2'};begin();finish()
    assert c.get('/api/v1/me').json()['id']!=user['id']


@pytest.mark.parametrize('overrides',[{'nonce':'wrong'},{'iss':'another-issuer'},{'aud':'other-client'},{'exp':1},{'iat':4102444800},{'sub':''},{'azp':'other-client'},{'aud':['arena-test','other-client']},{'at_hash':'wrong'}])
def test_invalid_claims_cannot_create_identity(oidc,overrides):
    c,store,_,state,begin,finish,_=oidc
    state['overrides']=overrides;begin()
    assert finish().headers['location']=='/?auth_error=sign_in_failed'
    assert not c.get('/api/v1/auth/session').json()['authenticated']
    with store.db() as db: assert db.execute('SELECT count(*) FROM identities').fetchone()[0]==0


def test_wrong_signature_fails_closed(oidc):
    c,_,_,state,begin,finish,_=oidc
    state['private']=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    begin();assert finish().headers['location']=='/?auth_error=sign_in_failed'
    assert c.get('/api/v1/me').status_code==401


def test_callback_binding_expiry_and_replay(oidc):
    c,store,config,state,begin,finish,provider=oidc
    p,_=begin()
    outsider=TestClient(c.app,base_url=config.origin,follow_redirects=False)
    assert outsider.get('/api/v1/auth/nyxid/callback',params={'state':p['state'][0],'code':'stolen'}).headers['location']=='/?auth_error=sign_in_failed'
    assert finish().headers['location']=='/'
    assert finish().headers['location']=='/?auth_error=sign_in_failed'
    begin()
    with store.db() as db: db.execute('UPDATE login_flows SET expires=0')
    assert finish().headers['location']=='/?auth_error=sign_in_failed'


def test_csrf_agent_token_revocation_and_logout(oidc,monkeypatch):
    c,store,config,_,begin,finish,_=oidc
    begin();finish();session=c.get('/api/v1/auth/session').json()
    headers={'Origin':config.origin,'X-Arena-CSRF':session['csrf_token']}
    assert c.post('/api/v1/auth/agent-tokens').status_code==403
    assert c.post('/api/v1/auth/agent-tokens',headers=headers|{'Origin':'https://evil.example'}).status_code==403
    key=c.post('/api/v1/auth/agent-tokens',headers=headers).json()
    listed=c.get('/api/v1/auth/agent-tokens').json();assert len(listed)==1 and 'hash' not in listed[0] and 'token' not in listed[0]
    agent=TestClient(c.app,base_url=config.origin)
    agent.headers['Authorization']='Bearer '+key['token']
    assert agent.get('/api/v1/me').json()==session['user']
    assert agent.post('/api/v1/auth/agent-tokens').status_code==401
    assert c.get('/api/v1/me',headers={'Authorization':'Bearer wrong'}).status_code==401
    # Both transports enter the same match/ownership path.
    monkeypatch.setattr('flyarena.api.runtime_manifest',lambda:{'frozen':'test'})
    fly=store.add_fly(session['user']['id'],{'name':'fixture','color':'mint'},{'artifact_id':'a'*64})
    request={'fly_ids':[fly['id']],'mode':'forage','duration_seconds':1}
    assert c.post('/api/v1/matches',json=request).status_code==403
    m=c.post('/api/v1/matches',json=request,headers=headers);assert m.status_code==202 and m.json()['owner']==session['user']['id']
    assert agent.post('/api/v1/matches',json=request).status_code==202
    assert c.delete('/api/v1/auth/agent-tokens/'+key['id'],headers=headers).status_code==200
    assert agent.get('/api/v1/me').status_code==401
    old_cookie=c.cookies[SESSION_COOKIE]
    assert c.post('/api/v1/auth/logout',headers=headers).json()['logged_out']
    assert c.get('/api/v1/me').status_code==401
    c.cookies.set(SESSION_COOKIE,old_cookie)
    assert c.get('/api/v1/me').status_code==401


def test_nyxid_mode_does_not_accept_local_identity_bypass(oidc):
    c,store,_,_,_,_,_=oidc
    old=store.identity('Legacy')
    assert c.post('/api/v1/identities',json={'name':'Bypass'}).status_code==403
    assert c.get('/api/v1/me',headers={'Authorization':'Bearer '+old['token']}).status_code==401
    assert c.get('/api/v1/me',headers={'Authorization':'Bearer nyxid-access-token'}).status_code==401


def test_configuration_and_discovery_fail_closed(oidc):
    c,_,config,state,_,_,provider=oidc
    with pytest.raises(ValueError):AuthConfig(mode='nyxid')
    with pytest.raises(ValueError):AuthConfig.safe_url('http://public.example',loopback=True)
    AuthConfig.safe_url('http://127.0.0.1:8080',loopback=True)
    provider.config=AuthConfig(mode='nyxid',base_url=config.base_url,issuer='wrong',client_id=config.client_id,client_secret=config.client_secret,origin=config.origin)
    assert c.get('/api/v1/auth/nyxid/start').status_code==503


def test_expired_session_and_agent_token_stop_working(oidc):
    c,store,config,_,begin,finish,_=oidc
    begin();finish();session=c.get('/api/v1/auth/session').json()
    headers={'Origin':config.origin,'X-Arena-CSRF':session['csrf_token']}
    key=c.post('/api/v1/auth/agent-tokens',headers=headers).json()
    with store.db() as db:
        db.execute('UPDATE agent_tokens SET expires=0')
        db.execute('UPDATE browser_sessions SET expires=0')
    assert c.get('/api/v1/me',headers={'Authorization':'Bearer '+key['token']}).status_code==401
    assert not c.get('/api/v1/auth/session').json()['authenticated']
    assert c.get('/api/v1/me').status_code==401


def test_one_designer_cannot_revoke_another_agent_key(oidc):
    c,store,config,state,begin,finish,_=oidc
    begin();finish();first=c.get('/api/v1/auth/session').json()
    key=c.post('/api/v1/auth/agent-tokens',headers={'Origin':config.origin,'X-Arena-CSRF':first['csrf_token']}).json()
    state['overrides']={'sub':'different-user'};begin();finish()
    second=c.get('/api/v1/auth/session').json()
    c.delete('/api/v1/auth/agent-tokens/'+key['id'],headers={'Origin':config.origin,'X-Arena-CSRF':second['csrf_token']})
    assert c.get('/api/v1/me',headers={'Authorization':'Bearer '+key['token']}).json()==first['user']
