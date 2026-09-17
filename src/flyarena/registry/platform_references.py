"""Server seed definitions; labels never establish reference authority."""
from __future__ import annotations
import json
import time
from ..common import canonical, digest
from ..contracts import FlySpec

PRESETS = [
    ('wildtype', 'Wild Type / 原型', 'mint', []),
    ('official', 'Nectar / 花蜜', 'amber', [{'selector':'olfactory','scale':1.18}, {'selector':'projection','scale':1.10}]),
]


def initialize_references(store, compiler):
    graph_sha = compiler.graph.manifest['sha256']
    release = 'canonical-seeds-v1-' + digest({'graph':graph_sha, 'presets':PRESETS, 'profile':'malecns-lif-cpu-v1'})[:16]
    references = {}
    for role,name,color,mutations in PRESETS:
        spec = FlySpec(name=name,color=color,connectome_sha256=graph_sha,weight_mutations=mutations)
        report = compiler.compile(spec,publish=True,root=store.root)
        compiler.load_weights(report['artifact_id'],store.root)
        definition = {'release_id':release,'role':role,'spec':spec.model_dump(by_alias=True),'artifact_id':report['artifact_id']}
        ident = digest(definition)[:32]
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT * FROM flies WHERE id=?', (ident,)).fetchone()
            if existing:
                if existing['owner'] != 'arena' or json.loads(existing['spec']) != definition['spec'] or existing['artifact_id'] != report['artifact_id']:
                    raise ValueError('Trusted reference identity collision')
            else:
                db.execute('INSERT INTO flies VALUES(?,?,?,?,?,?,?,?)', (ident,'arena',name,color,canonical(definition['spec']).decode(),report['artifact_id'],canonical(report).decode(),time.time()))
            old = db.execute('SELECT definition FROM research_references WHERE release_id=? AND role=?', (release,role)).fetchone()
            if old and json.loads(old[0]) != definition:
                raise ValueError('Immutable reference definition mismatch')
            db.execute('INSERT OR IGNORE INTO research_references VALUES(?,?,?,?)', (release,role,ident,canonical(definition).decode()))
            db.execute('INSERT OR IGNORE INTO fly_provenance VALUES(?,?,?,?,?)', (ident,role,release,'seed',digest(definition)))
        references[role] = store.fly(ident)
    return references
