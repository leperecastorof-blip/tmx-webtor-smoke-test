"""Real 30-minute private synthetic HLS endurance. No production, public tunnel or accounts."""
import os,sys,json,time,math,ssl,socket,hashlib,secrets,tempfile,threading,subprocess,http.server,urllib.request,urllib.error,urllib.parse,statistics
from pathlib import Path
import authcheck
from video import bencode
BASE=authcheck.BASE
NAME='tmx-webtor-endurance'
DURATION=1805
results=[];known_secrets=set();processes=[];threads=[];players=[];stats=[];stop_stats=threading.Event()
def emit(item):
 print(json.dumps(item,separators=(',',':')),flush=True)
def result(name,ok=None,**detail):
 r=dict(test=name,status=('impossible' if ok is None else 'passed' if ok else 'failed'),**detail);results.append(r);emit(r);return r
def cmd(args,timeout=120,**kw):return subprocess.run(args,check=True,capture_output=True,text=True,timeout=timeout,**kw)
def attempt(name,fn):
 t=time.monotonic()
 try:
  details=fn() or {};result(name,True,elapsed_s=round(time.monotonic()-t,3),**details)
 except Exception as e:result(name,False,elapsed_s=round(time.monotonic()-t,3),error_type=type(e).__name__)
def require(ok):
 if not ok:raise AssertionError('criterion_not_met')
def wait_healthy(timeout=240):
 deadline=time.monotonic()+timeout
 while time.monotonic()<deadline:
  s=json.loads(cmd(['docker','inspect','--format','{{json .State}}',NAME]).stdout)
  if not s.get('Running'):return False
  if s.get('Health',{}).get('Status')=='healthy':return True
  time.sleep(3)
 return False
class LinkProxy(authcheck.Proxy):
 broken=False;fault_hits=0
 def proxy(self):
  if self.broken and '/torrent-http-proxy/' in self.path:
   type(self).fault_hits+=1
   try:self.connection.shutdown(socket.SHUT_RDWR)
   except OSError:pass
   self.connection.close();return
  super().proxy()
 do_GET=proxy;do_POST=proxy
