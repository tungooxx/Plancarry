#!/usr/bin/env python3
import argparse, asyncio, os, shlex, sys, subprocess, tempfile
from pathlib import Path
import asyncssh
REMOTE_REPO='/workspace/GPU-Lab/repos/plancarry'
REMOTE_COMMIT='acd6576e6255b571870a13dc689db6094d0668eb'
REMOTE_PYTHON='/opt/gpu-lab/envs/plancarry-replayresidual-t1-retry/bin/python'
EXPECTED_GPU='NVIDIA GeForce RTX 4070 SUPER'
EXPECTED_HOST='179.255.148.147'
EXPECTED_PORT=10415
EXPECTED_HOSTKEY_FP='SHA256:Wp5kj9iRjvutWLLGv4CUgWvlnY6rwlh/AxPn3PeMTCs'
LAUNCHER='localcontinuation_vast_primary_v1.sh'
SOURCE_HASHES={
'localcontinuation_packet_builder_v1.py':'116c213d27af987e782e463bc0317d8d443e95bf1ba571dbba0386d63d109128',
'localcontinuation_phase_runner_v1.py':'81a55589f68e1b8d53110ad64eceacb7cfc52a0838166b5241b34fb7fb11783d',
'localcontinuation_science_driver_v1.py':'7768a45cd41048ebcabd27a0be6602b41642fa95f425883e199a94c3c2291592',
'localcontinuation_validator_v1.py':'93390667e19302087f6b3d1a583f00ee4b97232443a4955aa2f1ca2a773fcbda',
LAUNCHER:'a640e43a1bb253ac0ac0e78bcdc61c42c5e1894ba26be834877f301b9744e72f',
'tests/test_localcontinuation_execution_stack_v1.py':'53d894d6d9ac406f8ff51263ab01ffbfe22ed65894cdb8a4901bf318b019f3d1'}
DEV_OUTPUTS=[
'results/science/plancarry_replayresidual_localcontinuation_dev_packets_v1',
'results/science/plancarry_replayresidual_localcontinuation_development_grid_v1.json',
'results/science/plancarry_replayresidual_localcontinuation_development_selection_v1.json',
'results/science/plancarry_replayresidual_localcontinuation_development_terminal_v1.json']
def q(x): return shlex.quote(str(x))
def remote_preflight_command():
    checks=' && '.join(f"echo {q(h+'  '+p)} | sha256sum -c -" for p,h in SOURCE_HASHES.items())
    absent=' && '.join(f"test ! -e {q(p)}" for p in DEV_OUTPUTS)
    return f'''set -euo pipefail
cd {q(REMOTE_REPO)}
test "$(git rev-parse HEAD)" = {q(REMOTE_COMMIT)}
test -z "$(git status --porcelain)"
test "$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1 | sed 's/[[:space:]]*$//')" = {q(EXPECTED_GPU)}
{checks}
test -x {q(REMOTE_PYTHON)}
{q(REMOTE_PYTHON)} - <<'PYV'
import sys, torch, transformers, tokenizers
from importlib.metadata import version
assert sys.version.split()[0]=='3.13.15'
assert torch.__version__=='2.13.0+cu130'
assert transformers.__version__=='4.51.3'
assert tokenizers.__version__=='0.21.1'
assert version('alfworld')=='0.4.2'
assert version('textworld')=='1.7.0'
assert version('PyYAML')=='6.0.3'
assert torch.cuda.is_available()
assert torch.cuda.get_device_name(0)=={EXPECTED_GPU!r}
print('EXACT_RUNTIME_PASS')
PYV
{absent}
PLANCARRY_EXPECTED_GIT_COMMIT={q(REMOTE_COMMIT)} LOCALCONT_EXPECTED_DEVICE_NAME={q(EXPECTED_GPU)} PLANCARRY_PYTHON={q(REMOTE_PYTHON)} CUBLAS_WORKSPACE_CONFIG=:4096:8 {q(REMOTE_PYTHON)} localcontinuation_science_driver_v1.py --phase preflight --expected-device {q(EXPECTED_GPU)}
echo DISPATCH_PREFLIGHT_PASS
'''
def remote_development_command():
    return f'''set -euo pipefail
cd {q(REMOTE_REPO)}
PLANCARRY_EXPECTED_GIT_COMMIT={q(REMOTE_COMMIT)} LOCALCONT_EXPECTED_DEVICE_NAME={q(EXPECTED_GPU)} PLANCARRY_PYTHON={q(REMOTE_PYTHON)} CUBLAS_WORKSPACE_CONFIG=:4096:8 bash {q(LAUNCHER)}
'''
async def run_stream(conn, command):
    proc=await conn.create_process(command)
    async def pump(reader,target):
        async for chunk in reader:
            target.write(chunk); target.flush()
    await asyncio.gather(pump(proc.stdout,sys.stdout),pump(proc.stderr,sys.stderr))
    await proc.wait_closed()
    return proc.exit_status
