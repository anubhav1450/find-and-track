"""Hosted workspace using verified sessions and ownership-enforced Supabase storage.
No service-role key or database password is used by the application.
"""
from dataclasses import dataclass
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from urllib.parse import urlsplit,urlencode,parse_qs
import base64,hashlib,hmac,json,mimetypes,os,re,secrets
from uuid import UUID
from server import validate
from workflow import prepare,refresh_feed,fetch_hevo,utcnow
ROOT=Path(__file__).resolve().parent
ACCESS='__Host-ft_access';REFRESH='__Host-ft_refresh';CSRF='__Host-ft_csrf';PKCE='__Host-ft_pkce'
class CloudError(Exception):
    def __init__(self,status,message):
        self.status,self.message=status,message
        super().__init__(message)
@dataclass(frozen=True)
class Config:
    url:str
    key:str
    owner_email:str
    origin:str
    @classmethod
    def from_env(cls):
        url=os.environ.get('SUPABASE_URL','').rstrip('/')
        key=os.environ.get('SUPABASE_PUBLISHABLE_KEY','')
        email=os.environ.get('FINDTRACK_OWNER_EMAIL','').lower().strip()
        origin=os.environ.get('APP_ORIGIN','').rstrip('/')
        if not re.fullmatch(r'https://[a-z0-9-]+\.supabase\.co',url) or not key or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):raise CloudError(503,'Private cloud setup is incomplete.')
        p=urlsplit(origin)
        if p.scheme!='https' or not p.netloc or p.path or p.query or p.fragment or p.username:raise CloudError(503,'Private cloud origin is not configured.')
        return cls(url,key,email,origin)
class Supabase:
    def __init__(self,config):self.config=config
    def request(self,path,method='GET',payload=None,access=None):
        headers={'apikey':self.config.key,'Accept':'application/json'}
        if access:headers['Authorization']='Bearer '+access
        raw=None
        if payload is not None:raw=json.dumps(payload).encode();headers['Content-Type']='application/json'
        req=Request(self.config.url+path,data=raw,method=method,headers=headers)
        try:
            with urlopen(req,timeout=12) as response:
                body=response.read(6_000_001)
                if len(body)>6_000_000:raise CloudError(502,'The cloud response is too large.')
                return json.loads(body) if body else {}
        except HTTPError as exc:
            status=exc.code
            with exc:
                try:code=json.loads(exc.read(8192)).get('code')
                except (ValueError,AttributeError):code=None
            if code=='P0001':raise CloudError(409,'This workspace changed in another tab. Reload before editing.') from None
            if status in (401,403):raise CloudError(401,'Please sign in again.') from None
            if status==429:raise CloudError(429,'Too many attempts. Please wait before trying again.') from None
            if path.startswith('/auth/') and status in (400,422):raise CloudError(400,'The sign-in code could not be verified. Request a new code.') from None
            raise CloudError(502,'The cloud service is unavailable. Your saved workspace is preserved.') from None
        except (URLError,TimeoutError,OSError,ValueError):raise CloudError(502,'The cloud service is unavailable. Your saved workspace is preserved.') from None
    def user(self,access):return self.request('/auth/v1/user',access=access)
    def refresh(self,token):return self.request('/auth/v1/token?grant_type=refresh_token','POST',{'refresh_token':token})
    def start(self,email,challenge):return self.request('/auth/v1/otp?'+urlencode({'redirect_to':self.config.origin+'/auth/callback'}),'POST',{'email':email,'create_user':True,'code_challenge':challenge,'code_challenge_method':'s256'})
    def exchange(self,code,verifier):return self.request('/auth/v1/token?grant_type=pkce','POST',{'auth_code':code,'code_verifier':verifier})
    def verify(self,email,code):return self.request('/auth/v1/verify','POST',{'email':email,'token':code,'type':'email'})
    def logout(self,access):return self.request('/auth/v1/logout','POST',access=access)
    def load(self,access):
        seed=json.loads((ROOT/'seed.example.json').read_text())
        row=self.request('/rest/v1/rpc/findtrack_load','POST',{'initial_data':seed},access)
        if not isinstance(row,dict) or not isinstance(row.get('revision'),int):raise CloudError(502,'The cloud workspace could not be read.')
        validate(row['data']);return row
    def save(self,access,revision,data):
        validate(data)
        value=self.request('/rest/v1/rpc/findtrack_save','POST',{'expected_revision':revision,'new_data':data},access)
        if type(value) is not int:raise CloudError(502,'The cloud save could not be confirmed. Reload before editing.')
        return value

