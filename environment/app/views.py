"""Output projection shared by existing reporting consumers."""
def render(observations,assignment):
    result=[]
    for row in observations:
        item=dict(row)
        if assignment[row['block']]:item['gt']='|'.join(reversed(row['gt'].split('|')))
        result.append(item)
    return sorted(result,key=lambda z:(z['chrom'],z['position'],z['sample'],z['id']))
