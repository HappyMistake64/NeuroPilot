"""Trusted comparison of measured resource use; unknown telemetry is never zero."""
import math
import statistics
from .common import RSIError


def efficiency_comparison(parent, candidate, min_percent=15):
    def keyed(rows):
        result={}
        for row in rows:
            key=(row['task'],row['seed'])
            if key in result: raise RSIError('Duplicate task/seed measurement')
            result[key]=row
        return result
    a,b=keyed(parent),keyed(candidate)
    if not a or a.keys()!=b.keys(): raise RSIError('Unpaired resource measurements')
    same_outcomes=all(a[k]['resolved']==b[k]['resolved'] for k in a)
    stable=all(len({r['resolved'] for r in rows if r['task']==task})==1
               for rows in (parent,candidate) for task in {r['task'] for r in rows})
    def tokens(row):
        value=row.get('usage',{}).get('actual_tokens')
        return value if type(value) is int and value>=0 else None
    av,bv=[tokens(a[k]) for k in a],[tokens(b[k]) for k in a]
    known=all(x is not None for x in av+bv)
    p,c=(sum(av),sum(bv)) if known else (None,None)
    savings=(p-c)/p*100 if known and p>0 else None
    # All tasks count, including failed attempts. A cheaper zero-success agent is not accepted.
    passed=bool(same_outcomes and stable and any(r['resolved'] for r in parent)
                and savings is not None and savings+1e-9>=min_percent)
    def median_time(rows):
        values=[r.get('elapsed') for r in rows]
        if not all(type(v) in (int,float) and math.isfinite(v) and v>=0 for v in values):return None
        return statistics.median(values)
    return {'gate_passed':passed,'metric':'actual_tokens','required_saving_percent':min_percent,
            'parent_tokens':p,'candidate_tokens':c,'saving_percent':savings,
            'telemetry_complete':known,'same_outcomes':same_outcomes,'stable':stable,
            'parent_median_seconds':median_time(parent),'candidate_median_seconds':median_time(candidate),
            'interpretation':'Efficiency only; timing is descriptive and not an acceptance gate.'}
