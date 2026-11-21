"""Optional replay of a private context regression fixture in a validation package.

Normal deployments do not contain context-regression.json. The file is not part
of the application's allowlisted package or Git source and contains no API keys.
"""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'agent'))
from qwen_client import count_tokens,chat
from chat_agent import ChatAgent,SYSTEM
from session_store import atomic_json


def verify(base,result):
    fixture=ROOT/'context-regression.json'
    if not fixture.exists():return
    payload=json.loads(fixture.read_text());messages=payload['messages']
    count,limit=count_tokens(messages,base)
    error=None
    try:chat(messages,base,max_tokens=1800,temperature=0)
    except RuntimeError as exc:error=str(exc)
    agent=ChatAgent(base,result/'context-regression-audit.jsonl')
    agent.messages=[{'role':'system','content':SYSTEM}]+messages[1:]
    try:agent.state=json.loads(messages[0]['content'].rsplit('SESSION_STATE\n',1)[1]);agent.state.pop('available_evidence',None)
    except (ValueError,IndexError):pass
    for message in messages[1:]:
        if message['content'].startswith('TOOL_RESULT\n'):
            item=json.loads(message['content'].split('\n',1)[1])
            if 'id' in item:agent.evidence.append(item)
    fitted=agent._context();after,new_limit=count_tokens(fitted,base)
    # The current question and its tools remain in the last complete turn.
    original_questions=[m['content'] for m in messages if m['role']=='user' and not m['content'].startswith(('TOOL_RESULT\n','MODEL_FORMAT_ERROR\n','ANSWER_VALIDATION_ERROR\n'))]
    assert original_questions[-1] in [m['content'] for m in fitted]
    assert after+1800+128<=new_limit
    record=dict(raw_input_tokens=count,context_limit=limit,requested_output_tokens=1800,
                raw_request_error=error,fitted_input_tokens=after,
                old_messages=len(messages),fitted_messages=len(fitted),
                current_question_preserved=True,passed=True)
    atomic_json(result/'context-regression.json',record);print('CONTEXT_REGRESSION_PASSED='+json.dumps(record),flush=True)
