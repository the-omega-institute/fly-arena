"""Color SWC segments from the official MaleCNS neuropil volume (offline only).

Install preprocessing dependency: uv pip install tensorstore
Run after prepare_morphology.py. No activity is synthesized or resimulated.
"""
import argparse
import colorsys
import json
from pathlib import Path
import urllib.request
import numpy as np
from flyarena.morphology import ROI_SOURCE, segment_regions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--morphology', type=Path, default=Path('data/connectome/morphology.json'))
    parser.add_argument('--cache', type=Path, default=Path('data/morphology-swc'))
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    def remote_json(name):
        return json.loads(urllib.request.urlopen(ROI_SOURCE + name, timeout=60).read())
    info = remote_json('info'); scale = info['scales'][3]
    props = remote_json('segment_properties/info')['inline']
    labels = next(p['values'] for p in props['properties'] if p['type'] == 'label')
    cache = args.cache / ('brain-roi-' + str(scale['resolution'][0]) + '.npy')
    if not cache.exists():
        import tensorstore as ts
        store = ts.open({'driver': 'neuroglancer_precomputed', 'kvstore': {
            'driver': 'http', 'base_url': ROI_SOURCE}, 'scale_index': 3}, open=True).result()
        np.save(cache, store.read().result())
    volume = np.load(cache, mmap_mode='r').reshape(scale['size'])
    data = json.loads(args.morphology.read_text())
    counts = {}
    for neuron in data['neurons']:
        neuron['edge_regions'] = segment_regions(neuron['positions'], neuron['edges'], volume,
                                                 scale['resolution'], scale['voxel_offset'])
        ids, totals = np.unique(neuron['edge_regions'], return_counts=True)
        for ident, total in zip(ids, totals):counts[int(ident)] = counts.get(int(ident), 0) + int(total)
    regions = []
    names = sorted({name.replace('(L)', '').replace('(R)', '') for name in labels})
    for ident, name in zip(props['ids'], labels):
        base = name.replace('(L)', '').replace('(R)', '')
        # Stable display palette; the spatial labels, not the hues, are source data.
        hue = (names.index(base) * .61803398875) % 1
        rgb = colorsys.hsv_to_rgb(hue, .60 if name.endswith('(L)') else .78, 1)
        regions.append({'id': int(ident), 'name': name, 'color': '#' + ''.join(f'{round(c*255):02x}' for c in rgb),
                        'segments': counts.get(int(ident), 0)})
    data['parcellation'] = {'source': ROI_SOURCE, 'scale': scale['key'],
        'resolution_nm': scale['resolution'], 'assignment': 'segment midpoint, nearest containing voxel',
        'regions': regions, 'unassigned_segments': counts.get(0, 0)}
    args.morphology.write_text(json.dumps(data, separators=(',', ':')))
    print(json.dumps({'assigned_segments': sum(v for k,v in counts.items() if k),
                      'unassigned_segments': counts.get(0,0), 'regions_present': len([k for k in counts if k])}))


if __name__ == '__main__':
    main()
