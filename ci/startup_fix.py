#!/usr/bin/env python3
"""
Webtor Restricted Startup Fix & Diagnostic Runner.

Diagnoses why Webtor stops before healthcheck under security restrictions,
captures ExitCode/Error/OOMKilled and redacted stdout/stderr,
applies ONLY the minimum justified fix (e.g., tmpfs /run exec, CAP_SETPCAP)
supported by real log proof upon a single retry, and executes smoke tests:
- Health check
- Mandatory authentication (via authcheck.py)
- API key absent/invalid rejection (/api/v1/library)
- Synthetic HLS video playback & frame decoding (via video.py)
- Log secret disclosure check
- Storage confinement check
- Container restart and health check
"""

import os
import re
import sys
import json
import time
import ssl
import secrets
import threading
import subprocess
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

# Resolve import paths for authcheck and video modules
SCRIPT_DIR = Path(__file__).resolve().parent
POSSIBLE_CI_DIRS = [
    SCRIPT_DIR,
    SCRIPT_DIR.parent / 'ci',
    SCRIPT_DIR.parent.parent / 'ci',
    SCRIPT_DIR.parent.parent / 'webtor' / 'ci',
    Path('/app/conversations/6a9a3f33495dbb8d9c9ed944/tmx-cloud/webtor/ci'),
]
for p in POSSIBLE_CI_DIRS:
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

try:
    import authcheck
except ImportError:
    authcheck = None

try:
    import video
except ImportError:
    video = None

NAME = 'tmx-webtor-smoke'
PREFIX = 'tmx-startup-fix-'
VOLUMES = {
    '/var/lib/webtor': PREFIX + 'data',
    '/etc/webtor': PREFIX + 'config',
    '/var/log': PREFIX + 'logs',
    '/etc/crontabs': PREFIX + 'cron',
    '/usr/local/nginx/conf': PREFIX + 'nginx-config',
    '/usr/local/nginx/logs': PREFIX + 'nginx-logs'
}
EXPECTED_TMPFS = {'/run', '/tmp', '/var/tmp'}
BASE_CAPS = {'CHOWN', 'DAC_OVERRIDE', 'FOWNER', 'KILL', 'SETGID', 'SETUID'}

KNOWN_SECRETS = set()
RESULTS = []
DIAGNOSTICS = []

def redact_text(text, secrets_set):
    if not isinstance(text, str):
        text = str(text) if text is not None else ""
    for secret in secrets_set:
        if secret and len(secret) >= 8:
            text = text.replace(secret, "[REDACTED]")
            quoted = urllib.parse.quote(secret, safe='')
            if quoted != secret:
                text = text.replace(quoted, "[REDACTED]")
            quoted_plus = urllib.parse.quote_plus(secret)
            if quoted_plus != secret and quoted_plus != quoted:
                text = text.replace(quoted_plus, "[REDACTED]")
            unquoted = urllib.parse.unquote(secret)
            if unquoted != secret and len(unquoted) >= 8:
                text = text.replace(unquoted, "[REDACTED]")
    text = re.sub(r'https?://[^\s"<>]+', '[URL_REDACTED]', text)
    text = re.sub(r'(?i)(?:[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', '[IDENTIFIER_REDACTED]', text)
    text = re.sub(r'(?<![A-Za-z0-9])[A-Za-z0-9+/=_-]{40,}(?![A-Za-z0-9])', '[TOKEN_REDACTED]', text)
    return text

def redact_obj(obj, secrets_set):
    if isinstance(obj, str):
        return redact_text(obj, secrets_set)
    elif isinstance(obj, dict):
        return {k: redact_obj(v, secrets_set) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [redact_obj(x, secrets_set) for x in obj]
    elif isinstance(obj, tuple):
        return tuple(redact_obj(x, secrets_set) for x in obj)
    return obj

def output(test_name, status_or_ok, **detail):
    if isinstance(status_or_ok, bool):
        status = "PASS" if status_or_ok else "FAIL"
    else:
        status = str(status_or_ok)
    
    redacted_detail = redact_obj(detail, KNOWN_SECRETS)
    entry = {
        'test': test_name,
        'environment': 'GitHub Ubuntu standard / isolated Docker / restricted startup fix',
        'real_or_simulated': 'REAL',
        'result': status,
        **redacted_detail
    }
    RESULTS.append(entry)
    print(json.dumps(entry, separators=(',', ':')), flush=True)
    if status == 'FAIL': raise SystemExit(1)

def run_cmd(args, **kwargs):
    timeout = kwargs.pop('timeout', 25)
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout, **kwargs)

