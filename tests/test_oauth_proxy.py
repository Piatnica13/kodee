"""Exercise real Authlib state/PKCE/JWT validation with an offline OIDC provider."""
import base64
import hashlib
import json
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
import requests
from joserfc import jwt
from joserfc.jwk import RSAKey, OctKey
from flask import jsonify, request
from sqlalchemy import text
import test_system as fixtures
from __init__ import create_app
from db.models import db, User
from db.maintenance import upgrade_schema
from web.app.oauth import init_oauth


class OAuthTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.SystemTests.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.SystemTests.tearDownClass.__func__)
    tearDown = fixtures.SystemTests.tearDown
    csrf = fixtures.SystemTests.csrf
    login = fixtures.SystemTests.login

    def setUp(self):
        fixtures.SystemTests.setUp(self)
        self.app.config.update(GOOGLE_CLIENT_ID='offline-client',GOOGLE_CLIENT_SECRET='offline-secret')
        init_oauth(self.app)
        self.key=RSAKey.generate_key(2048,parameters={'kid':'offline-test'})
        self.claim_changes={}
        self.signing_key=self.key
        self.token_alg='RS256'
        self.token_requests=[]
        self.nonce=None
        self.network=patch('requests.sessions.Session.send',side_effect=self.respond)
        self.transport=self.network.start()

    def tearDown(self):
        self.network.stop()
        self.app.config.update(GOOGLE_CLIENT_ID='',GOOGLE_CLIENT_SECRET='')
        fixtures.SystemTests.tearDown(self)

    def respond(self, prepared, **kwargs):
        url=prepared.url
        if url=='https://accounts.google.com/.well-known/openid-configuration':
            payload={'issuer':'https://accounts.google.com',
                'authorization_endpoint':'https://accounts.google.com/o/oauth2/v2/auth',
                'token_endpoint':'https://oauth2.googleapis.com/token',
                'jwks_uri':'https://www.googleapis.com/oauth2/v3/certs',
                'id_token_signing_alg_values_supported':['RS256']}
        elif url=='https://www.googleapis.com/oauth2/v3/certs':
            payload={'keys':[self.key.as_dict(private=False)]}
        elif url=='https://oauth2.googleapis.com/token':
            body=prepared.body.decode() if isinstance(prepared.body,bytes) else prepared.body
            self.token_requests.append(parse_qs(body))
            now=int(time.time())
            claims={'iss':'https://accounts.google.com','aud':'offline-client','sub':'google-person-1',
                'iat':now,'exp':now+300,'nonce':self.nonce,'email':'google@example.com','email_verified':True,'name':'Google User'}
            claims.update(self.claim_changes)
            payload={'access_token':'offline-access','token_type':'Bearer','expires_in':300,
                'id_token':jwt.encode({'alg':self.token_alg,'kid':'offline-test'},claims,self.signing_key)}
        else:
            raise AssertionError('Unexpected external OAuth request')
        response=requests.Response()
        response.status_code=200
        response.headers['Content-Type']='application/json'
        response._content=json.dumps(payload).encode()
        response.url=url
        response.request=prepared
        return response

    def begin(self,link=False,headers=None):
        if link:
            result=self.client.post('/profil/google/link',data={'csrf_token':self.csrf()},headers=headers)
        else:
            result=self.client.get('/login/google',headers=headers)
        self.assertEqual(result.status_code,302)
        self.authorization=parse_qs(urlsplit(result.location).query)
        self.nonce=self.authorization['nonce'][0]
        self.state=self.authorization['state'][0]
        return self.authorization

    def finish(self,**params):
        return self.client.get('/callback',query_string={'state':self.state,'code':'offline-code',**params})

    def assert_rejected(self):
        result=self.finish()
        self.assertEqual(result.location,'/login')
        self.assertEqual(User.query.filter_by(google_sub='google-person-1').count(),0)

    def test_google_signup_and_pkce(self):
        data=self.begin()
        self.assertEqual(data['redirect_uri'],['http://localhost/callback'])
        self.assertEqual(data['code_challenge_method'],['S256'])
        self.assertEqual(self.finish().location,'/')
        user=User.query.filter_by(google_sub='google-person-1').one()
        self.assertTrue(user.is_google)
        self.assertEqual(user.email,'google@example.com')
        verifier=self.token_requests[0]['code_verifier'][0]
        digest=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        self.assertEqual(digest,data['code_challenge'][0])
        with self.client.session_transaction() as state:
            self.assertEqual(state['user_id'],user.id)
            self.assertFalse(state['admin'])

    def test_state_mismatch_never_calls_token_endpoint(self):
        self.begin()
        self.assertEqual(self.finish(state='forged').location,'/login')
        self.assertFalse(self.token_requests)

    def test_nonce_mismatch(self):
        self.begin()
        self.claim_changes['nonce']='forged'
        self.assert_rejected()

    def test_nonce_cannot_be_disabled_by_token_claim(self):
        self.begin()
        self.claim_changes.update(nonce='forged',nonce_supported=False)
        self.assert_rejected()

    def test_algorithm_substitution_is_rejected(self):
        self.begin()
        self.token_alg='HS256'
        self.signing_key=OctKey.generate_key(256)
        self.assert_rejected()

    def test_google_transport_has_a_timeout(self):
        self.begin()
        self.assertEqual(self.transport.call_args.kwargs['timeout'],10)

    def test_invalid_signature(self):
        self.begin()
        self.signing_key=RSAKey.generate_key(2048,parameters={'kid':'offline-test'})
        self.assert_rejected()

    def test_wrong_audience_and_issuer_and_expiry(self):
        for changed in ({'aud':'another-client'},{'iss':'https://attacker.invalid'},{'exp':int(time.time())-1000}):
            with self.subTest(claims=list(changed)):
                self.begin()
                self.claim_changes=changed
                self.assert_rejected()

    def test_unverified_google_email(self):
        self.begin()
        self.claim_changes['email_verified']=False
        self.assert_rejected()

    def test_no_automatic_email_linking(self):
        self.begin()
        self.claim_changes['email']=self.user.email
        self.assert_rejected()
        self.assertIsNone(self.user.google_sub)

    def test_explicit_link_and_login_after_profile_email_change(self):
        self.login()
        self.begin(link=True)
        self.assertEqual(self.finish().location,'/profil')
        self.assertEqual(db.session.get(User,self.user.id,populate_existing=True).google_sub,'google-person-1')
        self.client.post('/profil/update_user',data={'csrf_token':self.csrf(),'name':'Tester','email':'changed@example.com'})
        self.client.get('/logout')
        self.begin()
        self.assertEqual(self.finish().location,'/')
        with self.client.session_transaction() as state:
            self.assertEqual(state['user_id'],self.user.id)
        self.assertEqual(User.query.count(),2)
        self.assertEqual(db.session.get(User,self.user.id).email,'changed@example.com')

    def test_link_requires_csrf_and_same_session(self):
        self.login()
        self.assertEqual(self.client.post('/profil/google/link').status_code,400)
        self.begin(link=True)
        self.client.get('/logout')
        self.assert_rejected()
        self.assertFalse(self.token_requests)

    def test_google_subject_cannot_be_taken_by_another_profile(self):
        self.user.google_sub='google-person-1'
        db.session.commit()
        self.login(admin=True)
        self.begin(link=True)
        self.assertEqual(self.finish().location,'/login')
        self.assertIsNone(db.session.get(User,self.admin.id,populate_existing=True).google_sub)

    def test_callback_replay_and_denied_consent(self):
        self.begin()
        self.assertEqual(self.finish(error='access_denied').location,'/login')
        self.assertFalse(self.token_requests)
        self.begin()
        self.assertEqual(self.finish().location,'/')
        count=len(self.token_requests)
        self.assertEqual(self.finish().location,'/login')
        self.assertEqual(len(self.token_requests),count)

    def test_expired_flow(self):
        self.begin()
        with self.client.session_transaction() as state:
            flow=state['google_flow'].copy()
            flow['started_at']-=1000
            state['google_flow']=flow
        self.assert_rejected()
        self.assertFalse(self.token_requests)

    def test_redirect_cannot_be_changed_with_host_headers(self):
        data=self.begin(headers={'X-Forwarded-Host':'attacker.invalid','X-Forwarded-Proto':'https'})
        self.assertEqual(data['redirect_uri'],['http://localhost/callback'])
        self.assertEqual(self.client.get('/login/google',headers={'Host':'attacker.invalid'}).status_code,400)

    def test_auth_alias_redirects_before_creating_oauth_state(self):
        with patch.dict(self.app.config,{'TRUSTED_HOSTS':['localhost','alias.example.com']}):
            response=self.client.get('/login/google',base_url='http://alias.example.com')
            self.assertEqual(response.location,'http://localhost/login/google')
            self.assertFalse(self.transport.called)

    def test_legacy_google_binding_is_an_explicit_cli_operation(self):
        result=self.app.test_cli_runner().invoke(args=['bind-google','--user-id',str(self.user.id),'--subject','google-person-1'])
        self.assertEqual(result.exit_code,0,result.output)
        self.begin()
        self.assertEqual(self.finish().location,'/')
        with self.client.session_transaction() as state:
            self.assertEqual(state['user_id'],self.user.id)

    def test_disabled_google_and_discovery_outage(self):
        with patch.dict(self.app.config,{'GOOGLE_CLIENT_ID':''}):
            self.assertEqual(self.client.get('/login/google').status_code,503)
        with patch('requests.sessions.Session.send',side_effect=requests.exceptions.ConnectionError('offline')):
            self.assertEqual(self.client.get('/login/google').location,'/login')

    def test_migration_from_pre_google_sub_schema(self):
        db.session.remove()
        with db.engine.begin() as connection:
            connection.execute(text('DROP INDEX uq_users_google_sub'))
            connection.execute(text('ALTER TABLE users DROP COLUMN google_sub'))
        upgrade_schema()
        self.assertEqual(User.query.count(),2)
        self.assertIsNone(User.query.first().google_sub)


