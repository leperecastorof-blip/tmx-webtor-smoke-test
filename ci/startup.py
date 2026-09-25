import os,subprocess,secrets,time,json,urllib.request,urllib.error
name='tmx-webtor-smoke'; results=[]
def run(args,**kw):return subprocess.run(args,check=True,capture_output=True,text=True,**kw)
def add(n,ok,**kw):results.append(dict(test=n,pass_=bool(ok),**kw));print(json.dumps(results[-1]),flush=True)
env=os.environ.copy()
for k in ['ADMIN_PASSWORD','PG_PASSWORD','AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY']:env[k]=secrets.token_hex(24)
env.update(DOMAIN='https://localhost',ONLY_AUTHORIZED='true',EMBED_ONLY_AUTHORIZED='true')
try:
 args=['docker','run','-d','--name',name,'--memory=6g','--cpus=2','-p','127.0.0.1:18080:8080']
 for k in ['ADMIN_PASSWORD','PG_PASSWORD','AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','DOMAIN','ONLY_AUTHORIZED','EMBED_ONLY_AUTHORIZED']:args+=['--env',k]
 run(args+['tmx-webtor:test'],env=env)
 healthy=False;state={}
 for _ in range(60):
  state=json.loads(run(['docker','inspect','--format','{{json .State}}',name]).stdout)
  if not state.get('Running'):break
  if state.get('Health',{}).get('Status')=='healthy':healthy=True;break
  time.sleep(5)
 add('container_running',state.get('Running'),oomKilled=state.get('OOMKilled'),exitCode=state.get('ExitCode'))
 add('docker_healthcheck',healthy)
 if healthy:
  r=urllib.request.urlopen('http://127.0.0.1:18080/login',timeout=10);body=r.read().decode()
  add('login_password_form',r.status==200 and 'type="password"' in body)
 logs=run(['docker','logs',name]);alllogs=logs.stdout+logs.stderr
 add('configured_test_secrets_absent_from_logs',not any(env[k] in alllogs for k in ['ADMIN_PASSWORD','PG_PASSWORD','AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY']))
 if not healthy:
  # Emit only whitelisted categories, never raw logs.
  categories=[label for label,needle in [('image_guard','TMX_WEBTOR_GUARD:'),('permission','permission denied'),('out_of_memory','out of memory'),('database','database'),('init_error','s6-rc: warning'),('storage_xattrs','xattr')] if needle.lower() in alllogs.lower()]
  print(json.dumps({'failure_categories':categories}))
 print(json.dumps({'real_authentication':'not_executed_in_startup_phase','video_playback':'not_executed_in_startup_phase'}))
 if not all(r['pass_'] for r in results):raise SystemExit(1)
except Exception as e:
 print(json.dumps({'test':'execution','pass_':False,'error_type':type(e).__name__}));raise SystemExit(1)
finally:
 subprocess.run(['docker','rm','-fv',name],capture_output=True)
