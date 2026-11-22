import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from session_store import atomic_json
from web_worker import process
from chat_agent import ChatAgent
from demo_web import fixture

ROOT = Path(__file__).resolve().parents[1]


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,str(path));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


supervisor=module('stock_supervisor',ROOT/'deploy'/'tacc'/'supervisor.py')
tacc=module('stock_tacc_cli',ROOT/'scripts'/'tacc.py')


class DeploymentTests(unittest.TestCase):
    def test_bridge_passes_local_ui_without_submitting_a_job(self):
        with patch.object(tacc, 'sdk_binary', return_value='/tmp/tcloud'), \
             patch.object(tacc.subprocess, 'call', return_value=0) as call, \
             patch('sys.argv', ['tacc.py', 'bridge', '30934', '--local-ui']):
            with self.assertRaises(SystemExit) as exit_result:
                tacc.main()
        self.assertEqual(exit_result.exception.code, 0)
        self.assertIn('--local-ui', call.call_args.args[0])
        self.assertIn('30934', call.call_args.args[0])
        self.assertEqual(call.call_args.kwargs['env']['TCLOUD_BIN'], '/tmp/tcloud')

    def test_launcher_is_loopback_and_preserves_course_runtime(self):
        source='''#!/usr/bin/env bash
export CUDA_VISIBLE_DEVICES=0,1
exec bash "$project/runtime.sh" "$project/vllm-env/bin/python" \\
--model "$project/models/Qwen3.8-27B-AWQ-INT4" \\
--served-model-name qwen3.8-27b --safetensors-load-strategy prefetch \\
--host 0.0.0.0 --port 8000 --tensor-parallel-size 2 \\
--gpu-memory-utilization 0.90 --max-model-len 32768 \\
--max-num-seqs 4 --max-num-batched-tokens 4096
'''
        config={'gpu_memory_utilization':.55,'max_model_len':16384}
        text=supervisor.render_launcher(source,42865,config)
        self.assertNotIn('export CUDA_VISIBLE_DEVICES',text)
        self.assertIn('--host 127.0.0.1 --port 42865',text)
        self.assertIn('--max-model-len 16384',text)
        self.assertIn('--max-num-seqs 1 --enforce-eager',text)
        self.assertIn('runtime.sh',text)
        with self.assertRaises(ValueError):supervisor.render_launcher(source.replace('--port 8000','--port 9000'),42865,config)

    def test_package_has_only_runtime_files_and_unique_workdir(self):
        with tempfile.TemporaryDirectory() as temp:
            one=tacc.package(Path(temp),namespace='my-research',minutes=30)
            two=tacc.package(Path(temp),mode='smoke')
            self.assertNotEqual(one.name,two.name)
            names={str(p.relative_to(one)) for p in one.rglob('*') if p.is_file()}
            self.assertIn('agent/chat_agent.py',names);self.assertIn('agent/data/hk_tech30_snapshot.csv',names)
            self.assertIn('deploy/tacc/server_entry.py',names)
            self.assertFalse(any('.git' in n or 'logs/' in n or '.env' in n or 'id_rsa' in n for n in names))
            self.assertIn('time=00:30:00',(one/'tuxiv.conf').read_text())
            config=json.loads((one/'deployment.json').read_text())
            self.assertEqual(config['namespace'],'my-research')
            subprocess.run(['bash','-n',str(one/'job.sh')],check=True)
            manifest=json.loads((one/'package-manifest.json').read_text())
            self.assertEqual(set(manifest['files']),names-{'package-manifest.json'})

    def test_sdk_error_even_with_zero_exit_status(self):
        with tempfile.TemporaryDirectory() as temp:
            binary=Path(temp)/'tcloud';binary.write_text('#!/bin/sh\necho "[Tcloud Error] submission failed"\nexit 0\n');binary.chmod(0o700)
            with self.assertRaises(RuntimeError):tacc.sdk_call(str(binary),['submit'])

    def test_commit_marker_payload_and_duplicate(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/('a'*32+'.ask');payload=path.with_suffix('.request')
            atomic_json(payload,{'session':'b'*32,'question':'Rank top 3'})
            atomic_json(path,{'protocol':2,'payload':payload.name})
            factory=lambda base,log:ChatAgent(base,log,call=fixture)
            process(path,{},'http://localhost:42865/v1',factory)
            reply=json.loads(path.with_suffix('.reply').read_text())
            self.assertNotIn('error',reply);self.assertFalse(payload.exists())
            self.assertEqual(reply['request_id'],'a'*32)
            atomic_json(path,{'protocol':2,'payload':'../../outside'})
            before=path.with_suffix('.reply').read_bytes();process(path,{},'http://localhost:42865/v1',factory)
            self.assertEqual(path.with_suffix('.reply').read_bytes(),before)

    def test_invalid_marker_does_not_read_outside_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/('c'*32+'.ask');atomic_json(path,{'protocol':2,'payload':'../secret'})
            process(path,{},'http://localhost:42865/v1')
            self.assertIn('Invalid request commit marker',json.loads(path.with_suffix('.reply').read_text())['error'])

    def test_supervisor_readiness_runtime_and_cleanup(self):
        import socket
        import sys
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);root=base/'job';public=base/'public';result=base/'results'
            (root/'deploy'/'tacc').mkdir(parents=True);(public/'vllm-env'/'bin').mkdir(parents=True);result.mkdir()
            (public/'vllm-env'/'bin'/'python').symlink_to(sys.executable)
            (public/'runtime.sh').write_text('#!/bin/bash\nexec "$@"\n')
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            server=base/'server.py'
            server.write_text("""import argparse,json
from http.server import BaseHTTPRequestHandler,HTTPServer
p=argparse.ArgumentParser();p.add_argument('--host');p.add_argument('--port',type=int);a,_=p.parse_known_args()
class H(BaseHTTPRequestHandler):
 def do_GET(self):
  body=json.dumps({'data':[{'id':'qwen3.8-27b'}]}).encode();self.send_response(200);self.end_headers();self.wfile.write(body)
HTTPServer((a.host,a.port),H).serve_forever()
""")
            source=('#!/bin/bash\nexport CUDA_VISIBLE_DEVICES=0,1\nexec '+sys.executable+' '+str(server)+
                    ' --host 0.0.0.0 --port 8000 --safetensors-load-strategy prefetch --gpu-memory-utilization 0.90 --max-model-len 32768 --max-num-seqs 4\n')
            (public/'serve.sh').write_text(source)
            (root/'deploy'/'tacc'/'server_entry.py').write_text("import os,urllib.request\nassert urllib.request.urlopen(os.environ['QWEN_BASE_URL']+'/models').status==200\nprint('FIXTURE_WORKER_OK')\n")
            atomic_json(root/'deployment.json',{'mode':'smoke','port':port,'startup_timeout':10})
            env=dict(os.environ,TACC_WORKDIR=str(root),STOCK_RESULT_DIR=str(result),QWEN_PROJECT_ROOT=str(public),SLURM_JOB_ID='123')
            run=subprocess.run([sys.executable,str(ROOT/'deploy'/'tacc'/'supervisor.py')],env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertIn('MODEL_READY=',run.stdout);self.assertIn('FIXTURE_WORKER_OK',run.stdout)
            self.assertEqual(json.loads((result/'status.json').read_text())['state'],'completed')
            with socket.socket() as sock:
                self.assertNotEqual(sock.connect_ex(('127.0.0.1',port)),0)

    def test_config_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'deployment.json';atomic_json(path,{'port':0})
            with self.assertRaises(ValueError):supervisor.load_config(path)
            atomic_json(path,{'namespace':'../escape'})
            with self.assertRaises(ValueError):supervisor.load_config(path)


if __name__=='__main__':unittest.main()