def make_handler(config=None,client=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass  # No auth query strings, cookies or bodies in logs.
        def reply(self,status,value,kind='application/json; charset=utf-8',extra=None):
            body=json.dumps(value).encode() if kind.startswith('application/json') else value
            self.send_response(status)
            headers={'Content-Type':kind,'Content-Length':str(len(body)),'Cache-Control':'private, no-store','Vary':'Cookie','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"}
            for k,v in {**headers,**(extra or {})}.items():self.send_header(k,v)
            for cookie in self.out_cookies:self.send_header('Set-Cookie',cookie)
            self.end_headers();self.wfile.write(body)
        def cookie(self,name,value,age):self.out_cookies.append(f'{name}={value}; Path=/; Max-Age={int(age)}; Secure; HttpOnly; SameSite=Lax')
        def clear_cookies(self):
            for name in (ACCESS,REFRESH,CSRF,PKCE):self.cookie(name,'',0)
        def body(self,limit=5_000_000):
            try:size=int(self.headers.get('Content-Length','0'))
            except ValueError:raise CloudError(400,'Invalid request.')
            if size<1 or size>limit:raise CloudError(413,'The request is too large or empty.')
            try:value=json.loads(self.rfile.read(size))
            except (ValueError,UnicodeError):raise CloudError(400,'Invalid JSON request.')
            if not isinstance(value,dict):raise CloudError(400,'Expected an object.')
            return value
        def origin(self):
            if self.headers.get('Origin')!=self.cfg.origin:raise CloudError(403,'Request origin is not allowed.')
        def owner(self,user):
            if not isinstance(user,dict) or user.get('email','').lower()!=self.cfg.owner_email or not user.get('email_confirmed_at'):
                self.clear_cookies();raise CloudError(403,'This workspace is private.')
            try:UUID(user['id'])
            except (KeyError,ValueError,TypeError):raise CloudError(401,'Please sign in again.')
            return user
        def tokens(self,session):
            access,refresh=session.get('access_token'),session.get('refresh_token')
            if not all(isinstance(t,str) and re.fullmatch(r'[A-Za-z0-9_.-]+',t) for t in (access,refresh)):raise CloudError(502,'The sign-in session could not be established.')
            self.cookie(ACCESS,access,min(int(session.get('expires_in',3600)),86400));self.cookie(REFRESH,refresh,604800)
            return access
        def authenticated(self):
            self.access=self.cookies.get(ACCESS).value if self.cookies.get(ACCESS) else ''
            try:
                if not self.access:raise CloudError(401,'Please sign in.')
                return self.owner(self.db.user(self.access))
            except CloudError as exc:
                if exc.status!=401:raise
                refresh=self.cookies.get(REFRESH)
                if not refresh:raise
                session=self.db.refresh(refresh.value)
                user=self.owner(self.db.user(session.get('access_token','')))
                self.access=self.tokens(session)
                return user
        def csrf(self):
            value=self.cookies.get(CSRF);sent=self.headers.get('X-Workspace-Token','')
            if not value or not sent or not hmac.compare_digest(value.value,sent):raise CloudError(403,'Reload this page before editing.')
        def asset(self,name):
            file=ROOT/'static'/name
            return self.reply(200,file.read_bytes(),(mimetypes.guess_type(file.name)[0] or 'text/plain')+'; charset=utf-8')
        def dispatch(self):
            self.out_cookies=[];self.cookies=SimpleCookie()
            try:
                self.cookies.load(self.headers.get('Cookie',''))
                path=urlsplit(self.path).path
                assets={'/app.js':'app.js','/domain.js':'domain.js','/styles.css':'styles.css','/login.js':'login.js'}
                if self.command=='GET' and path in assets:return self.asset(assets[path])
                try:self.cfg=config or Config.from_env()
                except CloudError:
                    if self.command=='GET' and path in ('/','/login'):return self.reply(503,(ROOT/'static'/'setup.html').read_bytes(),'text/html; charset=utf-8')
                    raise
                self.db=client or Supabase(self.cfg)
                if self.headers.get('Host')!=urlsplit(self.cfg.origin).netloc:raise CloudError(403,'Request host is not allowed.')
                if self.command=='GET' and path=='/health':return self.reply(200,{'status':'ok','storage':'supabase'})
                if self.command=='GET' and path=='/login':return self.asset('login.html')
                if self.command=='POST':
                    self.origin()
                    if path=='/api/auth/start':
                        email=str(self.body(2048).get('email','')).strip().lower()
                        verifier=secrets.token_urlsafe(48)
                        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
                        self.cookie(PKCE,verifier,600)
                        if email==self.cfg.owner_email:self.db.start(email,challenge)
                        return self.reply(200,{'message':'If this is the workspace owner’s email, a sign-in link is on its way. Open it in this browser to continue.'})
                    if path=='/api/auth/verify':
                        body=self.body(2048);email=str(body.get('email','')).strip().lower();code=str(body.get('code','')).strip()
                        if email!=self.cfg.owner_email or not re.fullmatch(r'\d{6,10}',code):raise CloudError(400,'Check your email and sign-in code.')
                        session=self.db.verify(email,code);self.owner(self.db.user(session.get('access_token','')))
                        self.tokens(session);self.cookie(CSRF,secrets.token_urlsafe(32),604800)
                        return self.reply(200,{'ok':True})
                if self.command=='GET' and path=='/auth/callback':
                    query=parse_qs(urlsplit(self.path).query,max_num_fields=10)
                    codes=query.get('code',[]);verifier=self.cookies.get(PKCE)
                    self.cookie(PKCE,'',0)
                    if len(codes)!=1 or not re.fullmatch(r'[A-Za-z0-9_-]{8,256}',codes[0]) or not verifier or not re.fullmatch(r'[A-Za-z0-9_-]{43,128}',verifier.value):
                        raise CloudError(401,'Open the sign-in link in the browser where you requested it, or request a new link.')
                    session=self.db.exchange(codes[0],verifier.value)
                    self.owner(self.db.user(session.get('access_token','')))
                    self.tokens(session);self.cookie(CSRF,secrets.token_urlsafe(32),604800)
                    return self.reply(303,b'','text/plain; charset=utf-8',{'Location':'/'})
                if self.command=='GET' and path=='/':
                    try:self.authenticated()
                    except CloudError as exc:
                        if exc.status in (401,403):return self.asset('login.html')
                        raise
                    return self.asset('index.html')
                self.authenticated()
                if self.command=='GET' and path=='/api/session':
                    value=self.cookies.get(CSRF);nonce=value.value if value else secrets.token_urlsafe(32)
                    if not value:self.cookie(CSRF,nonce,604800)
                    return self.reply(200,{'token':nonce,'workflowVersion':1,'storage':'cloud'})
                if self.command=='GET' and path=='/api/state':return self.reply(200,self.db.load(self.access))
                if self.command in ('POST','PUT'):
                    self.origin();self.csrf()
                    if self.command=='POST' and path=='/api/auth/logout':
                        try:self.db.logout(self.access)
                        finally:self.clear_cookies()
                        return self.reply(200,{'ok':True})
                    if self.command=='PUT' and path=='/api/state':
                        body=self.body();data=validate(body.get('data'));revision=body.get('revision')
                        if type(revision) is not int or revision<1:raise CloudError(400,'Invalid workspace revision.')
                        return self.reply(200,{'revision':self.db.save(self.access,revision,data)})
                    if self.command=='POST' and path=='/api/workflow':
                        body=self.body(1024)
                        if body.get('action') not in ('prepare','refresh'):raise CloudError(400,'Unknown workflow action.')
                        state=self.db.load(self.access);data=state['data'];stamp=utcnow()
                        report={'at':stamp,'mode':'cloud preparation','sources':[]}
                        if body['action']=='refresh':
                            try:posts=fetch_hevo()
                            except Exception:report['sources'].append({'source':'Hevo Data / Lever public postings API','error':'Public feed unavailable; saved jobs preserved.'})
                            else:report['sources'].append(refresh_feed(data,posts,stamp))
                        report['preparation']=prepare(data,stamp);data.setdefault('workflow',{})['lastRun']=report
                        self.db.save(self.access,state['revision'],data)
                        return self.reply(200,{'report':report})
                raise CloudError(404,'Not found.')
            except CloudError as exc:return self.reply(exc.status,{'error':exc.message})
            except (ValueError,KeyError,TypeError,AttributeError):return self.reply(400,{'error':'The request could not be validated.'})
            except Exception:return self.reply(500,{'error':'The request could not be completed. Reload before editing.'})
        do_GET=dispatch
        do_POST=dispatch
        do_PUT=dispatch
    return Handler