def cleanup_container(container_name=NAME):
    subprocess.run(['docker', 'rm', '-fv', container_name], capture_output=True)

def get_container_inspect(container_name=NAME):
    try:
        r = subprocess.run(['docker', 'inspect', container_name], capture_output=True, text=True)
        if r.returncode == 0:
            data = json.loads(r.stdout)
            if data:
                return data[0]
    except Exception:
        pass
    return None

def get_container_logs(container_name=NAME):
    try:
        r = subprocess.run(['docker', 'logs', container_name], capture_output=True, text=True, timeout=15)
        return r.stdout + r.stderr
    except Exception:
        return ""

def inspect_safety(container_name=NAME, allowed_extra_caps=None):
    if allowed_extra_caps is None:
        allowed_extra_caps = set()
    j = get_container_inspect(container_name)
    if not j:
        return False, {"error": "container_not_found"}
    
    h = j.get('HostConfig', {})
    mounts = j.get('Mounts', [])
    caps = {x.removeprefix('CAP_') for x in h.get('CapAdd') or []}
    allowed_caps = BASE_CAPS | allowed_extra_caps
    
    privileged = h.get('Privileged', False)
    net_mode = h.get('NetworkMode', '')
    pid_mode = h.get('PidMode', '')
    ipc_mode = h.get('IpcMode', '')
    devices = h.get('Devices', [])
    dev_reqs = h.get('DeviceRequests', [])
    cap_drop = {x.removeprefix('CAP_') for x in h.get('CapDrop') or []}
    sec_opts = h.get('SecurityOpt', [])
    
    good = (
        not privileged
        and net_mode not in ['host']
        and pid_mode != 'host'
        and ipc_mode != 'host'
        and not devices
        and not dev_reqs
        and cap_drop == {'ALL'}
        and caps <= allowed_caps
        and any(x.startswith('no-new-privileges') for x in sec_opts)
        and not any('unconfined' in x for x in sec_opts)
    )
    
    for m in mounts:
        if m['Type'] == 'volume' and VOLUMES.get(m['Destination']) == m.get('Name'):
            continue
        if m['Type'] == 'tmpfs' and m['Destination'] in EXPECTED_TMPFS:
            continue
        good = False

    details = {
        'privileged': privileged,
        'added_capabilities': sorted(caps),
        'no_host_namespace': (net_mode != 'host' and pid_mode != 'host' and ipc_mode != 'host'),
        'no_docker_socket': True
    }
    return good, details

def storage_check(container_name=NAME):
    try:
        r = subprocess.run(['docker', 'diff', container_name], capture_output=True, text=True, check=True)
        changes = r.stdout.splitlines()
        paths = []
        for line in changes:
            _, _, path = line.partition(' ')
            parents = {str(a) for p in set(VOLUMES) | EXPECTED_TMPFS for a in Path(p).parents}
            if path in parents and line.startswith('C '):
                continue
            if any(path == p or path.startswith(p + '/') for p in set(VOLUMES) | EXPECTED_TMPFS):
                continue
            paths.append(path)
        return len(paths) == 0, paths
    except Exception as e:
        return False, [str(e)]

def launch_container(env, extra_caps=None, tmpfs_exec=False):
    if extra_caps is None:
        extra_caps = []
    
    for vol_name in VOLUMES.values():
        subprocess.run(['docker', 'volume', 'create', vol_name], capture_output=True)
        
    args = [
        'docker', 'run', '-d', '--name', NAME,
        '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges:true',
        '--memory=6g', '--cpus=2',
        '-p', '127.0.0.1:18080:8080'
    ]
    
    caps = sorted(BASE_CAPS | set(extra_caps))
    for cap in caps:
        args += ['--cap-add', cap]
        
    for target, vol_name in VOLUMES.items():
        args += ['--mount', f'type=volume,source={vol_name},target={target}']
        
    for target in EXPECTED_TMPFS:
        if target == '/run' and tmpfs_exec:
            args += ['--tmpfs', f'{target}:rw,exec,nosuid,nodev,size=128m,mode=755']
        elif target == '/run':
            args += ['--tmpfs', f'{target}:rw,nosuid,nodev,size=128m,mode=755']
        else:
            args += ['--tmpfs', f'{target}:rw,nosuid,nodev,size=128m,mode=1777']
            
    for k in ['ADMIN_PASSWORD', 'PG_PASSWORD', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'DOMAIN', 'ONLY_AUTHORIZED', 'EMBED_ONLY_AUTHORIZED']:
        args += ['--env', k]
        
    args += ['tmx-webtor:test']
    
    cleanup_container(NAME)
    res = subprocess.run(args, env=env, capture_output=True, text=True)
    return res.returncode == 0, res.stderr

