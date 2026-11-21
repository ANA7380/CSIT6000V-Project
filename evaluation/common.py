"""Shared helpers for the evaluation pipeline. Python 3.9+, standard library only."""
import re
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
# On TACC the agent sources are copied next to this file by bundle.sh; locally use ../agent.
AGENT_DIR = EVAL_DIR / 'agent_src' if (EVAL_DIR / 'agent_src' / 'agent.py').exists() else EVAL_DIR.parent / 'agent'
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

_DATE = re.compile(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}')
_TICKER = re.compile(r'(?<![\d.])(\d{1,5})\.HK\b', re.I)
_NUMBER = re.compile(r'(?<![\w.])([-+]?\d+(?:\.(\d+))?)(\s?[%％])?')


def clean(text):
    text = text.replace('−', '-').replace('％', '%')
    return re.sub(r'(?<=\d),(?=\d{3}(?!\d))', '', text)


def extract_numbers(text):
    """Return (value, decimals, is_percent) for every number, ignoring dates and tickers."""
    text = _TICKER.sub(' ', _DATE.sub(' ', clean(text)))
    return [(float(m.group(1)), len(m.group(2) or ''), bool(m.group(3))) for m in _NUMBER.finditer(text)]


def close_enough(value, decimals, reference, relative=0.01):
    """True when value is a correct rounding of reference AND within 1% (or 0.005).

    Sign is ignored because prose often carries it in words ("fell 10.0%").
    """
    diff = abs(abs(value) - abs(reference))
    return diff <= 0.5 * 10 ** -decimals + 1e-9 and diff <= max(relative * abs(reference), 0.005) + 1e-9


def has_number(text, reference):
    return any(close_enough(v, d, reference) for v, d, _ in extract_numbers(text))


def numeric_claims(text, exclude_text=''):
    """Decimal or percentage figures in an answer, minus figures the user supplied."""
    given = {round(abs(v), 6) for v, _, _ in extract_numbers(exclude_text)}
    return [(v, d) for v, d, pct in extract_numbers(text) if (d > 0 or pct) and round(abs(v), 6) not in given]


def supported(value, decimals, evidence):
    """Is a claimed figure a rounding of some evidence number (allowing unit scaling)?"""
    for e in evidence:
        scales = [1.0]
        if abs(e) <= 1:
            scales.append(0.01)                       # 0.25 reported as 25%
        if abs(e) >= 1e5:
            scales += [1e3, 1e4, 1e6, 1e8, 1e9]       # thousands, 万, millions, 亿, billions
        if any(abs(abs(value) - abs(e) / s) <= 0.5 * 10 ** -decimals + 1e-9 for s in scales):
            return True
    return False


def flatten_numbers(obj, out=None):
    """Collect every finite number inside a nested tool result (numeric strings included)."""
    out = [] if out is None else out
    if isinstance(obj, bool) or obj is None:
        return out
    if isinstance(obj, (int, float)):
        if obj == obj and abs(obj) != float('inf'):
            out.append(float(obj))
    elif isinstance(obj, str):
        if re.fullmatch(r'\s*[-+]?\d+(\.\d+)?([eE][-+]?\d+)?\s*', obj):
            out.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            flatten_numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            flatten_numbers(v, out)
    return out


def mentioned_tickers(text, names):
    """Tickers in order of first mention. names maps symbol -> company name."""
    text = clean(text)
    hits = [(m.start(), '%04d.HK' % int(m.group(1))) for m in _TICKER.finditer(text)]
    masked = text
    for symbol, name in sorted(names.items(), key=lambda kv: -len(kv[1])):   # longest name first
        pattern = re.compile(r'(?<!\w)' + re.escape(name) + r'(?!\w)', re.I)
        for m in pattern.finditer(masked):
            hits.append((m.start(), symbol))
        masked = pattern.sub(lambda m: ' ' * len(m.group(0)), masked)
    ordered = []
    for _, symbol in sorted(hits):
        if symbol not in ordered:
            ordered.append(symbol)
    return ordered
