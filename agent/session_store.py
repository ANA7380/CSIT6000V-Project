"""Atomic, private JSON conversation snapshots; never stores model credentials."""
import json
import os
from pathlib import Path


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, allow_nan=False)
    os.chmod(temp, 0o600)
    temp.replace(path)


def save_agent(path, agent):
    atomic_json(path, {'version': 1, 'messages': agent.messages, 'state': agent.state,
                       'evidence': agent.evidence, 'next_evidence': agent.next_evidence})


def restore_agent(path, agent):
    path = Path(path)
    if not path.exists():
        return
    saved = json.loads(path.read_text(encoding='utf-8'))
    if saved.get('version') != 1 or not isinstance(saved.get('messages'), list):
        raise ValueError('Unsupported conversation snapshot; start a new conversation.')
    # Always use the current system prompt, not a saved instruction.
    agent.messages = [agent.messages[0]] + saved['messages'][1:]
    agent.state = saved['state']
    agent.evidence = saved['evidence']
    agent.next_evidence = saved['next_evidence']
