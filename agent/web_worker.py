"""Serve browser turns from the job's private SDK-accessible directory."""
import json
import os
import re
import time
from pathlib import Path

from chat_agent import ChatAgent


def process(path, sessions, base_url):
    reply = path.with_suffix('.reply')
    if reply.exists():
        path.unlink()
        return
    try:
        request = json.loads(path.read_text(encoding='utf-8'))
        session = request['session']
        question = request['question']
        if not re.fullmatch('[a-f0-9]{32}', session):
            raise ValueError('Invalid conversation ID.')
        if not isinstance(question, str) or not 0 < len(question.strip()) <= 8000:
            raise ValueError('Enter a question of up to 8000 characters.')
        if session not in sessions:
            sessions[session] = ChatAgent(base_url, path.parent / (session + '.jsonl'))
        result = {'answer': sessions[session].ask(question)}
    except Exception as exc:
        result = {'error': str(exc)}
    temp = reply.with_suffix('.tmp')
    temp.write_text(json.dumps(result), encoding='utf-8')
    temp.replace(reply)
    path.unlink()


def main():
    job = os.environ['SLURM_JOB_ID']
    folder = Path(os.environ['TACC_USERDIR']) / 'stock-chat' / job
    folder.mkdir(mode=0o700, parents=True)
    page = folder / 'chat.html'
    temp = page.with_suffix('.tmp')
    temp.write_bytes(Path(__file__).with_name('chat.html').read_bytes())
    temp.replace(page)
    print(f'Chat ready. On your SDK machine run: python3 web_bridge.py {job}', flush=True)
    sessions = {}
    while True:
        for path in folder.glob('*.ask'):
            if re.fullmatch('[a-f0-9]{32}', path.stem):
                process(path, sessions, os.environ['QWEN_BASE_URL'])
        time.sleep(1)


if __name__ == '__main__':
    main()
