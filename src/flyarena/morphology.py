"""Public MaleCNS centerline geometry; independent of simulation activity."""
from __future__ import annotations
import math

SOURCE = 'https://storage.googleapis.com/flyem-male-cns/v1.0/segmentation/skeletons-malecns/skeletons-swc/'


def parse_swc(text: str) -> dict:
    """Keep source coordinates and every parent branch, including forest roots."""
    rows = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        values = line.split()
        if len(values) != 7:
            raise ValueError('SWC requires seven columns')
        ident, kind = int(values[0]), int(values[1])
        x, y, z, radius = map(float, values[2:6])
        parent = int(values[6])
        if ident < 0 or radius < 0 or not all(math.isfinite(v) for v in (x, y, z, radius)):
            raise ValueError('Invalid SWC geometry')
        rows.append((ident, kind, x, y, z, radius, parent))
    indices = {row[0]: i for i, row in enumerate(rows)}
    if not rows or len(indices) != len(rows):
        raise ValueError('Empty or duplicate SWC nodes')
    edges = []
    for i, row in enumerate(rows):
        parent = row[6]
        if parent == -1:
            continue
        if parent not in indices or parent == row[0]:
            raise ValueError('Invalid SWC parent')
        edges.extend((indices[parent], i))
    return {'positions': [v for row in rows for v in row[2:5]],
            'radii': [row[5] for row in rows], 'edges': edges}
