"""Shared fixtures for KnowledgeGraph tests."""

import pytest

from grapy.core import KnowledgeGraph


@pytest.fixture
def kg():
    """Fresh in-memory KnowledgeGraph."""
    return KnowledgeGraph()


@pytest.fixture
def populated_kg():
    """KnowledgeGraph pre-loaded with a small knowledge base."""
    kg = KnowledgeGraph()
    kg.add_type("concept")
    kg.add_type("person")

    kg.write(
        "spreading-activation",
        "---\ntype: concept\ndescription: How activation propagates\ntags: [graph, cognition]\n---\n"
        "Spreading activation follows [[agent-traversal]] paths\n"
        "and uses [[semantic-similarity]].",
    )
    kg.write(
        "agent-traversal",
        "---\ntype: concept\ndescription: How agents navigate graphs\ntags: [graph, agents]\n---\n"
        "Traversal uses [[spreading-activation]].",
    )
    kg.write(
        "semantic-similarity",
        "---\ntype: concept\ndescription: Measuring meaning overlap\ntags: [nlp, embeddings]\n---\n"
        "Quantifies closeness of meanings.",
    )
    kg.write(
        "turing",
        "---\ntype: person\nrole: researcher\nborn: 1912\n---\n"
        "Alan Turing pioneered computation and [[agent-traversal]].",
    )
    kg.touch("readme", "Welcome to the knowledge graph.")
    return kg
