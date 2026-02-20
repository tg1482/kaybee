"""Tests for GraphShell command adapter and chaining semantics."""

from kaybee import GraphShell, KnowledgeGraph


def test_run_dispatches_command() -> None:
    kg = KnowledgeGraph()
    sh = GraphShell(kg)

    sh.run("touch", ["alpha", "hello"])
    assert sh.run("cat", ["alpha"]) == "hello"


def test_execute_pipe_works() -> None:
    kg = KnowledgeGraph()
    sh = GraphShell(kg)

    out = sh.execute("echo hello | grep hello")
    assert out == "hello"


def test_execute_and_short_circuit() -> None:
    kg = KnowledgeGraph()
    sh = GraphShell(kg)

    out = sh.execute("cat missing && echo should-not-run")
    assert "should-not-run" not in out


def test_execute_or_short_circuit() -> None:
    kg = KnowledgeGraph()
    sh = GraphShell(kg)

    out = sh.execute("cat missing || echo recovered")
    assert out == "recovered"


def test_execute_semicolon_continues_after_error() -> None:
    kg = KnowledgeGraph()
    sh = GraphShell(kg)

    out = sh.execute("cat missing ; echo continued")
    assert out == "continued"
