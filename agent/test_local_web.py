import json
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from pathlib import Path

from chat_agent import ChatAgent
from demo_web import fixture
from local_web import make_server
from web_worker import process
from session_store import atomic_json


class LocalWebTests(unittest.TestCase):
    def test_local_protocol_status_and_restart_restore(self):
        with tempfile.TemporaryDirectory() as temp:
            factory=lambda base,log:ChatAgent(base,log,call=fixture)
            server=make_server(0,Path(temp),factory,'http://localhost:8000/v1')
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            conn=HTTPConnection(server.address,timeout=20)
            try:
                conn.request('POST','/ask',json.dumps({'session':'a'*32,'question':'Rank top 3'}),
                             {'Content-Type':'application/json','Origin':'http://'+server.address})
                response=conn.getresponse();self.assertEqual(response.status,202)
                turn=json.load(response)['turn'];deadline=time.monotonic()+10
                while True:
                    conn.request('GET','/reply/'+turn);r=conn.getresponse();data=json.load(r)
                    if r.status==200:break
                    self.assertEqual(r.status,202)
                    if time.monotonic()>deadline:self.fail('Worker timed out')
                    time.sleep(.03)
                self.assertNotIn('error',data)
                self.assertEqual(len(data['state']['ranking_history']),1)
                self.assertTrue(data['end_to_end_ms']>=data['duration_ms'])
                self.assertTrue((Path(temp)/(turn+'.status')).exists())
                self.assertTrue((Path(temp)/('a'*32+'.state')).exists())
                # Simulate a worker restart: empty in-memory sessions, same private JSON snapshots.
                second=Path(temp)/('b'*32+'.ask')
                atomic_json(second,{'session':'a'*32,'question':'Keep the same criteria, top 5'})
                process(second,{},'http://localhost:8000/v1',factory)
                resumed=json.loads(second.with_suffix('.reply').read_text())
                self.assertEqual(resumed['state']['last_ranking_request']['top_k'],5)
                self.assertEqual(resumed['state']['last_ranking_request']['filters'],data['state']['last_ranking_request']['filters'])
                # A duplicate already-completed request returns the same reply, no second model turn.
                reply=second.with_suffix('.reply').read_bytes()
                atomic_json(second,{'session':'a'*32,'question':'Rank top 30'})
                process(second,{},'http://localhost:8000/v1',factory)
                self.assertEqual(second.with_suffix('.reply').read_bytes(),reply)
                conn.request('POST','/ask','{}',{'Content-Type':'application/json','Origin':'http://untrusted.example'})
                denied=conn.getresponse();self.assertEqual(denied.status,403);denied.read()
            finally:
                conn.close();server.shutdown();server.server_close();server.queue.put(None)
                server.worker.join(2);thread.join(2)


if __name__=='__main__':unittest.main()
