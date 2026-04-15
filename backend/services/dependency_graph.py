# backend/services/dependency_graph.py
from collections import deque
from typing import Any


class CyclicDependencyError(Exception):
    pass


def validate_dependency_graph(sessions: list[dict[str, Any]]) -> bool:
    if not sessions:
        return True

    producers: dict[str, int] = {}
    for i, s in enumerate(sessions):
        for f in s.get("produces", []):
            producers[f] = i

    all_produced = set(producers.keys())
    for s in sessions:
        for dep in s.get("depends_on", []):
            if dep not in all_produced:
                raise ValueError(f"Unresolved dependency: '{dep}' is not produced by any session")

    n = len(sessions)
    adj: list[list[int]] = [[] for _ in range(n)]
    in_degree = [0] * n

    for i, s in enumerate(sessions):
        for dep in s.get("depends_on", []):
            if dep in producers:
                parent = producers[dep]
                if parent == i:
                    raise CyclicDependencyError(
                        f"Self-dependency: session '{s['agent_name']}' depends on file it produces"
                    )
                adj[parent].append(i)
                in_degree[i] += 1

    queue = deque(i for i in range(n) if in_degree[i] == 0)
    visited = 0

    while queue:
        node = queue.popleft()
        visited += 1
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if visited != n:
        raise CyclicDependencyError("Cyclic dependency detected among sessions")

    return True