class ProxyTests(unittest.TestCase):
    def app(self,**changes):
        config={'TESTING':True,'SECRET_KEY':'offline-proxy-test','SQLALCHEMY_DATABASE_URI':'sqlite:///:memory:',
                'BOT_TOKEN':None,'APP_BASE_URL':'https://kodee.kz','TRUSTED_HOSTS':['kodee.kz','localhost'],
                'TRUSTED_PROXY_CIDRS':[], 'PROXY_X_FOR':0,'PROXY_X_PROTO':0,'PROXY_X_HOST':0,'PROXY_X_PORT':0}
        config.update(changes)
        app=create_app(config)
        @app.get('/_test/request')
        def details():
            return jsonify(scheme=request.scheme,host=request.host,remote=request.remote_addr)
        return app

    def test_default_ignores_spoofed_headers(self):
        app=self.app()
        response=app.test_client().get('/_test/request',headers={'X-Forwarded-Proto':'https','X-Forwarded-Host':'attacker.invalid','X-Forwarded-For':'1.2.3.4'})
        self.assertEqual(response.json,{'scheme':'http','host':'localhost','remote':'127.0.0.1'})
        self.assertNotIn('Strict-Transport-Security',response.headers)

    def test_trusted_peer_and_single_hop(self):
        app=self.app(TRUSTED_PROXY_CIDRS=['127.0.0.1/32'],PROXY_X_FOR=1,PROXY_X_PROTO=1,PROXY_X_HOST=1)
        response=app.test_client().get('/_test/request',headers={'X-Forwarded-Proto':'http, https','X-Forwarded-Host':'bad.invalid, kodee.kz','X-Forwarded-For':'10.0.0.1, 203.0.113.8'})
        self.assertEqual(response.json,{'scheme':'https','host':'kodee.kz','remote':'203.0.113.8'})
        self.assertIn('Strict-Transport-Security',response.headers)

    def test_untrusted_peer_cannot_use_enabled_proxyfix(self):
        app=self.app(TRUSTED_PROXY_CIDRS=['10.1.0.0/16'],PROXY_X_FOR=1,PROXY_X_PROTO=1,PROXY_X_HOST=1)
        response=app.test_client().get('/_test/request',headers={'X-Forwarded-Proto':'https','X-Forwarded-Host':'kodee.kz','X-Forwarded-For':'1.2.3.4'})
        self.assertEqual(response.json['scheme'],'http')
        self.assertEqual(response.json['host'],'localhost')

    def test_invalid_host_and_scheme(self):
        app=self.app(TRUSTED_PROXY_CIDRS=['127.0.0.1/32'],PROXY_X_PROTO=1,PROXY_X_HOST=1)
        for headers in ({'Host':'evil.invalid'},{'X-Forwarded-Host':'evil.invalid'},{'X-Forwarded-Proto':'javascript'}):
            self.assertEqual(app.test_client().get('/_test/request',headers=headers).status_code,400)

    def test_standard_https_port_does_not_create_auth_redirect_loop(self):
        app=self.app(TRUSTED_PROXY_CIDRS=['127.0.0.1/32'],PROXY_X_PROTO=1,PROXY_X_HOST=1,PROXY_X_PORT=1)
        response=app.test_client().get('/login',headers={'X-Forwarded-Proto':'https','X-Forwarded-Host':'kodee.kz','X-Forwarded-Port':'443'})
        self.assertEqual(response.status_code,200)

    def test_invalid_proxy_configuration_fails_early(self):
        for changes in ({'APP_BASE_URL':'https://user:pass@kodee.kz'},{'APP_BASE_URL':'https://kodee.kz:bad'},{'APP_BASE_URL':'https://kodee.kz:0'},{'TRUSTED_PROXY_CIDRS':['invalid']},{'PROXY_X_FOR':-1}):
            with self.assertRaises(ValueError):
                self.app(**changes)


if __name__=='__main__':
    unittest.main()
