"""Legacy estimator: repair cycle/strand and period counting before production."""
from math import factorial

def estimate(q):
    m=q['counts'];n=sum(map(sum,m));degrees=[sum(row) for row in m]
    # Legacy assumption: any permutation preserving base totals is eligible.
    words=factorial(n)
    for count in degrees:words//=factorial(count)
    rotations=words//n
    strands=rotations//2
    rows=[]
    for d in range(1,n+1):
        if n%d==0:
            rows.append(dict(period=d,rotation_classes=str(rotations if d==n else 0),
                             self_reverse_complement='0',strand_classes=str(strands if d==n else 0)))
    return dict(length=n,linear_words=str(words),rotation_classes=str(rotations),strand_classes=str(strands),period_spectrum=rows)
