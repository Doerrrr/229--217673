"""The batch adapter's in-process record table."""
def apply(rows):
    current={}
    for row in rows:
        if row['op']=='PUT':current[(row['kind'],row['id'])]=row['record']
        elif row['op']=='DELETE':current.pop((row['kind'],row['id']),None)
    return current

def adjacency(variables,relations):
    graph={v:[] for v in variables}
    for r in relations:
        graph[r['a']].append((r['b'],r['bit']));graph[r['b']].append((r['a'],r['bit']))
    return graph
