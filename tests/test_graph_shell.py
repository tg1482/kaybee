"""Tests for GraphShell command adapter and chaining semantics."""

import pytest

from kaybee import GraphShell, KnowledgeGraph


@pytest.fixture(params=["multi", "single"])
def sh(request):
    kg = KnowledgeGraph(mode=request.param)
    return GraphShell(kg)


def test_run_dispatches_command(sh) -> None:
    sh.run("touch", ["alpha", "hello"])
    assert sh.run("cat", ["alpha"]) == "hello"


def test_execute_pipe_works(sh) -> None:
    out = sh.execute("echo hello | grep hello")
    assert out == "hello"


def test_execute_and_short_circuit(sh) -> None:
    out = sh.execute("cat missing && echo should-not-run")
    assert "should-not-run" not in out


def test_execute_or_short_circuit(sh) -> None:
    out = sh.execute("cat missing || echo recovered")
    assert out == "recovered"


def test_execute_semicolon_continues_after_error(sh) -> None:
    out = sh.execute("cat missing ; echo continued")
    assert out == "continued"
