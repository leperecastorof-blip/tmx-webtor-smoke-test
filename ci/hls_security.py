"""Negative HLS checks on synthetic media only. Never print URLs, keys or token values."""
import base64,hashlib,hmac,json,shlex,time,urllib.request,urllib.error,urllib.parse

def verify(targets,ctx,run,known,output):
 from authcheck import NoRedirect
 opener=urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),NoRedirect())
 def request(url):
  try:r=opener.open(url,timeout=25)
  except urllib.error.HTTPError as e:r=e
  with r:return r.status,r.read(250000)
 selected={}
 for url in targets:
  u=urllib.parse.urlsplit(url)
  if u.netloc!='127.0.0.1:18443':continue
  kind='playlist' if u.path.endswith('.m3u8') else ('segment' if u.path.endswith('.ts') else None)
  if kind and kind not in selected:selected[kind]=url
 output('hls_negative_setup',set(selected)=={'playlist','segment'})
 env=run(['docker','exec','tmx-webtor-smoke','sh','-c','cat /etc/webtor/secrets/api.env']).stdout
 secrets=[]
 for line in env.splitlines():
  key,sep,value=line.removeprefix('export ').partition('=')
  if sep and 'SECRET' in key:
   value=shlex.split(value)[0] if value.strip() else ''
   if len(value)>=16:secrets.append(value.encode());known.add(value)
 def b64(v):return base64.urlsafe_b64encode(v).decode().rstrip('=')
 def dec(v):return base64.urlsafe_b64decode(v+'='*(-len(v)%4))
 for kind,url in selected.items():
  u=urllib.parse.urlsplit(url);pairs=urllib.parse.parse_qsl(u.query,keep_blank_values=True)
  names=[k for k,v in pairs if k.lower() in ['token','sig','signature']]
  status,_=request(urllib.parse.urlunsplit(u._replace(query='')))
  output('hls_token_absent',status in [400,401,403,404],resource=kind,http_status=status)
  output('hls_signature_parameter_identified',bool(names),resource=kind)
  bad=[]
  for k,v in pairs:
   if k in names and v:
    n=len(v)//2;v=v[:n]+('B' if v[n]=='A' else 'A')+v[n+1:];known.add(v)
   bad.append((k,v))
  status,_=request(urllib.parse.urlunsplit(u._replace(query=urllib.parse.urlencode(bad))))
  output('hls_token_invalid',status in [400,401,403,404],resource=kind,http_status=status,other_parameters_preserved=True)
  # An expiry check is valid only if the signing secret matches the observed positive token.
  found=None
  for name,token in pairs:
   if name not in names or token.count('.')!=2:continue
   try:
    a,b,c=token.split('.');header=json.loads(dec(a));payload=json.loads(dec(b));alg={'HS256':hashlib.sha256,'HS384':hashlib.sha384,'HS512':hashlib.sha512}.get(header.get('alg'))
    if not alg or 'exp' not in payload:continue
    for secret in secrets:
     if hmac.compare_digest(hmac.new(secret,(a+'.'+b).encode(),alg).digest(),dec(c)):found=(name,a,payload,alg,secret);break
   except (ValueError,TypeError):continue
   if found:break
  if not found:
   output('hls_token_expired','NON TESTÉ',resource=kind,reason='No verified signing key and supported exp claim; do not fabricate an expiry test')
   continue
  name,a,payload,alg,secret=found;payload=dict(payload);now=int(time.time())
  if 'iat' in payload:payload['iat']=now-600
  if 'nbf' in payload:payload['nbf']=now-600
  def signed(delta):
   claims={**payload,'exp':now+delta};b=b64(json.dumps(claims,separators=(',',':')).encode());data=a+'.'+b;token=data+'.'+b64(hmac.new(secret,data.encode(),alg).digest());known.add(token)
   return urllib.parse.urlunsplit(u._replace(query=urllib.parse.urlencode([(k,token if k==name else v) for k,v in pairs])))
  status,body=request(signed(120));media=body.startswith(b'#EXTM3U') if kind=='playlist' else body.startswith(b'\x47')
  output('hls_expiry_positive_control',status==200 and media,resource=kind,http_status=status)
  status,_=request(signed(-120))
  output('hls_token_expired',status in [400,401,403,404],resource=kind,http_status=status,method='correct_signature_expired_claim_with_matching_fresh_positive_control')
