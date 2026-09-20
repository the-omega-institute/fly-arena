"""Download real MaleCNS SWCs for replay neurons and a bounded context sample.

No activity is synthesized. Existing SWCs are reused; no brain simulation runs.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import urllib.error
import urllib.request
from flyarena.morphology import SOURCE, parse_swc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connectome', type=Path, default=Path('data/connectome'))
    parser.add_argument('--frames', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('data/connectome/morphology.json'))
    parser.add_argument('--cache', type=Path, default=Path('data/morphology-swc'))
    args = parser.parse_args()
    meta = json.loads((args.connectome/'neurons.json').read_text())
    by_id = {n['id']: n for n in meta}
    frame = json.loads(args.frames.read_text())[0]
    ids = {n['id'] for brain in frame['brain'] for n in brain.get('sampled_nodes', brain.get('top_nodes', []))}
    # Uniform index spacing within each source-annotated superclass; structure only.
    for group, count in [('ol_intrinsic', 64), ('visual_projection', 32), ('cb_intrinsic', 32),
                         ('cb_sensory', 16), ('descending_neuron', 12), ('visual_centrifugal', 12)]:
        members = [n for n in meta if n['superclass'] == group]
        ids.update(members[min(len(members)-1, i*len(members)//count)]['id'] for i in range(min(count, len(members))))
    args.cache.mkdir(parents=True, exist_ok=True)
    def fetch(ident):
        node = by_id[ident];path = args.cache/(ident+'.swc')
        try:
            if not path.exists():
                raw = urllib.request.urlopen(SOURCE+ident+'.swc', timeout=45).read()
                path.write_bytes(raw)
            shape = parse_swc(path.read_text())
            return {'id':ident, 'type':node['type'], 'class':node['class'],
                    'superclass':node['superclass'], 'side':node['side'], **shape}
        except urllib.error.HTTPError as error:
            if error.code != 404:raise
            return None
    with ThreadPoolExecutor(max_workers=6) as pool:
        neurons = list(pool.map(fetch, sorted(ids, key=int)))
    absent = [ident for ident, neuron in zip(sorted(ids, key=int), neurons) if neuron is None]
    neurons = [n for n in neurons if n is not None]
    result = {'schema':'connectome-morphology/v1',
              'connectome_sha256':json.loads((args.connectome/'manifest.json').read_text())['sha256'],
              'source':SOURCE, 'license':'CC-BY-4.0', 'attribution':'Male CNS Connectome, Berg et al., Cell (2026); FlyEM / Janelia and collaborators',
              'coordinate_space':'MaleCNS v1.0 EM', 'coordinate_unit_nm':8,
              'selection':'Replay sample neurons plus uniformly spaced source-annotated superclass context; not the whole CNS.',
              'missing_ids':absent, 'neurons':neurons}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, separators=(',',':')))
    print(json.dumps({'neurons':len(neurons), 'missing':absent,
                      'segments':sum(len(n['edges'])//2 for n in neurons), 'bytes':args.output.stat().st_size}))


if __name__ == '__main__':
    main()
