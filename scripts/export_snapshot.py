"""Export frozen prepared JSON to deterministic CSVs, or check committed exports.

No network access. Field order and numeric/string types are preserved by schema.
"""
import argparse
import csv
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / 'data' / 'snapshot_2026-11-18'


def cell(value):
    if value is None:
        return ''
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def equivalent(a, b):
    if a == b:
        return True
    if 'GMT+0800' in a and 'T' in b:
        # Original spreadsheet export changed ISO timestamps to JS date strings
        # and discarded subsecond precision. Canonical exports retain full ISO.
        cleaned = re.sub(r' \(.*\)$', '', a).replace('GMT+0800', '+0800')
        try:
            old = datetime.strptime(cleaned, '%a %b %d %Y %H:%M:%S %z')
            return old == datetime.fromisoformat(b).replace(microsecond=0)
        except ValueError:
            return False
    try:
        return math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=1e-10)
    except ValueError:
        return False


def export(output, check=False):
    data = json.loads((SNAPSHOT / 'prepared_tables.json').read_text(encoding='utf-8'))
    schema = json.loads((ROOT / 'data' / 'csv_schema.json').read_text())
    manifest = {}
    for name, fields in schema.items():
        rows = [{key: cell(row.get(key)) for key in fields} for row in data[name]]
        target = output / (name + '.csv')
        if check:
            with target.open(encoding='utf-8-sig', newline='') as handle:
                reader = csv.DictReader(handle)
                actual = list(reader)
                if reader.fieldnames != fields or len(actual) != len(rows):
                    raise ValueError(f'{target}: schema/row-count mismatch')
            for i, (left, right) in enumerate(zip(actual, rows)):
                for key in fields:
                    if not equivalent(left[key], right[key]):
                        raise ValueError(f'{target}: row {i+1}, {key}: frozen JSON differs from CSV')
        else:
            output.mkdir(parents=True, exist_ok=True)
            with target.open('w', encoding='utf-8-sig', newline='') as handle:
                writer = csv.DictWriter(handle, fields, lineterminator='\r\n')
                writer.writeheader()
                writer.writerows(rows)
        manifest[name] = {'rows': len(rows), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=SNAPSHOT)
    p.add_argument('--check', action='store_true')
    args = p.parse_args()
    if not args.check and args.output.resolve() in {SNAPSHOT.resolve(), (ROOT/'agent'/'data').resolve()}:
        p.error('Export into a new directory; committed frozen data is not overwritten.')
    result = export(args.output, args.check)
    if args.check:
        for name in result:
            if (ROOT/'agent'/'data'/(name+'.csv')).read_bytes() != (SNAPSHOT/(name+'.csv')).read_bytes():
                raise ValueError('Application data copy differs from frozen snapshot: ' + name)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
