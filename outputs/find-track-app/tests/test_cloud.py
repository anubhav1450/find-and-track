import copy,io,json,sys,http.client,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cloud import Config,CloudError,Supabase,make_handler,ACCESS,REFRESH,CSRF,PKCE
ORIGIN='https://findtrack.example.com'
CONFIG=Config('https://project.supabase.co','public-test-key','owner@example.com',ORIGIN)
DATA={'schema':1,'profile':{'name':'Test Owner','resume':'Python'},'jobs':[],'contacts':[],'companies':[],'events':[],'actions':[],'rules':[]}
USER={'id':'6c1e0524-0413-49bc-afaa-09a130722e27','email':'owner@example.com','email_confirmed_at':'2026-10-27'}
class MemorySocket:
    def __init__(self,value):self.input=io.BytesIO(value);self.output=io.BytesIO()
    def makefile(self,*args,**kwargs):return self.input
    def sendall(self,value):self.output.write(value)
class Store:
    def __init__(self):self.state={'revision':1,'data':copy.deepcopy(DATA)};self.user_value=USER;self.sent=[];self.saved=0
    def user(self,token):
        if token not in ('valid-token','new-token'):raise CloudError(401,'Sign in again')
        return self.user_value
    def load(self,access):return copy.deepcopy(self.state)
    def save(self,access,revision,data):
        if revision!=self.state['revision']:raise CloudError(409,'Reload before editing')
        self.saved+=1;self.state={'revision':revision+1,'data':copy.deepcopy(data)};return revision+1
    def start(self,email,challenge):self.sent.append(email);self.challenge=challenge
    def exchange(self,code,verifier):
        if code!='valid-code' or verifier!='v'*64:raise CloudError(400,'Invalid code')
        return {'access_token':'valid-token','refresh_token':'refresh-token','expires_in':3600}
    def verify(self,email,code):
        if code!='123456':raise CloudError(400,'Invalid code')
        return {'access_token':'valid-token','refresh_token':'refresh-token','expires_in':3600}
    def refresh(self,token):
        if token!='refresh-token':raise CloudError(401,'Sign in again')
        return {'access_token':'new-token','refresh_token':'next-refresh','expires_in':3600}
    def logout(self,access):pass
