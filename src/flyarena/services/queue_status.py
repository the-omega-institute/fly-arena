"""Small queue estimate from actual progress and finished jobs; no GPU promise."""
import json
import statistics
import time


def queue_order(row, training, now):
    """Interactive jobs first; any job waiting ten minutes joins the oldest-first tier."""
    return (row['status'] != 'running',
            row['id'] in training and now - row['created'] < 600,
            row['created'], row['id'])


def queue_status(store):
    now=time.time()
    with store.db() as db:
        rows=[dict(r) for r in db.execute("SELECT id,status,progress,created,updated,request,attempt FROM matches WHERE status IN ('running','queued') ORDER BY created")]
        historical=[dict(r) for r in db.execute("SELECT request,created,updated FROM matches WHERE status='verified' ORDER BY updated DESC LIMIT 30")]
        training={r[0] for r in db.execute('SELECT match_id FROM training_evaluations')}
        research=db.execute("SELECT count(*) FROM experiments WHERE status IN ('running','queued')").fetchone()[0]
    estimates=[]
    for row in historical:
        req=json.loads(row['request']);units=req['duration_seconds']*len(req['fly_ids'])
        # created includes queue wait: conservative historical estimate, labeled below.
        if units:estimates.append((row['updated']-row['created'])/units)
    seconds_per_unit=statistics.median(estimates) if estimates else None
    rows.sort(key=lambda r: queue_order(r, training, now))
    wait=0.;unknown=bool(research);result={}
    for row in rows:
        req=json.loads(row['request']);duration=seconds_per_unit*req['duration_seconds']*len(req['fly_ids']) if seconds_per_unit else None
        remaining=duration*(1-row['progress']) if duration is not None else None
        result[row['id']]={'position':0 if row['status']=='running' else sum(r['status']=='queued' for r in rows[:rows.index(row)+1]),
            'queued_seconds':round(now-row['created']), 'estimated_wait_seconds':None if unknown else round(wait),
            'estimated_remaining_seconds':None if remaining is None else round(remaining),
            'estimate_samples':len(estimates),'estimate_basis':'Historical completion time including queue wait; approximate, not a deadline',
            'kind':'training' if row['id'] in training else 'match','backend':'cpu-numba',
            'research_running':bool(research)}
        if remaining is None:unknown=True
        else:wait+=remaining
    return result
