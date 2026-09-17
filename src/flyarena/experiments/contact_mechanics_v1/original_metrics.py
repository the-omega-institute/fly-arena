"""Load unchanged pure metric definitions without importing old native runners."""
import ast
from functools import lru_cache
from pathlib import Path
import numpy as np
from .schema import DT

@lru_cache(maxsize=64)
def helpers(lo=6000,hi=25000):
    if not 6000<=lo<hi<=25000:raise ValueError("retained active window")
    base=Path(__file__).resolve().parent.parent
    scope={'np':np,'DT':DT,'LEGS':('lf','lm','lh','rf','rm','rh'),'ANALYSIS_TICKS':(lo,hi)}
    groups={'behavior_v12_correction.py':('_phase_increment_failures','_phase_window_contract','_partition_true_runs','_longest_true','_median31','_cycle_metrics'),
            'verify_behavior_v12_correction.py':('_longest','_runs','_cycle_gate')}
    for filename,names in groups.items():
        tree=ast.parse((base/filename).read_text());nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
        if {n.name for n in nodes}!=set(names):raise ValueError('original metric function closure')
        if filename=='verify_behavior_v12_correction.py' and (lo,hi)!=(6000,25000):
            class ClippedWindow(ast.NodeTransformer):
                # Only absolute window constants change; mathematics/thresholds remain original.
                def visit_Constant(self,node):
                    if type(node.value) is int and node.value in (6000,25000,25001):return ast.copy_location(ast.Constant({6000:lo,25000:hi,25001:hi+1}[node.value]),node)
                    return node
            nodes=[ClippedWindow().visit(n) for n in nodes]
        module=ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[]))
        exec(compile(module,str(base/filename),'exec'),scope)
    return scope['_cycle_metrics'],scope['_cycle_gate'],scope['_phase_window_contract']