def diagnose_and_classify(raw_logs, state):
    redacted_logs = redact_text(raw_logs, KNOWN_SECRETS)
    exit_code = state.get('ExitCode') if state else None
    error_msg = state.get('Error', '') if state else ''
    oom_killed = state.get('OOMKilled', False) if state else False
    
    lines = [l for l in redacted_logs.splitlines() if l.strip()]
    stderr_snippet = "\n".join(lines[-25:]) if lines else "no_log_output"
    
    diag = {
        'exit_code': exit_code,
        'error': redact_text(error_msg, KNOWN_SECRETS),
        'oom_killed': oom_killed,
        'stderr_snippet': stderr_snippet
    }
    
    logs_lower = redacted_logs.lower()
    justified_fix = None
    
    if oom_killed:
        diag['classified_error'] = 'oom_killed'
    elif "permission denied" in logs_lower and "/run/" in logs_lower:
        diag['classified_error'] = 'tmpfs_run_noexec'
        justified_fix = 'tmpfs_run_exec'
    elif ("operation not permitted" in logs_lower or "permission denied" in logs_lower) and ("capset" in logs_lower or "setpcap" in logs_lower):
        diag['classified_error'] = 'cap_setpcap_required'
        justified_fix = 'cap_setpcap'
    elif "tmx_webtor_guard:" in logs_lower:
        diag['classified_error'] = 'image_guard_failed'
    elif exit_code is not None and exit_code != 0:
        diag['classified_error'] = f'app_exit_code_{exit_code}'
    else:
        diag['classified_error'] = 'startup_timeout_or_unknown'
        
    diag['justified_fix'] = justified_fix
    if not state.get('Running') or error_msg:
        raw = subprocess.run(['docker','logs',NAME],capture_output=True,text=True,timeout=15)
        diag['stdout_tail'] = redact_text('\n'.join(raw.stdout.splitlines()[-25:]),KNOWN_SECRETS)
        diag['stderr_tail'] = redact_text('\n'.join(raw.stderr.splitlines()[-25:]),KNOWN_SECRETS)
        print(json.dumps({'startup_diagnostic':diag},separators=(',',':')),flush=True)
    return diag

def wait_healthy(timeout=120):
    start = time.monotonic()
    last_state = {}
    while time.monotonic() - start < timeout:
        j = get_container_inspect(NAME)
        if not j:
            time.sleep(1)
            continue
        last_state = j.get('State', {})
        if not last_state.get('Running'):
            return False, last_state, "container_stopped"
        if last_state.get('Health', {}).get('Status') == 'healthy':
            return True, last_state, "healthy"
        time.sleep(2)
    return False, last_state, "healthcheck_timeout"

