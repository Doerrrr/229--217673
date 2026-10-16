"""Orientation engine for the legacy forest input."""
from state import adjacency

def orient(variables,relations):
    graph=adjacency(variables,relations);answer={}
    for root in sorted(graph):
        if root in answer:continue
        answer[root]=0;stack=[root]
        while stack:
            u=stack.pop()
            for v,bit in graph[u]:
                want=answer[u]^bit
                if v in answer:
                    if answer[v]!=want:raise ValueError('orientation conflict')
                else:answer[v]=want;stack.append(v)
    return answer
