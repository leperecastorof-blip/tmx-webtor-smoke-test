"""Synthetic H264 -> local webseed -> authenticated Webtor API -> HLS -> decoded frames.
Derived from documented endpoint usage in webtor-io/self-hosted tests/scenarios/30-hls.sh.
No public swarms, trackers, copyrighted media, or raw log output.
"""
import hashlib,json,threading,http.server,urllib.request,urllib.error,urllib.parse,tempfile,subprocess,time
from pathlib import Path
from authcheck import BASE,Parser,request

def bencode(v):
 if isinstance(v,int):return b'i'+str(v).encode()+b'e'
 if isinstance(v,str):v=v.encode()
 if isinstance(v,bytes):return str(len(v)).encode()+b':'+v
 if isinstance(v,list):return b'l'+b''.join(bencode(x) for x in v)+b'e'
 if isinstance(v,dict):return b'd'+b''.join(bencode(k)+bencode(v[k]) for k in sorted(v))+b'e'
 raise TypeError('unsupported')
def test_video(session,add,ctx,run):
 name='tmx-webtor-smoke';server=None;stage='create_fixture'
 try:
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)
   run(['docker','exec',name,'ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=320x240:rate=24','-t','4','-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart','-y','/var/lib/webtor/data/tmx-synthetic-source.mp4'])
   run(['docker','cp',name+':/var/lib/webtor/data/tmx-synthetic-source.mp4',str(p/'video.mp4')]);raw=(p/'video.mp4').read_bytes();assert len(raw)<2000000
   hits=[]
   class Seed(http.server.BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def do_GET(self):
     if self.path!='/video.mp4':self.send_error(404);return
     start=0;end=len(raw)-1;status=200
     rh=self.headers.get('Range','')
     if rh.startswith('bytes='):
      a,b=rh[6:].split('-',1);start=int(a) if a else 0;end=min(int(b),end) if b else end;status=206
     chunk=raw[start:end+1];self.send_response(status);self.send_header('Content-Type','video/mp4');self.send_header('Accept-Ranges','bytes');self.send_header('Content-Length',str(len(chunk)))
     if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{len(raw)}')
     self.end_headers();self.wfile.write(chunk);hits.append(len(chunk))
   gateway=run(['docker','network','inspect','bridge','--format','{{(index .IPAM.Config 0).Gateway}}']).stdout.strip()
   assert gateway.startswith('172.') or gateway.startswith('10.')
   server=http.server.ThreadingHTTPServer((gateway,18888),Seed);threading.Thread(target=server.serve_forever,daemon=True).start()
   info={b'name':b'video.mp4',b'length':len(raw),b'piece length':32768,b'pieces':b''.join(hashlib.sha1(raw[i:i+32768]).digest() for i in range(0,len(raw),32768)),b'private':1}
   torrent=bencode({b'info':info,b'url-list':[f'http://{gateway}:18888/video.mp4'.encode()]})
   stage='api_key'
   status,_,body=request(session['opener'],'/profile');assert status==200;pform=Parser();pform.feed(body)
   stage='api_key_read'
   status,_,body=request(session['opener'],'/api-credentials/key')
   print(json.dumps({'diagnostic':'key_lookup','status':status}),flush=True)
   if status==204:
    stage='api_key_generate'
    status,_,_=request(session['opener'],'/api-credentials/generate',{'_csrf':pform.csrf})
    print(json.dumps({'diagnostic':'key_generation','status':status}),flush=True)
    assert status in [200,201,202,204,302,303,307]
    stage='api_key_retrieve'
    status,_,body=request(session['opener'],'/api-credentials/key')
   assert status==200;key=json.loads(body)['key'];session['secretvalues'].append(key)
   opener=urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
   def api(path,data=None):
    req=urllib.request.Request(BASE+'/api/v1'+path,headers={'Authorization':'Bearer '+key,'Content-Type':'application/x-bittorrent'},data=data)
    with opener.open(req,timeout=90) as r:return json.load(r)
   # Confirm the same public API rejects an anonymous request before using the key.
   try:r=opener.open(BASE+'/api/v1/library',timeout=15);anon_status=r.status
   except urllib.error.HTTPError as e:anon_status=e.code
   add('api_denies_without_key',anon_status in [401,403],status=anon_status)
   stage='store_torrent';resource=api('/resource',torrent);rid=resource['id'];listing=api('/resource/'+rid+'/list?path=/')
   def walk(d):
    for x in d.get('items',[]):yield x;yield from walk(x)
   file=next(x for x in walk(listing) if x.get('name')=='video.mp4')
   stage='export_hls';export=api('/resource/'+rid+'/export/'+str(file['id']));url=export['exports']['stream']['url']
   assert urllib.parse.urlsplit(url).netloc=='127.0.0.1:18443'
   def fetch(url,timeout=120):
    # Signed links never appear in logs or assertion strings.
    assert urllib.parse.urlsplit(url).netloc=='127.0.0.1:18443'
    end=time.monotonic()+timeout
    while True:
     try:
      with opener.open(url,timeout=45) as r:return r.read()
     except Exception:
      if time.monotonic()>=end:raise RuntimeError('stream_timeout')
      time.sleep(3)
   stage='hls_playlist';playlist=fetch(url);assert playlist.startswith(b'#EXTM3U')
   for _ in range(3):
    entry=next(l.strip() for l in playlist.decode().splitlines() if l.strip() and not l.startswith('#'));child=urllib.parse.urljoin(url,entry)
    if '.m3u8' in urllib.parse.urlsplit(child).path:url=child;playlist=fetch(url);continue
    break
   stage='hls_segment';segment=fetch(child);assert len(segment)>1000;(p/'segment.ts').write_bytes(segment)
   run(['docker','cp',str(p/'segment.ts'),name+':/var/lib/webtor/data/tmx-hls-segment.ts'])
   stage='decode_segment';probe=json.loads(run(['docker','exec',name,'ffprobe','-v','error','-select_streams','v:0','-count_frames','-show_entries','stream=codec_name,width,height,nb_read_frames','-of','json','/var/lib/webtor/data/tmx-hls-segment.ts']).stdout)
   stream=probe['streams'][0];assert stream['codec_name']=='h264' and stream['width']==320 and stream['height']==240;frames=int(stream['nb_read_frames']);assert frames>0
   run(['docker','exec',name,'ffmpeg','-hide_banner','-loglevel','error','-i','/var/lib/webtor/data/tmx-hls-segment.ts','-f','null','-'])
   assert hits
   add('webtor_real_hls_decoded',True,codec=stream['codec_name'],width=stream['width'],height=stream['height'],frames=frames,segmentBytes=len(segment),webseedRequests=len(hits),syntheticVideo=True)
   return True
 except Exception as e:
  add('webtor_real_hls_decoded',False,stage=stage,error_type=type(e).__name__)
  return False
 finally:
  if server:server.shutdown();server.server_close()