class Seed(http.server.BaseHTTPRequestHandler):
 files={};modes={};hits={};fault_hits={};mode_until={}
 def log_message(self,*a):pass
 def do_GET(self):
  k=urllib.parse.urlsplit(self.path).path.lstrip('/');self.hits[k]=self.hits.get(k,0)+1
  mode=self.modes.get(k,'normal')
  if k in self.mode_until and time.monotonic()>=self.mode_until[k]:mode='normal'
  if mode=='missing':self.fault_hits[k]=self.fault_hits.get(k,0)+1;self.send_error(404);return
  if k not in self.files:self.send_error(404);return
  raw=self.files[k];start=0;end=len(raw)-1;status=200
  r=self.headers.get('Range','')
  if r.startswith('bytes='):
   a,b=r[6:].split('-',1);start=int(a) if a else 0;end=min(int(b),end) if b else end;status=206
  if start> end or start>=len(raw):self.send_error(416);return
  chunk=raw[start:end+1];self.send_response(status);self.send_header('Content-Type','video/mp4');self.send_header('Accept-Ranges','bytes');self.send_header('Content-Length',str(len(chunk)))
  if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{len(raw)}')
  self.end_headers()
  try:
   if mode=='interrupted':
    self.fault_hits[k]=self.fault_hits.get(k,0)+1;self.wfile.write(chunk[:max(1,min(8192,len(chunk)//4))]);self.wfile.flush();self.connection.shutdown(socket.SHUT_RDWR);self.connection.close();return
   if mode=='slow':
    self.fault_hits[k]=self.fault_hits.get(k,0)+1
    for i in range(0,len(chunk),4096):self.wfile.write(chunk[i:i+4096]);self.wfile.flush();time.sleep(.04)
   else:self.wfile.write(chunk)
  except (OSError,ConnectionError):pass
class QuietServer(http.server.ThreadingHTTPServer):
 def handle_error(self,*a):pass

def monitor():
 while not stop_stats.is_set():
  try:
   j=json.loads(cmd(['docker','stats',NAME,'--no-stream','--format','{{json .}}'],timeout=12).stdout)
   mem=j['MemUsage'].split('/')[0].strip();import re
   m=re.fullmatch(r'([\d.]+)\s*([A-Za-z]+)',mem);require(m is not None)
   factors={'B':1,'kB':1000,'KB':1000,'KiB':1024,'MB':1000**2,'MiB':1024**2,'GB':1000**3,'GiB':1024**3}
   stats.append({'t':time.monotonic(),'cpu_percent_one_core':float(j['CPUPerc'].strip('%')),'working_set_mib':float(m[1])*factors[m[2]]/1024**2})
  except Exception:pass
  stop_stats.wait(15)
class Player:
 def __init__(self,url,ca,seconds,seek=0,realtime=False):
  self.name='tmx-reader-'+secrets.token_hex(4);self.frames=0;self.media_s=0.;self.last_progress=time.monotonic();self.snapshots=[];self.started=time.monotonic();self.stderr='';self.ca=ca
  args=['docker','run','--rm','--name',self.name,'--network','host','--memory=512m','--cpus=1','--mount',f'type=bind,source={ca},target=/test-ca.pem,readonly','--entrypoint','ffmpeg','tmx-webtor:test','-hide_banner','-loglevel','quiet','-nostats','-stats_period','5','-progress','pipe:1','-tls_verify','1','-ca_file','/test-ca.pem','-rw_timeout','10000000','-reconnect','1','-reconnect_streamed','1','-reconnect_on_network_error','1','-reconnect_on_http_error','5xx','-reconnect_delay_max','2']
  if realtime:args+=['-re']
  if seek:args+=['-ss',str(seek)]
  args+=['-i',url,'-t',str(seconds),'-map','0:v:0','-f','null','-']
  self.p=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);players.append(self)
  def read():
   for line in self.p.stdout:
    key,_,value=line.strip().partition('=')
    try:
     if key=='frame':
      n=int(value)
      if n>self.frames:self.last_progress=time.monotonic()
      self.frames=n
     if key=='out_time_us':self.media_s=int(value)/1000000
     if key=='progress':self.snapshots.append({'elapsed_s':round(time.monotonic()-self.started,2),'frames':self.frames,'media_s':round(self.media_s,2)})
    except ValueError:pass
  self.thread=threading.Thread(target=read,daemon=True);self.thread.start()
  def errread():self.stderr=self.p.stderr.read()
  threading.Thread(target=errread,daemon=True).start()
 def finish(self,timeout):
  deadline=time.monotonic()+timeout;next_note=time.monotonic()+120
  while self.p.poll() is None and time.monotonic()<deadline:
   if time.monotonic()>=next_note:emit({'progress':'video_decode','elapsed_s':round(time.monotonic()-self.started,1),'decoded_frames':self.frames,'media_s':round(self.media_s,1)});next_note+=120
   if time.monotonic()-self.last_progress>150:break
   time.sleep(1)
  if self.p.poll() is None:self.stop();raise TimeoutError('decoder_deadline')
  self.thread.join(3);elapsed=time.monotonic()-self.started
  return {'returncode':self.p.returncode,'decoded_frames':self.frames,'decoded_media_s':round(self.media_s,3),'wall_s':round(elapsed,3),'progress_samples':len(self.snapshots)}
 def stop(self):
  subprocess.run(['docker','rm','-f',self.name],capture_output=True,timeout=20)
  if self.p.poll() is None:self.p.terminate()
  try:self.p.wait(timeout=10)
  except subprocess.TimeoutExpired:self.p.kill()

def main():
 env=os.environ.copy();root=tempfile.TemporaryDirectory();p=Path(root.name);proxy=None;ptmp=None;seed=None;session=None;opener=None;ctx=None;api_key=None;stage='setup';baseline=[];long_start=None;long_end=None
 for k in ['ADMIN_PASSWORD','PG_PASSWORD','AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY']:env[k]=secrets.token_hex(24);known_secrets.add(env[k])
 env.update(DOMAIN=BASE,ONLY_AUTHORIZED='true',EMBED_ONLY_AUTHORIZED='true')
 result('public_trusted_https',None,reason='Not_available_in_approved_environment_no_remote_tunnel',local_tls_not_public_https=True)
 result('iphone_safari',None,reason='No_real_iOS_or_representative_Safari_environment')
 try:
  args=['docker','run','-d','--name',NAME,'--restart','unless-stopped','--memory=6g','--cpus=2','-p','127.0.0.1:18080:8080']
  for k in ['ADMIN_PASSWORD','PG_PASSWORD','AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','DOMAIN','ONLY_AUTHORIZED','EMBED_ONLY_AUTHORIZED']:args+=['--env',k]
  cmd(args+['tmx-webtor:test'],env=env);require(wait_healthy());result('startup_healthcheck',True)
  authcheck.Proxy=LinkProxy;proxy,ptmp,ctx=authcheck.start_proxy();ca=str(Path(ptmp.name)/'cert.pem');opener=urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx));authresults=[]
  session=authcheck.test_auth(env,lambda n,ok,**kw:authresults.append({'name':n,'passed':ok}),ctx);known_secrets.update(session['secretvalues']);require(all(v['passed'] for v in authresults));result('authentication_and_denial',True,checks=authresults)
  s,_,body=authcheck.request(session['opener'],'/profile');form=authcheck.Parser();form.feed(body)
  s,_,body=authcheck.request(session['opener'],'/api-credentials/key')
  if s==204:authcheck.request(session['opener'],'/api-credentials/generate',{'_csrf':form.csrf});s,_,body=authcheck.request(session['opener'],'/api-credentials/key')
  require(s==200);api_key=json.loads(body)['key'];known_secrets.add(api_key)
  def api(path,data=None):
   req=urllib.request.Request(BASE+'/api/v1'+path,headers={'Authorization':'Bearer '+api_key,'Content-Type':'application/x-bittorrent'},data=data)
   with opener.open(req,timeout=60) as r:return json.load(r)
  def fetch(url,timeout=30):
   require(urllib.parse.urlsplit(url).netloc=='127.0.0.1:18443')
   with opener.open(url,timeout=timeout) as r:return r.read()
  def denied(url):
   try:
    with opener.open(url,timeout=15) as r:return r.status in [400,401,403,404]
   except urllib.error.HTTPError as e:return e.code in [400,401,403,404]
  require(denied(BASE+'/api/v1/library'));result('api_without_key_denied',True)
  gateway=cmd(['docker','network','inspect','bridge','--format','{{(index .IPAM.Config 0).Gateway}}']).stdout.strip();require(gateway.startswith(('172.','10.','192.168.')))
  seed=QuietServer((gateway,18888),Seed);threading.Thread(target=seed.serve_forever,daemon=True).start()
  def generate(name,duration,frequency):
   cmd(['docker','exec',NAME,'ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=320x240:rate=10','-f','lavfi','-i',f'sine=frequency={frequency}:sample_rate=22050','-t',str(duration),'-c:v','libx264','-preset','ultrafast','-crf','32','-g','20','-pix_fmt','yuv420p','-c:a','aac','-b:a','32k','-movflags','+faststart','-y','/var/lib/webtor/data/'+name],timeout=300)
   cmd(['docker','cp',NAME+':/var/lib/webtor/data/'+name,str(p/name)]);raw=(p/name).read_bytes();Seed.files[name]=raw;return raw
  def resource(name):
   raw=Seed.files[name];info={b'name':name.encode(),b'length':len(raw),b'piece length':32768,b'pieces':b''.join(hashlib.sha1(raw[i:i+32768]).digest() for i in range(0,len(raw),32768)),b'private':1}
   tor=bencode({b'info':info,b'url-list':[f'http://{gateway}:18888/{name}'.encode()]});rid=api('/resource',tor)['id'];listing=api('/resource/'+rid+'/list?path=/')
   def walk(d):
    for x in d.get('items',[]):yield x;yield from walk(x)
   item=next(x for x in walk(listing) if x.get('name')==name)
   def export():
    u=api('/resource/'+rid+'/export/'+str(item['id']))['exports']['stream']['url'];require(urllib.parse.urlsplit(u).netloc=='127.0.0.1:18443');known_secrets.update(v for values in urllib.parse.parse_qs(urllib.parse.urlsplit(u).query).values() for v in values if len(v)>=16);return u
   return rid,export
  def play(url,seconds=3,seek=0,realtime=False,timeout=120):
   player=Player(url,ca,seconds,seek,realtime);data=player.finish(timeout);require(data['returncode']==0 and data['decoded_frames']>=int(seconds*10)-2);return data
  stage='synthetic_fixture';raw=generate('endurance.mp4',1920,440);rid,export=resource('endurance.mp4');url=export();require(fetch(url).startswith(b'#EXTM3U'));result('synthetic_hls_setup',True,duration_s=1920,video_bytes=len(raw),resolution='320x240',fps=10)
  attempt('hls_without_signature_denied',lambda:{'denied':require(denied(urllib.parse.urlunsplit(urllib.parse.urlsplit(url)._replace(query='')))) is None})
  def series():
   times=[]
   for _ in range(20):
    t=time.monotonic();api('/library');times.append((time.monotonic()-t)*1000)
   return times
  baseline=series();result('requests_before_endurance',True,count=20,median_ms=round(statistics.median(baseline),3),p95_ms=round(sorted(baseline)[18],3))
  attempt('seek_forward_protocol',lambda:dict(target_s=900,**play(url,3,900)))
  attempt('seek_backward_protocol',lambda:dict(target_s=120,**play(url,3,120)))
  thread=threading.Thread(target=monitor,daemon=True);thread.start();threads.append(thread)
  stage='long_playback';long_start=time.monotonic()
  try:
   reader=Player(url,ca,DURATION,realtime=True);data=reader.finish(1990);long_end=time.monotonic();gaps=[b['elapsed_s']-a['elapsed_s'] for a,b in zip(reader.snapshots,reader.snapshots[1:]) if b['frames']>a['frames']]
   ok=data['returncode']==0 and data['decoded_frames']>=18000 and data['decoded_media_s']>=1800 and data['wall_s']>=1800 and len(reader.snapshots)>=100 and (max(gaps,default=999)<=60)
   result('hls_30_minutes_realtime',ok,**data,max_progress_gap_s=round(max(gaps,default=0),2),frames_are_measured=True,player='FFmpeg_not_browser')
  except Exception as e:long_end=time.monotonic();result('hls_30_minutes_realtime',False,error_type=type(e).__name__,wall_s=round(long_end-long_start,2))
  def repeats():
   after=series();b95=sorted(baseline)[18];a95=sorted(after)[18];require(a95<=max(3*b95,2000));return {'count':20,'before_p95_ms':round(b95,3),'after_p95_ms':round(a95,3),'after_median_ms':round(statistics.median(after),3),'threshold_ms':round(max(3*b95,2000),3)}
  attempt('requests_after_endurance',repeats)
  def network():
   old=LinkProxy.fault_hits;u=export();on=threading.Timer(5,lambda:setattr(LinkProxy,'broken',True));off=threading.Timer(20,lambda:setattr(LinkProxy,'broken',False));on.start();off.start()
   try:data=play(u,40,realtime=True,timeout=100);require(LinkProxy.fault_hits>old);return dict(injected_tcp_outage_s=15,connections_dropped=LinkProxy.fault_hits-old,**data)
   finally:LinkProxy.broken=False;on.cancel();off.cancel()
  attempt('network_tcp_cut_and_player_recovery',network)
  def renewal():
   oldcookie=set(session['secretvalues']);checks=[];authcheck.test_logout(session,lambda n,ok,**kw:checks.append(ok));require(all(checks));new=authcheck.test_auth(env,lambda n,ok,**kw:checks.append(ok),ctx);known_secrets.update(new['secretvalues']);require(all(checks));session.update(new);require(authcheck.request(session['opener'],'/profile')[0]==200);return {'logout_and_relogin':True,'natural_time_expiry_tested':False,'profile_after_renewal':200}
  attempt('session_renewal_and_reconnection',renewal)
  def restart():
   marker=secrets.token_hex(24);cmd(['docker','exec',NAME,'sh','-c','printf %s "$1" > /var/lib/webtor/data/validation-marker','sh',marker]);cmd(['docker','restart',NAME],timeout=90);require(wait_healthy());value=cmd(['docker','exec',NAME,'cat','/var/lib/webtor/data/validation-marker']).stdout;require(value==marker);api('/library');api('/resource/'+rid+'/list?path=/');data=play(export(),3);return dict(storage_scope='same_container_restart_not_recreation_or_permanent_disk',marker_preserved=True,api_key_preserved=True,**data)
  attempt('service_restart_and_playback',restart)
  for name,mode,freq in [('slow.mp4','slow',510),('interrupted.mp4','interrupted',620),('missing.mp4','missing',730)]:
   def fault(name=name,mode=mode,freq=freq):
    generate(name,12,freq);Seed.modes[name]=mode
    if mode=='interrupted':Seed.mode_until[name]=time.monotonic()+15
    _,out=resource(name);u=out()
    if mode=='missing':
     try:fetch(u,timeout=25);outcome='unexpected_media'
     except urllib.error.HTTPError as e:outcome='http_'+str(e.code)
     except Exception as e:outcome='client_'+type(e).__name__
     count=Seed.fault_hits.get(name,0);api('/library');ok=count>0 and outcome.startswith(('http_4','http_5'));result('source_unavailable_behavior',ok,observed=outcome,source_fault_requests=count,service_responds_after_error=True);return
    data=play(u,3,timeout=150);count=Seed.fault_hits.get(name,0);require(count>0);return dict(controlled_fault=mode,source_fault_requests=count,latency_per_4096_bytes_s=.04 if mode=='slow' else None,recovery_after_s=15 if mode=='interrupted' else None,**data)
   if mode=='missing':
    try:fault()
    except Exception as e:result('source_unavailable_behavior',False,error_type=type(e).__name__,source_fault_requests=Seed.fault_hits.get(name,0))
   else:attempt('source_'+mode+'_decode',fault)
  stage='completed'
 except BaseException as e:result('suite_execution',False,stage=stage,error_type=type(e).__name__)
 finally:
  LinkProxy.broken=False;stop_stats.set()
  for t in threads:t.join(15)
  for player in players:
   if player.p.poll() is None:player.stop()
  if stats:
   window=[x for x in stats if long_start is not None and x['t']>=long_start and (long_end is None or x['t']<=long_end)]
   if window:
    cpu=[x['cpu_percent_one_core'] for x in window];mem=[x['working_set_mib'] for x in window]
    emit({'measurement':'webtor_resources_during_long_playback','samples':len(window),'span_s':round(window[-1]['t']-window[0]['t'],2),'cpu_percent_one_core_mean':round(statistics.mean(cpu),3),'cpu_percent_one_core_peak':max(cpu),'memory_working_set_mib_mean':round(statistics.mean(mem),3),'memory_working_set_mib_peak':max(mem),'memory_first_5_samples_mean_mib':round(statistics.mean(mem[:5]),3),'memory_last_5_samples_mean_mib':round(statistics.mean(mem[-5:]),3),'limits':{'cpus':2,'memory_gib':6},'scope':'Webtor_container_only_decoder_separate'})
  try:
   r=subprocess.run(['docker','exec',NAME,'cat','/etc/webtor/secrets/api.env'],capture_output=True,text=True,timeout=15)
   for line in r.stdout.splitlines():
    k,sep,v=line.removeprefix('export ').partition('=');v=v.strip().strip('\"\'')
    if sep and len(v)>=16 and any(x in k for x in ['KEY','SECRET','PASSWORD']):known_secrets.add(v)
   r=cmd(['docker','logs',NAME],timeout=20);logs=r.stdout+r.stderr;variants=set()
   for v in known_secrets:
    if len(v)>=16:variants.update([v,urllib.parse.quote(v,safe=''),urllib.parse.quote_plus(v),urllib.parse.unquote(v)])
   server_leaks=sum(1 for v in variants if v and v in logs);decoder_leaks=sum(1 for v in variants if v and any(v in pl.stderr for pl in players))
   result('secret_values_absent_from_logs',server_leaks==0 and decoder_leaks==0,checked_values=len(known_secrets),server_value_matches=server_leaks,decoder_value_matches=decoder_leaks,no_raw_logs_published=True)
  except Exception as e:result('secret_values_absent_from_logs',False,error_type=type(e).__name__)
  if seed:seed.shutdown();seed.server_close()
  if proxy:proxy.shutdown();proxy.server_close()
  if ptmp:ptmp.cleanup()
  subprocess.run(['docker','rm','-fv',NAME],capture_output=True,timeout=30);root.cleanup()
  emit({'summary':True,'passed':[r['test'] for r in results if r['status']=='passed'],'failed':[r['test'] for r in results if r['status']=='failed'],'impossible':[r['test'] for r in results if r['status']=='impossible'],'production_eligible':False,'tmx_production_unchanged':True,'paid_resources_created':False,'external_accounts_created':False,'natural_session_expiry_tested':False,'iphone_compatibility':'not_validated'})
 return 1 if any(r['status']=='failed' for r in results) else 0
if __name__=='__main__':
 import signal
 class SuiteDeadline(BaseException):pass
 def abort(*args):raise SuiteDeadline()
 signal.signal(signal.SIGALRM,abort);signal.signal(signal.SIGTERM,abort);signal.alarm(3300)
 sys.exit(main())
