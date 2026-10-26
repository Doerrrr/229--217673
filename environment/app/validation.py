def validate(q):
    if not isinstance(q,dict) or set(q)!={'id','counts'}:raise ValueError('query fields')
    m=q['counts']
    if type(m)is not list or len(m)!=4 or any(type(row)is not list or len(row)!=4 for row in m):raise ValueError('counts shape')
    if any(type(x)is not int or not 0<=x<=96 for row in m for x in row):raise ValueError('counts integer')
    if not 1<=sum(map(sum,m))<=96:raise ValueError('total count')
