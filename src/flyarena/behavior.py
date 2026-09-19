"""Versioned behavioral fitness derived from recorded body poses and intake events."""
from __future__ import annotations

import math
import numpy as np

SUSTAINED_FORAGING = "sustained-foraging-v1"
FITNESS_OBJECTIVES = [
    {"id": "food", "name": "Food collected", "ready": True},
    {"id": SUSTAINED_FORAGING, "name": "Sustained foraging", "ready": True},
]


def behavior_metrics(scene, frames, events, count, physics_dt):
    """No invented posture for old replays. Upright is relative to initial pose.

    Intervals use the posture of their left sample (zero-order hold); intake
    after the temporal midpoint comes from the event clock, not animation.
    This is an engineering selection objective, not a biological fitness claim.
    """
    results = []
    for slot in range(count):
        try:
            index = next(i for i, g in enumerate(scene['body']['geoms'])
                         if g['slot'] == slot and g.get('name', '').endswith('/c_thorax'))
            times = np.asarray([f['time'] for f in frames], dtype=float)
            quats = np.asarray([f['poses'][index][3:7] for f in frames], dtype=float)
            if (len(times) < 2 or not np.isfinite(times).all() or np.any(np.diff(times) <= 0)
                    or quats.shape != (len(times), 4) or not np.isfinite(quats).all()):
                raise ValueError('Incomplete posture observations')
            norms = np.linalg.norm(quats, axis=1)
            if np.any(norms <= 0):
                raise ValueError('Invalid quaternion')
            quats = quats / norms[:, None]
            a, b, c, d = quats[0]
            w, x, y, z = quats.T
            qx = -w*b + x*a - y*d + z*c
            qy = -w*c + x*d + y*a - z*b
            upright = 1 - 2*(qx*qx + qy*qy) >= 0
            duration = float(times[-1] - times[0])
            fraction = min(1., max(0., math.fsum(float(dt) for dt, up in zip(np.diff(times), upright[:-1]) if up) / duration))
            midpoint = float((times[0] + times[-1]) / 2)
            intake = [e for e in events if e['type'] == 'intake' and e['slot'] == slot]
            food = sum(float(e['amount']) for e in intake)
            late = sum(float(e['amount']) for e in intake if e['tick'] * physics_dt > midpoint)
            if not math.isfinite(food + late) or food < 0 or late < 0:
                raise ValueError('Invalid intake observations')
            first = next((float(t) for t, up in zip(times, upright) if not up), None)
            results.append(dict(schema=SUSTAINED_FORAGING, food=food, latter_half_food=late,
                                upright_fraction=fraction, recorded_seconds=duration,
                                first_inversion_s=first, fitness=(food + late)*fraction))
        except (KeyError, IndexError, TypeError, ValueError, StopIteration):
            results.append(None)
    return results


def selection_score(result, slot, objective):
    if objective == 'food':
        return result['scores'][slot]
    metrics = result.get('behavior', [])
    metric = metrics[slot] if slot < len(metrics) else None
    if not metric or metric.get('schema') != SUSTAINED_FORAGING:
        return None
    value = metric.get('fitness')
    return value if isinstance(value, (int, float)) and math.isfinite(value) else None
