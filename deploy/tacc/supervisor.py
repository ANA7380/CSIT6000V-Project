"""Own service and worker process groups; persist readiness and bounded cleanup.

Kept compatible with Python 3.6 for the course /usr/bin/python3. Application code
runs with the public runtime Python (3.9+). No public environment files are edited.
"""
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def atomic(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2), encoding='utf-8')
    os.chmod(str(temp), 0o600)
    temp.replace(path)


def render_launcher(source, port, config):
    replacements = [
        (r'^export CUDA_VISIBLE_DEVICES=.*\n', '', 'GPU assignment'),
        (r'--host\s+0\.0\.0\.0\b', '--host 127.0.0.1', 'loopback binding'),
        (r'--port\s+8000\b', '--port ' + str(port), 'HTTP port'),
        (r'--safetensors-load-strategy\s+prefetch\b', '--safetensors-load-strategy lazy', 'load strategy'),
        (r'--gpu-memory-utilization\s+0\.90\b', '--gpu-memory-utilization ' + str(config['gpu_memory_utilization']), 'GPU memory'),
        (r'--max-model-len\s+32768\b', '--max-model-len ' + str(config['max_model_len']), 'context length'),
        (r'--max-num-seqs\s+4\b', '--max-num-seqs 1 --enforce-eager', 'inference concurrency'),
    ]
    for pattern, replacement, label in replacements:
        source, count = re.subn(pattern, replacement, source, flags=re.M)
        if count != 1:
            raise ValueError('Public serve.sh changed: expected exactly one ' + label + ' setting; found ' + str(count))
    return source


def load_config(path):
    config = dict(mode='web', port=42865, startup_timeout=1800,
                  gpu_memory_utilization=0.55, max_model_len=16384,
                  smoke=True, namespace=None)
    if path.exists():
        config.update(json.loads(path.read_text(encoding='utf-8')))
    if config['mode'] not in ('web', 'smoke'):
        raise ValueError('mode must be web or smoke')
    for key, low, high in [('port', 1024, 65535), ('startup_timeout', 10, 1800), ('max_model_len', 4096, 32768)]:
        if type(config[key]) is not int or not low <= config[key] <= high:
            raise ValueError('Invalid deployment value: ' + key)
    if type(config['gpu_memory_utilization']) not in (int,float) or not 0.1 <= config['gpu_memory_utilization'] <= 0.9:
        raise ValueError('Invalid GPU memory utilization')
    if type(config['smoke']) is not bool:
        raise ValueError('smoke must be a boolean')
    if config['namespace'] is not None and not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', config['namespace']):
        raise ValueError('Invalid persistent conversation namespace')
    return config


def ready(base_url):
    # Bypass inherited proxies for an allocation-local service.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(base_url + '/models', timeout=3) as response:
            data = json.load(response)
        return isinstance(data,dict) and isinstance(data.get('data'),list) and any(isinstance(m,dict) and m.get('id') == 'qwen3.8-27b' for m in data['data'])
    except (OSError, ValueError):
        return False


def stop_group(process, grace=15):
    if process is None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        process.poll()
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        raise RuntimeError('Process group did not exit: ' + str(process.pid))


def sample_startup(result, service):
    """Only inspect this service's process group; never log other users' tasks."""
    sample = {'timestamp': time.time(), 'service_pid': service.pid}
    try:
        rows = subprocess.check_output(['ps','-eo','pid=,ppid=,pgid=,stat=,etime=,pcpu=,rss=,args='], timeout=5).decode(errors='replace').splitlines()
        sample['processes'] = [line.strip() for line in rows if len(line.split(None,7)) >= 3 and line.split(None,7)[2] == str(service.pid)]
    except (OSError, subprocess.SubprocessError) as exc:
        sample['process_error'] = str(exc)
    try:
        probe = subprocess.run(['nvidia-smi','--query-gpu=index,utilization.gpu,memory.used,memory.free','--format=csv'],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=5)
        sample['gpus'] = probe.stdout.decode(errors='replace')
    except (OSError, subprocess.SubprocessError) as exc:
        sample['gpu_error'] = str(exc)
    atomic(result/'runtime-sample.json', sample)
    with (result/'runtime-samples.jsonl').open('a') as handle:
        handle.write(json.dumps(sample) + '\n')


