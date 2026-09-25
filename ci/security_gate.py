"""Isolated security gate. Abort immediately on observed blocking evidence. No production."""
import os,sys,json,time,ssl,signal,secrets,threading,subprocess,urllib.request,urllib.error,urllib.parse
import authcheck,video
NAME='tmx-webtor-smoke';prefix='tmx-security-v2-';volumes={'/var/lib/webtor':prefix+'data','/etc/webtor':prefix+'config','/var/log':prefix+'logs'}
expected_tmpfs={'/run','/tmp','/var/tmp'};known=set();done=threading.Event();failed=threading.Event();results=[];captured=[]
class CriticalStop(BaseException):pass
class Deadline(BaseException):pass
def output(test,status,**detail):
 r={'test':test,'environment':'GitHub Ubuntu standard / isolated Docker / local test TLS','real_or_simulated':'REAL','result':status,**detail};results.append(r);print(json.dumps(r,separators=(',',':')),flush=True)
def run(a,**kw):return subprocess.run(a,check=True,capture_output=True,text=True,timeout=kw.pop('timeout',25),**kw)
def stop(test,**evidence):
 if not failed.is_set():
  failed.set();output(test,'FAIL',blocking=True,**evidence)
  subprocess.run(['docker','stop','--time','1',NAME],capture_output=True,timeout=12)
 if threading.current_thread() is threading.main_thread():raise CriticalStop()
 os.kill(os.getpid(),signal.SIGUSR1)
def reject_signal(*args):raise CriticalStop()
signal.signal(signal.SIGUSR1,reject_signal)
def leakcheck(data,scope,allowed=()):
 if isinstance(data,bytes):data=data.decode(errors='replace')
 for value in tuple(known):
  if len(value)<16 or value in allowed:continue
  if any(v in data for v in [value,urllib.parse.quote(value,safe=''),urllib.parse.quote_plus(value),urllib.parse.unquote(value)]):stop('secret_disclosure',surface=scope,values_not_published=True)
def inspect_safety():
 j=json.loads(run(['docker','inspect',NAME]).stdout)[0];h=j['HostConfig'];mounts=j['Mounts'];caps={x.removeprefix('CAP_') for x in h.get('CapAdd') or []}
 good=(not h['Privileged'] and h.get('NetworkMode') not in ['host'] and h.get('PidMode')!='host' and h.get('IpcMode')!='host' and not h.get('Devices') and not h.get('DeviceRequests') and {x.removeprefix('CAP_') for x in h.get('CapDrop') or []}=={'ALL'} and caps<= {'CHOWN','DAC_OVERRIDE','FOWNER','KILL','SETGID','SETUID'} and any(x.startswith('no-new-privileges') for x in h.get('SecurityOpt',[])) and not any('unconfined' in x for x in h.get('SecurityOpt',[])))
 if not good:stop('container_privilege_gate',privileged=h['Privileged'],capabilities=sorted(caps))
 for m in mounts:
  if m['Type']=='volume' and volumes.get(m['Destination'])==m.get('Name'):continue
  if m['Type']=='tmpfs' and m['Destination'] in expected_tmpfs:continue
  stop('unexpected_mount',destination=m['Destination'],mount_type=m['Type'])
 return j

def storage_check():
 changes=run(['docker','diff',NAME]).stdout.splitlines();paths=[]
 for line in changes:
  _,_,path=line.partition(' ')
  # Parent directory metadata can change when a declared mountpoint is prepared.
  # Only directories are ignored this way, never arbitrary files under /etc or /var.
  parents={str(__import__('pathlib').PurePosixPath(p).parent) for p in set(volumes)|expected_tmpfs}
  if path in parents and line.startswith('C '):continue
  if any(path==p or path.startswith(p+'/') for p in set(volumes)|expected_tmpfs):continue
  paths.append(path)
 if paths:stop('write_outside_declared_volumes',paths=sorted(paths)[:30],total=len(paths))

def watch():
 while not done.is_set():
  try:
   storage_check()
   r=run(['docker','logs',NAME]);leakcheck(r.stdout+r.stderr,'container_logs')
  except CriticalStop:return
  except Exception as e:
   if not done.is_set() and not failed.is_set():stop('security_watchdog_failure',error_type=type(e).__name__)
  done.wait(1)

