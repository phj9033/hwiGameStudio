# tests/test_dependency_graph.py
import pytest
from backend.services.dependency_graph import validate_dependency_graph, CyclicDependencyError


def test_valid_linear_graph():
    sessions = [
        {"agent_name": "designer", "depends_on": [], "produces": ["gdd.md"]},
        {"agent_name": "developer", "depends_on": ["gdd.md"], "produces": ["spec.md"]},
    ]
    assert validate_dependency_graph(sessions) is True


def test_valid_parallel_graph():
    sessions = [
        {"agent_name": "designer", "depends_on": [], "produces": ["gdd.md"]},
        {"agent_name": "artist", "depends_on": [], "produces": ["art.md"]},
        {"agent_name": "developer", "depends_on": ["gdd.md", "art.md"], "produces": ["spec.md"]},
    ]
    assert validate_dependency_graph(sessions) is True


def test_cyclic_dependency_raises():
    sessions = [
        {"agent_name": "a", "depends_on": ["b.md"], "produces": ["a.md"]},
        {"agent_name": "b", "depends_on": ["a.md"], "produces": ["b.md"]},
    ]
    with pytest.raises(CyclicDependencyError):
        validate_dependency_graph(sessions)


def test_self_dependency_raises():
    sessions = [
        {"agent_name": "a", "depends_on": ["a.md"], "produces": ["a.md"]},
    ]
    with pytest.raises(CyclicDependencyError):
        validate_dependency_graph(sessions)


def test_unresolved_dependency_raises():
    sessions = [
        {"agent_name": "a", "depends_on": ["nonexistent.md"], "produces": ["a.md"]},
    ]
    with pytest.raises(ValueError, match="(?i)unresolved"):
        validate_dependency_graph(sessions)


def test_empty_sessions():
    assert validate_dependency_graph([]) is True