class CloudTests(unittest.TestCase):
    def setUp(self):self.store=Store()
    def request(self,path='/api/state',method='GET',body=None,authenticated=False,headers=None):
        raw=json.dumps(body).encode() if body is not None else b''
        fields={'Host':'findtrack.example.com','Content-Length':str(len(raw))}
        if authenticated:fields['Cookie']=f'{ACCESS}=valid-token; {CSRF}=nonce'
        fields.update(headers or {})
        request=f'{method} {path} HTTP/1.0\r\n'+''.join(f'{k}: {v}\r\n' for k,v in fields.items())+'\r\n'
        sock=MemorySocket(request.encode()+raw)
        make_handler(CONFIG,self.store)(sock,('127.0.0.1',12),SimpleNamespace(server_port=443))
        response=http.client.HTTPResponse(MemorySocket(sock.output.getvalue()));response.begin()
        data=response.read()
        return response.status, json.loads(data) if response.headers['Content-Type'].startswith('application/json') else data.decode(),response.headers
    def write(self,body,headers=None):return self.request(method='PUT',body=body,authenticated=True,headers={'Origin':ORIGIN,'X-Workspace-Token':'nonce',**(headers or {})})
    def test_unauthenticated_requests_never_return_private_data(self):
        status,body,_=self.request();self.assertEqual(status,401);self.assertNotIn('Test Owner',json.dumps(body))
        self.assertEqual(self.request('/api/session')[0],401)
        status,body,_=self.request('/');self.assertEqual(status,200);self.assertIn('Your private workspace.',body)
    def test_session_uses_verified_user_and_httponly_csrf(self):
        status,body,headers=self.request('/api/session',authenticated=True)
        self.assertEqual(status,200);self.assertEqual(body['storage'],'cloud');self.assertEqual(body['token'],'nonce')
        status,body,headers=self.request('/api/session',headers={'Cookie':f'{ACCESS}=valid-token'})
        self.assertEqual(status,200);self.assertIn('HttpOnly',headers['Set-Cookie']);self.assertIn('Secure',headers['Set-Cookie'])
        self.assertNotIn('valid-token',json.dumps(body))
    def test_other_verified_account_is_rejected(self):
        self.store.user_value={**USER,'email':'other@example.com'}
        self.assertEqual(self.request(authenticated=True)[0],403);self.assertEqual(self.store.saved,0)
    def test_unconfirmed_owner_is_rejected(self):
        self.store.user_value={**USER,'email_confirmed_at':None}
        self.assertEqual(self.request(authenticated=True)[0],403)
    def test_host_origin_and_csrf_are_all_required(self):
        payload={'revision':1,'data':DATA}
        self.assertEqual(self.write(payload,{'Host':'evil.example'})[0],403)
        self.assertEqual(self.write(payload,{'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.write(payload,{'X-Workspace-Token':'wrong'})[0],403)
        self.assertEqual(self.request(method='PUT',body=payload,authenticated=True)[0],403)
        self.assertEqual(self.store.saved,0)
    def test_stale_write_preserves_newer_workspace(self):
        self.assertEqual(self.write({'revision':1,'data':DATA})[0],200)
        changed=copy.deepcopy(DATA);changed['profile']['name']='Stale'
        self.assertEqual(self.write({'revision':1,'data':changed})[0],409)
        self.assertEqual(self.store.state['data']['profile']['name'],'Test Owner')
    def test_malformed_import_cannot_save(self):
        bad=copy.deepcopy(DATA);bad['jobs']=[{'id':'bad','title':'Job','company':'Test','status':'applied','url':'javascript:alert(1)'}]
        self.assertEqual(self.write({'revision':1,'data':bad})[0],400);self.assertEqual(self.store.saved,0)
    def test_login_start_does_not_enumerate_owner(self):
        a=self.request('/api/auth/start','POST',{'email':'owner@example.com'},headers={'Origin':ORIGIN})
        b=self.request('/api/auth/start','POST',{'email':'other@example.com'},headers={'Origin':ORIGIN})
        self.assertEqual(a[:2],b[:2]);self.assertEqual(self.store.sent,['owner@example.com'])
    def test_successful_login_sets_secure_host_only_cookies(self):
        status,body,headers=self.request('/api/auth/verify','POST',{'email':'owner@example.com','code':'123456'},headers={'Origin':ORIGIN})
        self.assertEqual(status,200);self.assertEqual(body,{'ok':True})
        cookies=headers.get_all('Set-Cookie');self.assertEqual(len(cookies),3)
        for cookie in cookies:
            self.assertIn('HttpOnly',cookie);self.assertIn('Secure',cookie);self.assertIn('Path=/',cookie);self.assertNotIn('Domain=',cookie)
        self.assertEqual(self.request('/api/auth/verify','POST',{'email':'owner@example.com','code':'000000'},headers={'Origin':ORIGIN})[0],400)
    def test_expired_access_refreshes_via_provider(self):
        status,body,headers=self.request(headers={'Cookie':f'{ACCESS}=expired; {REFRESH}=refresh-token'})
        self.assertEqual(status,200);self.assertEqual(body['data']['profile']['name'],'Test Owner')
        self.assertTrue(any('new-token' in c for c in headers.get_all('Set-Cookie')))
    def test_logout_clears_all_cookies(self):
        status,_,headers=self.request('/api/auth/logout','POST',authenticated=True,headers={'Origin':ORIGIN,'X-Workspace-Token':'nonce'})
        self.assertEqual(status,200)
        self.assertEqual(len(headers.get_all('Set-Cookie')),4)
        self.assertTrue(all('Max-Age=0' in c for c in headers.get_all('Set-Cookie')))
    def test_cloud_workflow_preserves_revision_conflicts(self):
        self.assertEqual(self.request('/api/workflow','POST',{'action':'prepare'},True,{'Origin':ORIGIN,'X-Workspace-Token':'nonce'})[0],200)
        self.assertEqual(self.store.state['revision'],2)
    def test_magic_link_requires_the_original_browser_proof(self):
        status,_,_=self.request('/auth/callback?code=valid-code')
        self.assertEqual(status,401)
        status,_,headers=self.request('/auth/callback?code=valid-code',headers={'Cookie':f'{PKCE}='+('v'*64)})
        self.assertEqual(status,303);self.assertEqual(headers['Location'],'/')
        self.assertEqual(len(headers.get_all('Set-Cookie')),4)
        self.assertEqual(self.request('/auth/callback?code=valid-code&code=other',headers={'Cookie':f'{PKCE}='+('v'*64)})[0],401)
    def test_magic_link_start_sets_secure_pkce_proof(self):
        status,_,headers=self.request('/api/auth/start','POST',{'email':'owner@example.com'},headers={'Origin':ORIGIN})
        self.assertEqual(status,200);self.assertIn(PKCE,headers['Set-Cookie']);self.assertIn('HttpOnly',headers['Set-Cookie'])
        self.assertEqual(len(self.store.challenge),43)
    def test_missing_env_fails_closed(self):
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaises(CloudError) as exc:Config.from_env()
        self.assertEqual(exc.exception.status,503)
    def test_provider_errors_do_not_echo_credentials(self):
        from urllib.error import HTTPError
        error=HTTPError('https://project.supabase.co/auth/v1/user',500,'oops',{},io.BytesIO(b'{"message":"SECRET TOKEN"}'))
        with patch('cloud.urlopen',side_effect=error):
            with self.assertRaises(CloudError) as exc:Supabase(CONFIG).user('SECRET TOKEN')
        self.assertNotIn('SECRET',str(exc.exception));self.assertEqual(exc.exception.status,502)
if __name__=='__main__':unittest.main()
