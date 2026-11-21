"""Serve browser turns from the job's private SDK-accessible directory."""
import json
import os
import re
import time
from pathlib import Path

from chat_agent import ChatAgent
from session_store import atomic_json, save_agent, restore_agent


def process(path, sessions, base_url, factory=None):
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
            sessions[session] = (factory or ChatAgent)(base_url, path.parent / (session + '.jsonl'))
            sessions[session].session_id = session
            restore_agent(path.parent / (session + '.state'), sessions[session])
        agent = sessions[session]
        def progress(event):
            atomic_json(path.with_suffix('.status'), dict(event, request_id=path.stem))
        agent.progress = progress
        # Old factories are supported for the original mocked transport tests.
        text = agent.ask(question)
        result = dict(agent.last_response or {}, answer=text)
        if agent.last_response:
            result['explanation'] = agent.last_response['answer']
        save_agent(path.parent / (session + '.state'), agent)
        result['request_id'] = path.stem
    except Exception as exc:
        result = {'error': str(exc), 'request_id': path.stem}
        atomic_json(path.with_suffix('.status'), {'event': 'turn_error', 'error': str(exc), 'request_id': path.stem})
    atomic_json(reply, result)
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
        for path in sorted(folder.glob('*.ask'), key=lambda p: p.stat().st_mtime):
            if re.fullmatch('[a-f0-9]{32}', path.stem):
                process(path, sessions, os.environ['QWEN_BASE_URL'])
        time.sleep(1)


if __name__ == '__main__':
    main()