async def fetch_outputs(conn,jobdir):
    outdir=Path(jobdir)/'artifacts'; outdir.mkdir(parents=True,exist_ok=True)
    remote_tar='/tmp/plancarry_localcontinuation_dev_artifacts_v1.tgz'
    items=' '.join(q(p) for p in DEV_OUTPUTS)
    cmd=f"cd {q(REMOTE_REPO)}; set --; for p in {items}; do [ -e \"$p\" ] && set -- \"$@\" \"$p\"; done; [ \"$#\" -gt 0 ]; tar -czf {q(remote_tar)} \"$@\""
    r=await conn.run(cmd,check=False)
    if r.exit_status: raise RuntimeError('REMOTE_ARTIFACT_TAR_FAILED')
    async with conn.start_sftp_client() as sftp:
        await sftp.get(remote_tar,str(outdir/'plancarry_localcontinuation_dev_artifacts_v1.tgz'))
        for rel in DEV_OUTPUTS[1:]:
            e=await conn.run(f'test -f {q(REMOTE_REPO+"/"+rel)}',check=False)
            if e.exit_status==0:
                await sftp.get(REMOTE_REPO+'/'+rel,str(outdir/Path(rel).name))
    print('DEVELOPMENT_ARTIFACTS_FETCHED')
def pinned_known_hosts(host, port):
    if host != EXPECTED_HOST or int(port) != EXPECTED_PORT:
        raise SystemExit('VAST_ENDPOINT_MISMATCH')
    scan=subprocess.run(['ssh-keyscan','-T','8','-t','ed25519','-p',str(port),host],capture_output=True,text=True,check=False)
    if scan.returncode != 0 or not scan.stdout.strip():
        raise SystemExit('VAST_HOSTKEY_SCAN_FAILED')
    with tempfile.NamedTemporaryFile('w',delete=False,prefix='plancarry_known_hosts_',suffix='.tmp') as f:
        f.write(scan.stdout); path=f.name
    fp=subprocess.run(['ssh-keygen','-lf',path,'-E','sha256'],capture_output=True,text=True,check=False)
    if fp.returncode != 0 or EXPECTED_HOSTKEY_FP not in fp.stdout:
        Path(path).unlink(missing_ok=True)
        raise SystemExit('VAST_HOSTKEY_MISMATCH')
    return path
async def main_async(mode):
    host=os.environ.get('LOCALCONT_VAST_HOST'); port=os.environ.get('LOCALCONT_VAST_PORT')
    user=os.environ.get('LOCALCONT_VAST_USER','root'); key=os.environ.get('LOCALCONT_VAST_SSH_KEY','/run/ssh-key')
    if not host or not port or not port.isdigit(): raise SystemExit('VAST_ENDPOINT_ENV_REQUIRED')
    if mode=='development':
        if os.environ.get('LOCALCONT_DEVELOPMENT_AUTHORIZATION')!='RESEARCH_DECISION_BOUND': raise SystemExit('RESEARCH_DECISION_BOUND_AUTHORIZATION_REQUIRED')
        if not os.environ.get('GPU_LAB_JOB_DIR'): raise SystemExit('GPU_LAB_JOB_DIR_REQUIRED')
    known=pinned_known_hosts(host,int(port))
    try:
        async with asyncssh.connect(host,port=int(port),username=user,client_keys=[key],known_hosts=known,connect_timeout=30) as conn:
            pre=await conn.run(remote_preflight_command(),check=False,timeout=120)
            sys.stdout.write(pre.stdout); sys.stderr.write(pre.stderr)
            if pre.exit_status or 'READY_NO_SCIENCE' not in pre.stdout or 'DISPATCH_PREFLIGHT_PASS' not in pre.stdout:
                raise SystemExit(pre.exit_status or 85)
            if mode=='preflight': return
            code=await run_stream(conn,remote_development_command())
            if code: raise SystemExit(code)
            await fetch_outputs(conn,os.environ['GPU_LAB_JOB_DIR'])
    finally:
        Path(known).unlink(missing_ok=True)
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--mode',choices=['preflight','development'],required=True)
    asyncio.run(main_async(ap.parse_args().mode))
if __name__=='__main__': main()
