"""Static prospective seams. No executable scientific runner or model import."""
from copy import deepcopy
from . import PROFILE, CONTROL, READY
from .contracts import ContractError

CASES=(('zero',0.,0.),('straight-008',.08,0.),('straight-02',.2,0.),
       ('straight-04',.4,0.),('turn-negative-04',.2,-.4),('turn-positive-04',.2,.4),
       ('turn-negative-08',.2,-.8),('turn-positive-08',.2,.8))


def plan():
    return {
        'schema':'contact-realization-prospective/v1','ready':False,
        'science_authorized':False,'candidate':PROFILE,'control':CONTROL,
        'development':[(profile,seed,case) for seed in (42,43) for case in CASES for profile in (CONTROL,PROFILE)],
        'heldout':[(PROFILE,seed,case) for seed in (31042,31043) for case in CASES],
        'repeat':(PROFILE,31042,CASES[2]),'trial_ticks':40000,'dt':.0001,
        'active_ticks':[3000,25000],'analysis_ticks':[6000,25000],
        'checkpoint_tick':10000,'continuation_ticks':100,
        'development_seconds':128.,'conditional_total_seconds':196.01,'hard_seconds':260.,
        'original_neural_product_seconds':259.,'neural_seconds_authorized':0.,
        'source_boundary':'New adapter/controller only; immutable baseline v16 and matched physical model/input.',
        'analysis':'Keep unmodified analyze_v16 intent-window path; a separately labeled realized-window adapter supplies realized phases. Require both original and realized results, with every condition and failed/inconclusive/partial cycle retained.',
        'failure':'Stall/phase-bound failure marks the trial and missing remainder failed/incomplete, never drops denominators. Continue fixed safe development unless existing unsafe/resource/retention stop policy blocks. Any failure/inconclusive prevents heldout/repeat/restore and downstream work.',
        'required_registration':['source and selected-law hashes','compiled model and original MJB identity','native dependency/asset/input hashes','subject identity','observation/output maps and exact clock','all phase/mode/contact schemas','unchanged gate versions','condition order','resources and retention closure','independent review dispositions'],
        'unrun_native_contracts':['binding validation','coherent material transport at actual model state','two-pose excursion','native action mapping','whole native cache checkpoint/restore','all physical gates'],
    }


def require_admission(intent,realized,expected_trial_ids):
    """Pure report join, never computes or replaces the authoritative gate metrics."""
    expected=set(expected_trial_ids)
    if len(expected)!=len(expected_trial_ids): raise ContractError('duplicate expected trial')
    required={'trial_id','complete','all_original_gates_pass','inconclusive','controller_failure','missing_remainder','partials_retained'}
    def collect(rows):
        result={}
        for row in rows:
            if not isinstance(row,dict) or set(row)!=required or row['trial_id'] in result:
                raise ContractError('gate report schema/duplicate')
            if any(type(row[key]) is not bool for key in required-{'trial_id'}): raise ContractError('gate report booleans')
            result[row['trial_id']]=row
        if set(result)!=expected: raise ContractError('missing/extra trial denominator')
        return result
    left=collect(intent); right=collect(realized)
    failures=[]
    for key in sorted(expected):
        for label,rows in (('intent',left),('realized',right)):
            row=rows[key]
            passed=(row['complete'] and row['all_original_gates_pass'] and not row['inconclusive']
                    and not row['controller_failure'] and not row['missing_remainder'] and row['partials_retained'])
            if not passed: failures.append((key,label))
    return {'mechanical_admission':not failures,'ready':False,'failures':failures,
            'science_execution_authorized':False,'original_intent':deepcopy(left),'realized':deepcopy(right)}