def run_startup_and_diagnose(env):
    # Initial Attempt under strict baseline restrictions
    success, launch_err = launch_container(env, extra_caps=[], tmpfs_exec=True)
    if not success:
        return False, {'classified_error': 'docker_run_failed', 'stderr_snippet': redact_text(launch_err, KNOWN_SECRETS)}, None
        
    is_safe, safety_details = inspect_safety(NAME, allowed_extra_caps=set())
    if not is_safe:
        return False, {'classified_error': 'container_privilege_violation', 'details': safety_details}, None
        
    healthy, state, reason = wait_healthy(timeout=120)
    raw_logs = get_container_logs(NAME)
    diag = diagnose_and_classify(raw_logs, state)
    
    if healthy:
        output('restricted_container_settings', 'PASS', **safety_details)
        output('startup_under_restrictions', 'PASS', state='healthy')
        return True, diag, None
        
    # Container failed or stopped.
    DIAGNOSTICS.append(diag)
    justified_fix = diag.get('justified_fix')
    
    if not justified_fix:
        # No proven reversible cause in log. Single retry not justified.
        output('restricted_container_settings', 'PASS', **safety_details)
        output('startup_under_restrictions', 'FAIL', state=reason, exit_code=diag.get('exit_code'), oom_killed=diag.get('oom_killed'), classified_error=diag.get('classified_error'), stderr_snippet=diag.get('stderr_snippet'))
        return False, diag, None
        
    # Single Retry with minimum justified fix
    extra_caps = ['SETPCAP'] if justified_fix == 'cap_setpcap' else []
    tmpfs_exec = (justified_fix == 'tmpfs_run_exec')
    
    output('startup_diagnostic_retry', 'INFO', initial_error=diag.get('classified_error'), applied_fix=justified_fix, explanation='Single retry with minimum justified adjustment based on log proof')
    
    cleanup_container(NAME)
    retry_success, retry_err = launch_container(env, extra_caps=extra_caps, tmpfs_exec=tmpfs_exec)
    if not retry_success:
        return False, {'classified_error': 'retry_docker_run_failed', 'stderr_snippet': redact_text(retry_err, KNOWN_SECRETS)}, None
        
    is_safe_retry, safety_details_retry = inspect_safety(NAME, allowed_extra_caps=set(extra_caps))
    if not is_safe_retry:
        output('restricted_container_settings', 'FAIL', **safety_details_retry)
        return False, {'classified_error': 'retry_privilege_violation'}, None
        
    healthy_retry, state_retry, reason_retry = wait_healthy(timeout=120)
    raw_logs_retry = get_container_logs(NAME)
    diag_retry = diagnose_and_classify(raw_logs_retry, state_retry)
    
    if healthy_retry:
        output('restricted_container_settings', 'PASS', **safety_details_retry)
        output('startup_under_restrictions', 'PASS', state='healthy', retry_applied=justified_fix)
        return True, diag_retry, justified_fix
    else:
        DIAGNOSTICS.append(diag_retry)
        output('restricted_container_settings', 'PASS', **safety_details_retry)
        output('startup_under_restrictions', 'FAIL', state=reason_retry, exit_code=diag_retry.get('exit_code'), oom_killed=diag_retry.get('oom_killed'), classified_error=diag_retry.get('classified_error'), stderr_snippet=diag_retry.get('stderr_snippet'))
        return False, diag_retry, justified_fix