def run():
    root = Path(os.environ['TACC_WORKDIR'])
    result = Path(os.environ['STOCK_RESULT_DIR'])
    config = load_config(root / 'deployment.json')
    base = 'http://127.0.0.1:{}/v1'.format(config['port'])
    # Detect a collision before starting; never attach to or stop another service.
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', config['port']))
    os.environ['QWEN_BASE_URL'] = base
    os.environ['no_proxy'] = os.environ.get('no_proxy', '') + ',127.0.0.1,localhost'
    os.environ['NO_PROXY'] = os.environ['no_proxy']
    # Application uses a conservative character budget; the service enforces
    # the actual tokenizer limit, and errors are logged rather than hidden.
    if config['namespace']:
        os.environ['STOCK_CHAT_NAMESPACE'] = config['namespace']
    launcher = result / 'serve-stock.sh'
    launcher.write_text(render_launcher((Path(os.environ['QWEN_PROJECT_ROOT']) / 'serve.sh').read_text(), config['port'], config))
    atomic(result / 'deployment.json', dict(config, base_url=base, job_id=os.environ['SLURM_JOB_ID'],
                                           python=sys.version, cuda_visible_devices=os.environ.get('CUDA_VISIBLE_DEVICES')))
    runtime = Path(os.environ['QWEN_PROJECT_ROOT'])
    client_command = ['bash', str(runtime/'runtime.sh'), str(runtime/'vllm-env'/'bin'/'python'),
                      '-u', str(root/'deploy'/'tacc'/'server_entry.py')]
    stop = [None]
    def request_stop(signum, _frame):
        stop[0] = signum
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, request_stop)
    service = worker = None
    state = 'starting_model'
    result_code = 1
    try:
        with (result / 'model.log').open('w') as model_log:
            service = subprocess.Popen(['bash', str(launcher)], stdout=model_log, stderr=subprocess.STDOUT, start_new_session=True)
            atomic(result/'status.json', {'state': state, 'base_url': base, 'service_pid': service.pid})
            print('SERVICE_BASE_URL=' + base, flush=True)
            deadline = time.monotonic() + config['startup_timeout']
            next_notice = 0
            while not ready(base):
                if stop[0] is not None:
                    state = 'stopped'
                    result_code = 128 + stop[0]
                    return result_code
                if service.poll() is not None:
                    raise RuntimeError('Model process exited before readiness; inspect model.log')
                if time.monotonic() >= deadline:
                    raise RuntimeError('Model startup timeout; inspect model.log')
                if time.monotonic() >= next_notice:
                    sample_startup(result, service)
                    print('Waiting for Qwen readiness; model log is in ' + str(result/'model.log'), flush=True)
                    next_notice = time.monotonic() + 30
                time.sleep(2)
            print('MODEL_READY=' + base, flush=True)
            # Worker runs a live smoke test before advertising browser readiness.
            worker = subprocess.Popen(client_command, cwd=str(root), start_new_session=True)
            state = 'running_agent'
            atomic(result/'status.json', {'state':state, 'base_url':base,'service_pid':service.pid,'worker_pid':worker.pid})
            announced_ready = False
            while stop[0] is None:
                if not announced_ready and (result/'connection.json').exists():
                    announced_ready = True
                    atomic(result/'status.json', {'state':'ready','base_url':base,
                           'service_pid':service.pid,'worker_pid':worker.pid})
                result_code = worker.poll()
                if result_code is not None:
                    break
                if service.poll() is not None:
                    raise RuntimeError('Model service exited while Agent was running')
                time.sleep(0.5)
            if stop[0] is not None:
                result_code = 128 + stop[0]
            state = 'completed' if result_code == 0 else ('stopped' if stop[0] is not None else 'failed')
    except Exception as exc:
        state = 'failed'
        print('DEPLOYMENT_ERROR=' + str(exc), file=sys.stderr, flush=True)
        atomic(result/'error.json', {'state':state, 'error':str(exc)})
        result_code = 1
    finally:
        try:
            stop_group(worker, 5)
        finally:
            stop_group(service, 15)
        atomic(result/'status.json', {'state':state,'returncode':result_code,'base_url':base})
        print('STOCK_RESEARCH_EXIT=' + str(result_code), flush=True)
    return result_code if result_code >= 0 else 128 - result_code


if __name__ == '__main__':
    sys.exit(run())
