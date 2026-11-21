"""DeepSeek transport for the agent's JSON tool protocol; no dependencies."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = 'https://api.deepseek.com/v1'


def chat(messages, base_url=BASE_URL, max_tokens=1800, temperature=0):
    key = os.environ.get('DEEPSEEK_API_KEY', '').strip()
    if not key:
        raise ValueError('Set DEEPSEEK_API_KEY in your terminal before starting the agent.')
    # Keep credentials confined to the official endpoint.
    if base_url.rstrip('/') != BASE_URL:
        raise ValueError('DeepSeek mode uses https://api.deepseek.com/v1.')
    payload = {
        'model': os.environ.get('DEEPSEEK_MODEL', 'deepseek-flash'),
        'messages': messages, 'max_tokens': max_tokens, 'temperature': temperature,
        'thinking': {'type': 'disabled'}, 'response_format': {'type': 'json_object'},
        'stream': False,
    }
    request = Request(BASE_URL + '/chat/completions',
                      data=json.dumps(payload).encode('utf-8'),
                      headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
    try:
        with urlopen(request, timeout=120) as response:
            result = json.load(response)
    except HTTPError as exc:
        hints = {401: 'Check DEEPSEEK_API_KEY.', 402: 'Check your DeepSeek API balance.',
                 429: 'Rate limit reached; wait and try again.',
                 400: 'Check DEEPSEEK_MODEL and request compatibility.'}
        raise RuntimeError(f'DeepSeek HTTP {exc.code}. ' + hints.get(exc.code, 'Try again or check DeepSeek service status.')) from None
    except (URLError, TimeoutError, OSError):
        raise RuntimeError('Cannot reach DeepSeek or request timed out. Check your internet connection.') from None
    except (ValueError, UnicodeError):
        raise RuntimeError('DeepSeek returned invalid JSON.') from None
    try:
        choice = result['choices'][0]
        if choice.get('finish_reason') == 'length':
            raise RuntimeError('DeepSeek response was truncated. Try a simpler question.')
        if not isinstance(choice['message']['content'], str):
            raise TypeError()
    except (KeyError, IndexError, TypeError):
        raise RuntimeError('DeepSeek returned no text answer.') from None
    return result
