"""Public MaleCNS centerline geometry; independent of simulation activity."""
from __future__ import annotations
import math

SOURCE = 'https://storage.googleapis.com/flyem-male-cns/v1.0/segmentation/skeletons-malecns/skeletons-swc/'
ROI_SOURCE = 'https://storage.googleapis.com/flyem-male-cns/rois/fullbrain-roi-v4/'


def segment_regions(positions, edges, volume, resolution_nm, offset=(0, 0, 0)):
    """Sample official spatial labels at SWC edge midpoints; 0 stays unassigned.

    SWC units are 8 nm. Labels describe spatial compartments, not cell types.
    Out-of-volume fibers (including VNC) must never inherit a brain ROI.
    """
    import numpy as np
    points = np.asarray(positions).reshape(-1, 3)
    pairs = np.asarray(edges, dtype=int).reshape(-1, 2)
    voxels = np.floor(points[pairs].mean(axis=1) * 8 / np.asarray(resolution_nm)).astype(int) - offset
    valid = ((voxels >= 0) & (voxels < np.asarray(volume.shape))).all(axis=1)
    labels = np.zeros(len(pairs), dtype=np.uint16)
    labels[valid] = volume[tuple(voxels[valid].T)]
    return labels.tolist()


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
