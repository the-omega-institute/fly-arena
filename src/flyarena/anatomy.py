"""Display actual soma coordinates without inventing positions or activity."""
import json
import math
from pathlib import Path


def build_anatomy(connectome: Path) -> dict:
    manifest = json.loads((connectome / 'manifest.json').read_text())
    neurons = json.loads((connectome / 'neurons.json').read_text())
    positions = []
    for neuron in neurons:
        position = neuron.get('position')
        if (isinstance(position, list) and len(position) == 3
                and all(type(v) in (int, float) and math.isfinite(v) for v in position)):
            positions.extend(position)
    count = len(positions) // 3
    return {'schema': 'connectome-anatomy/v1', 'connectome_sha256': manifest['sha256'],
            'neuron_count': len(neurons), 'position_count': count,
            'missing_position_count': len(neurons) - count, 'positions': positions,
            'coordinate_units': 'source somaLocation coordinates; no micrometer conversion applied',
            'scope': 'Anatomical soma locations only, not neural activity, surfaces or neurite paths.'}
