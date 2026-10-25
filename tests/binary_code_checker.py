"""Independent binary matrix multiplication and invertibility certificate checks."""

def check(q,result):
    try:
        permutation=result['permutation'];transform=result['row_transform'];n=q['n'];k=q['k']
        if type(permutation)is not list or len(permutation)!=n or any(type(v)is not int for v in permutation) or sorted(permutation)!=list(range(n)):return False
        if type(transform)is not list or len(transform)!=k or any(type(row)is not list or len(row)!=k or any(type(x)is not int or x not in (0,1) for x in row) for row in transform):return False
        a=[row[:] for row in transform];rank=0
        for col in range(k):
            pivot=next((i for i in range(rank,k) if a[i][col]),None)
            if pivot is None:continue
            a[rank],a[pivot]=a[pivot],a[rank]
            for i in range(rank+1,k):
                if a[i][col]:a[i]=[x^y for x,y in zip(a[i],a[rank])]
            rank+=1
        if rank!=k:return False
        return all(sum(transform[i][t]*q['left'][t][permutation[j]] for t in range(k))%2==q['right'][i][j] for i in range(k) for j in range(n))
    except (KeyError,TypeError,ValueError,IndexError):return False