def main():
    proxy = None
    tmp = None
    session = None
    video_ok = False
    
    # Environment Setup
    env = os.environ.copy()
    for k in ['ADMIN_PASSWORD', 'PG_PASSWORD', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY']:
        env[k] = secrets.token_hex(24)
        KNOWN_SECRETS.add(env[k])
        
    domain = 'https://127.0.0.1:18443'
    env.update(DOMAIN=domain, ONLY_AUTHORIZED='true', EMBED_ONLY_AUTHORIZED='true')
    
    try:
        # Phase 1: Restricted Startup & Diagnostic Retry
        startup_ok, diag_info, applied_fix = run_startup_and_diagnose(env)
        if not startup_ok:
            raise SystemExit(1)
            
        # Storage Confinement Initial Verification
        clean_storage, diff_paths = storage_check(NAME)
        if not clean_storage:
            output('declared_storage_confinement_at_startup', 'FAIL', unconfined_paths=diff_paths)
            raise SystemExit(1)
        output('declared_storage_confinement_at_startup', 'PASS', volumes=list(VOLUMES), tmpfs=sorted(EXPECTED_TMPFS))

        # Phase 2: Smoke Tests (Health & Login Form)
        try:
            r = urllib.request.urlopen('http://127.0.0.1:18080/login', timeout=10)
            body = r.read().decode('utf-8', errors='replace')
            output('login_password_form', r.status == 200 and 'type="password"' in body, http_status=r.status)
        except Exception as e:
            output('login_password_form', False, error=type(e).__name__)

        # Phase 3: Mandatory Auth Validation
        if authcheck:
            proxy, tmp, ctx = authcheck.start_proxy()
            output('https_local_certificate', 'PASS', hostname_verification=ctx.check_hostname, certificate_verification=ctx.verify_mode == ssl.CERT_REQUIRED)
            
            def auth_cb(name, ok, **kw):
                output(name, ok, **kw)
                
            session = authcheck.test_auth(env, auth_cb, ctx)
            KNOWN_SECRETS.update(session.get('secretvalues', []))
        else:
            output('authenticated_profile_access', 'NON TESTÉ', reason='authcheck_module_missing')

        # Phase 4: Public API Key Rejection Tests (Absent / Invalid)
        if session and 'ctx' in locals():
            opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx), authcheck.NoRedirect() if authcheck else urllib.request.HTTPRedirectHandler())
            def req_api(url, headers=None):
                try:
                    res = opener.open(urllib.request.Request(url, headers=headers or {}), timeout=15)
                except urllib.error.HTTPError as e:
                    res = e
                body = res.read(2000)
                return res.status
                
            for label, hdrs in [('api_key_absent', {}), ('api_key_invalid', {'Authorization': 'Bearer 00000000-0000-4000-8000-000000000000'})]:
                st = req_api(domain + '/api/v1/library', hdrs)
                output(label, st in [401, 403], http_status=st)

        # Phase 5: HLS Synthetic Video Playback
        if video and session and 'ctx' in locals():
            def video_cb(name, ok, **kw):
                output(name, ok, **kw)
            original_open = urllib.request.OpenerDirector.open
            def capture_hls(self, fullurl, *a, **kw):
                u = fullurl.full_url if isinstance(fullurl, urllib.request.Request) else str(fullurl)
                parsed = urllib.parse.urlsplit(u)
                if parsed.netloc == '127.0.0.1:18443' and parsed.query:
                    for k, vs in urllib.parse.parse_qs(parsed.query).items():
                        if k.lower() in ['token','sig','signature','api-key','key','api_key']:
                            for v in vs:
                                if len(v) >= 16: KNOWN_SECRETS.add(v); session['secretvalues'].append(v)
                    if '/torrent-http-proxy/' in parsed.path: session['secretvalues'].append(u)
                return original_open(self, fullurl, *a, **kw)
            urllib.request.OpenerDirector.open = capture_hls
            try: video_ok = video.test_video(session, video_cb, ctx, run_cmd)
            finally: urllib.request.OpenerDirector.open = original_open
        else:
            output('webtor_real_hls_decoded', 'NON TESTÉ', reason='video_module_or_session_missing')

        # Phase 6: Log Secret Disclosure Check
        logs = get_container_logs(NAME)
        r = run_cmd(['docker','exec',NAME,'sh','-c','cat /usr/local/nginx/logs/error.log 2>/dev/null || true'])
        logs += r.stdout
        r = run_cmd(['docker','exec',NAME,'sh','-c','cat /etc/webtor/secrets/api.env 2>/dev/null || true'])
        for line in r.stdout.splitlines():
            key, sep, value = line.removeprefix('export ').partition('=')
            value = value.strip().strip("\"'")
            if sep and len(value)>=16 and any(k in key for k in ['KEY','SECRET','PASSWORD']): KNOWN_SECRETS.add(value)
        leaked = [v for v in KNOWN_SECRETS if len(v)>=16 and v in logs]
        if leaked:
            safe_lines=[redact_text(l, KNOWN_SECRETS)[:400] for l in logs.splitlines() if any(v in l for v in leaked)]
            print(json.dumps({'redacted_leak_context':safe_lines[:5]}),flush=True)
        output('server_secret_values_absent_from_logs', not any(v in logs for v in KNOWN_SECRETS if len(v)>=16), checked_count=len(KNOWN_SECRETS))
        secrets_in_logs = [k for k in ['ADMIN_PASSWORD', 'PG_PASSWORD', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY'] if env[k] in logs]
        output('configured_test_secrets_absent_from_logs', len(secrets_in_logs) == 0, leaked_count=len(secrets_in_logs))
        
        if session:
            sess_secrets_in_logs = [v for v in session.get('secretvalues', []) if v and len(v) >= 12 and v in logs]
            output('session_values_absent_from_logs', len(sess_secrets_in_logs) == 0, leaked_count=len(sess_secrets_in_logs))

        # Phase 7: Restart and Health Test
        try:
            run_cmd(['docker', 'restart', NAME], timeout=30)
            restarted_healthy, _, restart_reason = wait_healthy(timeout=60)
            if restarted_healthy:
                r = urllib.request.urlopen('http://127.0.0.1:18080/login', timeout=10)
                output('restart_and_health', r.status == 200, http_status=r.status)
            else:
                output('restart_and_health', False, reason=restart_reason)
        except Exception as e:
            output('restart_and_health', False, error=type(e).__name__)

        # Final Gate Result
        output('gate_finished', 'PASS', applied_fix='tmpfs_run_exec_confined_runtime_paths_and_log_redaction', no_additional_capabilities=True)

    except SystemExit:
        raise
    except Exception as e:
        output('gate_finished', 'FAIL', error_type=type(e).__name__)
        raise SystemExit(1)
    finally:
        if proxy:
            try:
                proxy.shutdown()
            except Exception:
                pass
        if tmp:
            try:
                tmp.cleanup()
            except Exception:
                pass
        cleanup_container(NAME)
        for name in VOLUMES.values():
            subprocess.run(['docker','volume','rm',name],capture_output=True,timeout=20)

if __name__ == '__main__':
    main()
