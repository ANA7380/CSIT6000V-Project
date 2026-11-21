"""Package, submit and operate the co-located course Qwen + stock Agent job.

Uses the user's configured tcloud SDK. Never uploads repository credentials/logs.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
APP_FILES = ('agent.py','analysis_tools.py','chat_agent.py','tool_registry.py','qwen_client.py',
             'evidence.py','session_store.py','web_worker.py','chat.html')


def sdk_binary(explicit=None):
    command = explicit or os.environ.get('TCLOUD_BIN') or shutil.which('tcloud')
    if not command:
        candidate = ROOT.parent.parent/'mpi-assignment'/'linux-amd64-v0.4.1'/'tcloud'
        if candidate.is_file():
            command = str(candidate)
    if not command:
        raise RuntimeError('tcloud not found. Source your SDK env.sh or set TCLOUD_BIN.')
    return command


def sdk_call(command, args, cwd=None, timeout=120):
    run = subprocess.run([command] + list(map(str,args)), cwd=cwd, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, timeout=timeout)
    output = run.stdout.replace(b'\0',b'').decode('utf-8',errors='replace')
    bad = ('[tcloud error]', 'permission denied', 'rsync error', 'authentication failed', 'failed to')
    if run.returncode or any(m in output.lower() for m in bad):
        raise RuntimeError('tcloud {} failed:\n{}'.format(args[0],output.strip()))
    return output


def package(output, mode='web', namespace=None, port=42865, smoke=True, minutes=60):
    if mode not in ('web','smoke','diagnostic') or type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError('Invalid mode or port')
    if namespace is not None and not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',namespace):
        raise ValueError('Namespace must contain 1..80 letters, digits, underscores or hyphens.')
    if type(minutes) is not int or not 1 <= minutes <= 60:
        raise ValueError('Job duration must be 1..60 minutes')
    name='stock-research-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8]
    folder=output.resolve()/name
    folder.mkdir(parents=True,exist_ok=False)
    (folder/'agent'/'data').mkdir(parents=True)
    (folder/'deploy'/'tacc').mkdir(parents=True)
    files=list(APP_FILES)
    if mode=='diagnostic':
        files += ['web_bridge.py','local_web.py','demo_web.py','deepseek_client.py']
        files += [p.name for p in sorted((ROOT/'agent').glob('test_*.py'))]
    for name in files:
        shutil.copyfile(ROOT/'agent'/name,folder/'agent'/name)
    for name in ('hk_tech30_snapshot.csv','hk_tech30_financials.csv','hk_tech30_daily_prices.csv','README.md'):
        shutil.copyfile(ROOT/'agent'/'data'/name,folder/'agent'/'data'/name)
    for name in ('supervisor.py','server_entry.py','diagnose.py','job.sh','tuxiv.conf'):
        shutil.copyfile(ROOT/'deploy'/'tacc'/name,folder/'deploy'/'tacc'/name)
    shutil.copyfile(ROOT/'deploy'/'tacc'/'job.sh',folder/'job.sh')
    config=(ROOT/'deploy'/'tacc'/'tuxiv.conf').read_text()
    walltime='{:02d}:{:02d}:00'.format(minutes//60,minutes%60)
    config=config.replace('time=01:00:00','time='+walltime)
    if mode=='diagnostic':
        config=config.replace('    - gres=gpu:2\n','').replace('cpus-per-task=8','cpus-per-task=2')
        # Diagnostics exercise the packaging helpers too; no SDK network test is run.
        (folder/'scripts').mkdir()
        shutil.copyfile(ROOT/'scripts'/'tacc.py',folder/'scripts'/'tacc.py')
    (folder/'tuxiv.conf').write_text(config)
    deployment=dict(mode=mode,namespace=namespace,port=port,smoke=smoke,
                    startup_timeout=1800,gpu_memory_utilization=0.55,max_model_len=16384)
    (folder/'deployment.json').write_text(json.dumps(deployment,indent=2)+'\n')
    manifest={str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(folder.rglob('*')) if p.is_file()}
    try:
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True,stderr=subprocess.DEVNULL).strip()
        dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True,stderr=subprocess.DEVNULL))
    except (subprocess.CalledProcessError,OSError):
        commit=None;dirty=True
    (folder/'package-manifest.json').write_text(json.dumps(dict(source_commit=commit,source_dirty=dirty,files=manifest),indent=2)+'\n')
    return folder


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk',help='Path to configured tcloud executable')
    sub=parser.add_subparsers(dest='command',required=True)
    for name in ('package','submit'):
        p=sub.add_parser(name)
        p.add_argument('--output',type=Path,default=ROOT/'var'/'tacc')
        p.add_argument('--mode',choices=['web','smoke','diagnostic'],default='web')
        p.add_argument('--namespace',help='Stable server-side conversation namespace; never run two workers with the same name')
        p.add_argument('--port',type=int,default=42865)
        p.add_argument('--skip-smoke',action='store_true')
        p.add_argument('--minutes',type=int,default=60)
    sub.add_parser('preflight')
    for name in ('status','download','bridge','stop'):
        p=sub.add_parser(name);p.add_argument('job',type=int)
        if name=='download':p.add_argument('--output',type=Path,default=ROOT/'var'/'tacc-results')
        if name=='bridge':p.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    if hasattr(args,'job') and args.job <= 0:
        parser.error('Job ID must be a positive integer.')
    if args.command in ('package','submit'):
        folder=package(args.output,args.mode,args.namespace,args.port,not args.skip_smoke,args.minutes)
        print('PACKAGE='+str(folder),flush=True)
        if args.command=='package':return
        sdk=sdk_binary(args.sdk)
        output=sdk_call(sdk,['submit'],cwd=folder,timeout=300)
        print(output,flush=True)
        match=re.search(r'Submitted batch job\s+(\d+)',output)
        if not match:raise RuntimeError('SDK did not confirm a job ID; check its output before resubmitting.')
        job=int(match[1])
        (folder.parent/('submitted-'+str(job)+'.json')).write_text(json.dumps(dict(job=job,package=str(folder),mode=args.mode,namespace=args.namespace),indent=2))
        print('JOB_ID='+str(job))
        print('LOG=slurm_log/stock-research-'+str(job)+'.log')
        if args.mode=='web':
            print('BRIDGE=python3 scripts/tacc.py bridge '+str(job))
        return
    sdk=sdk_binary(args.sdk)
    if args.command=='preflight':
        print(sdk_call(sdk,['env','ls']))
        print(sdk_call(sdk,['env','ls','-n','proxy']))
        print(sdk_call(sdk,['ps']))
    elif args.command=='status':
        print(sdk_call(sdk,['ps','-j',args.job]))
        try:
            print(sdk_call(sdk,['cat','slurm_log/stock-research-{}.log'.format(args.job)]))
        except RuntimeError as exc:
            if 'no such file' not in str(exc).lower():
                raise
            print('Log not created yet; queued jobs have no runtime log.')
    elif args.command=='download':
        target=args.output.resolve()/str(args.job)
        target.parent.mkdir(parents=True,exist_ok=True)
        print(sdk_call(sdk,['download','-r','stock-research/'+str(args.job),target.parent],timeout=300))
        print(sdk_call(sdk,['download','slurm_log/stock-research-{}.log'.format(args.job),target/'slurm.log']))
        print('DOWNLOADED='+str(target))
    elif args.command=='bridge':
        # Reuse the browser bridge. Its authenticated SDK traffic stays local.
        env=dict(os.environ,TCLOUD_BIN=sdk,PATH=str(Path(sdk).resolve().parent)+os.pathsep+os.environ.get('PATH',''))
        raise SystemExit(subprocess.call([sys.executable,str(ROOT/'agent'/'web_bridge.py'),str(args.job),'--port',str(args.port)],env=env))
    elif args.command=='stop':
        print(sdk_call(sdk,['cancel','-j',args.job]))


if __name__=='__main__':
    try:main()
    except (RuntimeError,ValueError,subprocess.TimeoutExpired) as exc:
        raise SystemExit(str(exc))