def main():
 env=os.environ.copy();proxy=None;tmp=None;watcher=None;oldopen=urllib.request.OpenerDirector.open
 for k in ['ADMIN_PASSWORD','PG_PASSWORD','AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY']:env[k]=secrets.token_hex(24);known.add(env[k])
 env.update(DOMAIN=authcheck.BASE,ONLY_AUTHORIZED='true',EMBED_ONLY_AUTHORIZED='true')
 try:
  for name in volumes.values():run(['docker','volume','create',name])
  args=['docker','run','-d','--name',NAME,'--cap-drop','ALL','--security-opt','no-new-privileges:true','--memory=6g','--cpus=2','-p','127.0.0.1:18080:8080']
  for cap in ['CHOWN','DAC_OVERRIDE','FOWNER','KILL','SETGID','SETUID']:args+=['--cap-add',cap]
  for target,name in volumes.items():args+=['--mount','type=volume,source='+name+',target='+target]
  for target in expected_tmpfs:args+=['--tmpfs',target+':rw,nosuid,nodev,size=128m,mode=1777' if target!='/run' else target+':rw,nosuid,nodev,size=128m,mode=755']
  for k in ['ADMIN_PASSWORD','PG_PASSWORD','AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','DOMAIN','ONLY_AUTHORIZED','EMBED_ONLY_AUTHORIZED']:args+=['--env',k]
  run(args+['tmx-webtor:test'],env=env);inspect_safety();output('restricted_container_settings','PASS',privileged=False,added_capabilities=['CHOWN','DAC_OVERRIDE','FOWNER','KILL','SETGID','SETUID'],no_host_namespace=True,no_docker_socket=True,limitation='Not a proof that every retained capability is strictly necessary')
  watcher=threading.Thread(target=watch,daemon=True);watcher.start()
  deadline=time.monotonic()+240
  while time.monotonic()<deadline:
   state=inspect_safety()['State']
   if not state.get('Running'):stop('startup_under_restrictions',state='not_running')
   if state.get('Health',{}).get('Status')=='healthy':break
   time.sleep(2)
  else:stop('startup_under_restrictions',state='healthcheck_timeout')
  storage_check();output('declared_storage_confinement_at_startup','PASS',volumes=list(volumes),tmpfs=sorted(expected_tmpfs),limitation='Docker writable-layer diff plus mount inspection, not host eBPF syscall tracing')
  proxy,tmp,ctx=authcheck.start_proxy();output('https_local_certificate','PASS',hostname_verification=ctx.check_hostname,certificate_verification=ctx.verify_mode==ssl.CERT_REQUIRED,limitation='Private test CA, not a publicly trusted certificate')
  def authadd(name,ok,**kw):
   if not ok:stop(name,mechanism='browser_session',**kw)
   output(name,'PASS',mechanism='browser_session',**kw)
  session=authcheck.test_auth(env,authadd,ctx);known.update(session['secretvalues'])
  opener=urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),authcheck.NoRedirect())
  def request(url,headers=None):
   try:r=opener.open(urllib.request.Request(url,headers=headers or {}),timeout=20)
   except urllib.error.HTTPError as e:r=e
   body=r.read(2_000_000);leakcheck(str(r.headers)+body.decode(errors='replace'),'negative_http_response');return r.status,body
  for label,headers in [('api_key_absent',{}),('api_key_invalid',{'Authorization':'Bearer 00000000-0000-4000-8000-000000000000'})]:
   status,_=request(authcheck.BASE+'/api/v1/library',headers)
   if status not in [401,403]:stop(label,http_status=status,mechanism='api_key')
   output(label,'PASS',http_status=status,mechanism='api_key')
  # Intercept only URL metadata in memory. Never emit URLs, query values or raw exceptions.
  def observe(self,fullurl,*a,**kw):
   u=fullurl.full_url if isinstance(fullurl,urllib.request.Request) else str(fullurl)
   if urllib.parse.urlsplit(u).netloc=='127.0.0.1:18443' and '/torrent-http-proxy/' in u:
    captured.append(u)
    for key,values in urllib.parse.parse_qs(urllib.parse.urlsplit(u).query).items():
     if key.lower() in ['token','sig','signature','api-key','key','api_key']:known.update(values)
   return oldopen(self,fullurl,*a,**kw)
  urllib.request.OpenerDirector.open=observe
  def videoadd(name,ok,**kw):
   if not ok:stop(name,**kw)
   output(name,'PASS',**kw)
  if not video.test_video(session,videoadd,ctx,run):stop('hls_positive_control')
  known.update(session['secretvalues']);urllib.request.OpenerDirector.open=oldopen
  targets=list(dict.fromkeys(captured));require_targets=[u for u in targets if urllib.parse.urlsplit(u).path.endswith(('.m3u8','.ts'))]
  if not require_targets:stop('hls_negative_test_setup',reason='no_observed_playlist_or_segment')
  for i,url in enumerate(require_targets):
   u=urllib.parse.urlsplit(url);pairs=urllib.parse.parse_qsl(u.query,keep_blank_values=True);token_names=[k for k,v in pairs if k.lower() in ['token','sig','signature']];kind='playlist' if u.path.endswith('.m3u8') else 'segment'
   absent=urllib.parse.urlunsplit(u._replace(query=''));status,body=request(absent)
   if status not in [400,401,403,404]:stop('hls_token_absent',resource=kind,http_status=status)
   output('hls_token_absent','PASS',resource=kind,http_status=status)
   if not token_names:output('hls_token_invalid','NON TESTÉ',resource=kind,limitation='No independently identified signature parameter');continue
   altered=[]
   for k,v in pairs:
    if k in token_names and v:
     n=len(v)//2;v=v[:n]+('B' if v[n]=='A' else 'A')+v[n+1:];known.add(v)
    altered.append((k,v))
   status,body=request(urllib.parse.urlunsplit(u._replace(query=urllib.parse.urlencode(altered))))
   if status not in [400,401,403,404]:stop('hls_token_invalid',resource=kind,http_status=status,valid_other_parameters_preserved=True)
   output('hls_token_invalid','PASS',resource=kind,http_status=status,valid_other_parameters_preserved=True)
  output('browser_session_expired','NON TESTÉ',limitation='No demonstrated supported short TTL or genuinely expired server-valid cookie; logout is not expiration')
  output('hls_token_expired','NON TESTÉ',limitation='No genuine expiration measured; token corruption is not expiration')
  for path in ['/profile','/api-credentials/key','/not-a-real-route','/metrics','/health','/debug/vars','/debug/pprof/','/.env']:
   status,body=request(authcheck.BASE+path);output('anonymous_response_secrets','PASS',path=path,http_status=status,limitation='Known test secrets checked, not a universal proof of no disclosure')
  r=run(['docker','logs',NAME]);leakcheck(r.stdout+r.stderr,'container_logs');storage_check()
  output('gate_finished','PASS',limitation='Only tested controls pass; expired credentials, public HTTPS, iPhone and long endurance are not validated')
 except CriticalStop:pass
 except BaseException as e:
  if not failed.is_set():failed.set();output('gate_execution','FAIL',error_type=type(e).__name__,blocking=True)
 finally:
  done.set();urllib.request.OpenerDirector.open=oldopen
  if watcher:watcher.join(15)
  if proxy:proxy.shutdown();proxy.server_close()
  if tmp:tmp.cleanup()
  subprocess.run(['docker','rm','-fv',NAME],capture_output=True,timeout=30)
  for v in volumes.values():subprocess.run(['docker','volume','rm',v],capture_output=True,timeout=20)
  print(json.dumps({'gate_summary':True,'blocking_failure':failed.is_set(),'tests_observed':len(results),'long_test_allowed':not failed.is_set(),'production_modified':False,'paid_resources_created':False,'external_accounts_created':False}),flush=True)
 return 1 if failed.is_set() else 0
if __name__=='__main__':
 def timeout(*a):raise Deadline()
 signal.signal(signal.SIGALRM,timeout);signal.alarm(540);sys.exit(main())
