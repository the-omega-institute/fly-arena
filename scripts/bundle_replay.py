"""Create a small, read-only replay bundle for a deployment.

The Arena database and full neural checkpoints stay on the research machine.
This command copies only the public match record and the JSON artifacts needed
by the browser.  The immutable receipt is checked against every copied file so
the bundle cannot silently combine assets from different attempts.

Example::

    python scripts/bundle_replay.py --match-id aca9ac97af8a4cfcb863c3b45da5e857

The resulting directory can be sent explicitly with ``scripts/sync_mac.py``
using the ``var/research/replay-gallery-v1`` path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--match-id', required=True, help='Verified match id to publish')
    parser.add_argument('--db', type=Path, default=ROOT / 'var' / 'arena.sqlite3')
    parser.add_argument('--runs', type=Path, default=ROOT / 'var' / 'runs')
    parser.add_argument('--output', type=Path, default=ROOT / 'var' / 'research' / 'replay-gallery-v1')
    args = parser.parse_args()
    if not (len(args.match_id) == 32 and all(c in '0123456789abcdef' for c in args.match_id)):
        parser.error('--match-id must be a 32-character lowercase hex id')

    with sqlite3.connect(args.db) as db:
        db.row_factory = sqlite3.Row
        row = db.execute('SELECT * FROM matches WHERE id=?', (args.match_id,)).fetchone()
    if row is None:
        raise SystemExit(f'Match not found: {args.match_id}')
    if row['status'] != 'verified':
        raise SystemExit(f'Match is {row["status"]}; only verified replays can be bundled')

    attempt = int(row['attempt'] or 0)
    source = args.runs / args.match_id / str(attempt)
    required = ('scene', 'frames', 'events', 'receipt')
    paths = {name: source / f'{name}.json' for name in required}
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise SystemExit('Missing immutable replay assets:\n' + '\n'.join(missing))
    receipt = json.loads(paths['receipt'].read_text())
    recorded = receipt.get('files', {})
    expected_names = {'scene': 'scene.json', 'frames': 'frames.json', 'events': 'events.json'}
    mismatches = []
    for name, filename in expected_names.items():
        expected = recorded.get(filename)
        actual = sha256(paths[name])
        if expected and expected != actual:
            mismatches.append(f'{filename}: receipt={expected} actual={actual}')
    if mismatches:
        raise SystemExit('Receipt does not match this attempt:\n' + '\n'.join(mismatches))

    destination = args.output
    destination.mkdir(parents=True, exist_ok=True)
    for path in destination.glob(f'{args.match_id}-*'):
        if path.is_file():
            path.unlink()
    public = {
        'id': row['id'],
        'status': row['status'],
        'progress': row['progress'],
        'attempt': attempt,
        'request': json.loads(row['request']),
        'result': json.loads(row['result']) if row['result'] else None,
        'created': row['created'],
        'updated': row['updated'],
        'source': {
            'schema': 'replay-gallery-v1',
            'receipt_sha256': sha256(paths['receipt']),
            'full_run': f'var/runs/{args.match_id}/{attempt}',
            'excluded': ['arena.sqlite3', 'brain-*.npz', 'physics.npz', 'account fields'],
        },
    }
    (destination / f'{args.match_id}-match.json').write_text(json.dumps(public, ensure_ascii=False, indent=2) + '\n')
    for name, path in paths.items():
        shutil.copyfile(path, destination / f'{args.match_id}-{name}.json')
    print(json.dumps({'match_id': args.match_id, 'attempt': attempt,
                      'output': str(destination),
                      'bytes': sum(p.stat().st_size for p in destination.glob(f'{args.match_id}-*')),
                      'receipt_sha256': sha256(paths['receipt'])}, ensure_ascii=False))


if __name__ == '__main__':
    main()
