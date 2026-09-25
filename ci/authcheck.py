import ssl,http.server,http.client,threading,tempfile,subprocess,urllib.request,urllib.error,urllib.parse,http.cookiejar,html.parser,json
from pathlib import Path
BASE='https://127.0.0.1:18443'
class Proxy(http.server.BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def proxy(self):
  try:
   data=self.rfile.read(int(self.headers.get('Content-Length','0'))) if self.command=='POST' else None
   headers={k:v for k,v in self.headers.items() if k.lower() not in ['connection','transfer-encoding']};headers['X-Forwarded-Proto']='https';headers['X-Forwarded-Host']='127.0.0.1:18443'
   c=http.client.HTTPConnection('127.0.0.1',18080,timeout=30);c.request(self.command,self.path,body=data,headers=headers);r=c.getresponse();body=r.read();self.send_response(r.status)
   for k,v in r.getheaders():
    if k.lower() not in ['connection','transfer-encoding','content-length']:self.send_header(k,v)
   self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);c.close()
  except Exception:self.send_error(502)
 do_GET=proxy;do_POST=proxy
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*a):return None
class Parser(html.parser.HTMLParser):
 def __init__(self):super().__init__();self.csrf=''
 def handle_starttag(self,t,a):
  d=dict(a)
  if t=='input' and d.get('name')=='_csrf':self.csrf=d.get('value','')
def request(opener,path,data=None):
 r=urllib.request.Request(BASE+path,headers={'User-Agent':'Webtor-isolated-smoke','Origin':BASE,'Referer':BASE+'/login'},data=urllib.parse.urlencode(data).encode() if data is not None else None)
 try:v=opener.open(r,timeout=30)
 except urllib.error.HTTPError as e:v=e
 return v.status,v.headers,v.read().decode(errors='replace')
def start_proxy():
 tmp=tempfile.TemporaryDirectory();p=Path(tmp.name)
 subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(p/'key.pem'),'-out',str(p/'cert.pem'),'-days','1','-subj','/CN=127.0.0.1','-addext','subjectAltName=IP:127.0.0.1'],check=True,capture_output=True)
 server=http.server.ThreadingHTTPServer(('127.0.0.1',18443),Proxy);ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(str(p/'cert.pem'),str(p/'key.pem'));server.socket=ctx.wrap_socket(server.socket,server_side=True);threading.Thread(target=server.serve_forever,daemon=True).start()
 ctx=ssl.create_default_context(cafile=str(p/'cert.pem'));return server,tmp,ctx
def test_auth(env,add,ctx):
 jar=http.cookiejar.CookieJar();op=urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),urllib.request.HTTPCookieProcessor(jar),NoRedirect());anon=urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),NoRedirect())
 def denied(r):return r[0] in [401,403] or (r[0] in [302,303,307] and '/login' in r[1].get('Location',''))
 add('profile_denies_anonymous',denied(request(anon,'/profile')))
 status,headers,body=request(op,'/login');p=Parser();p.feed(body);add('csrf_form_token',status==200 and bool(p.csrf))
 missing=request(op,'/login',{'password':env['ADMIN_PASSWORD']});add('missing_csrf_rejected',missing[0]==403,status=missing[0])
 status,_,body=request(op,'/login');p=Parser();p.feed(body)
 bad=request(op,'/login',{'password':'invalid-test-password','_csrf':p.csrf});add('wrong_password_rejected',bad[0]==401,status=bad[0])
 status,_,body=request(op,'/login');p=Parser();p.feed(body)
 good=request(op,'/login',{'password':env['ADMIN_PASSWORD'],'_csrf':p.csrf});add('valid_password_session',good[0] in [302,303],status=good[0])
 profile=request(op,'/profile');add('authenticated_profile_access',profile[0]==200 and not denied(profile),status=profile[0])
 secretvalues=[c.value for c in jar if c.value]+[p.csrf]
 return {'opener':op,'anonymous':anon,'secretvalues':secretvalues,'profile':profile[2]}
def test_logout(session,add):
 request(session['opener'],'/logout');r=request(session['opener'],'/profile');add('logout_revokes_session',r[0] in [401,403] or (r[0] in [302,303,307] and '/login' in r[1].get('Location','')),status=r[0])
