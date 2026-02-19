"""Tests for KnowledgeGraph.read() with depth."""

import pytest

from kaybee.core import KnowledgeGraph


@pytest.fixture
def kg():
    return KnowledgeGraph()


@pytest.fixture
def chain_kg(kg):
    """A -> B -> C chain."""
    kg.write("a", "---\ntype: concept\n---\nNode A links to [[b]].")
    kg.write("b", "---\ntype: concept\n---\nNode B links to [[c]].")
    kg.write("c", "---\ntype: concept\n---\nNode C is a leaf.")
    return kg


class TestReadDepthZero:
    def test_same_as_cat(self, chain_kg):
        assert chain_kg.read("a", depth=0) == chain_kg.cat("a")

    def test_default_depth_is_zero(self, chain_kg):
        assert chain_kg.read("a") == chain_kg.cat("a")

    def test_nonexistent_raises(self, kg):
        with pytest.raises(KeyError):
            kg.read("missing")


class TestReadDepthOne:
    def test_includes_direct_links(self, chain_kg):
        result = chain_kg.read("a", depth=1)
        assert "Node A links to [[b]]." in result
        assert "--- [[b]] ---" in result
        assert "Node B links to [[c]]." in result
        # c is depth=2 from a, should NOT appear
        assert "--- [[c]] ---" not in result

    def test_sorted_alphabetically(self, kg):
        kg.write("hub", "---\ntype: concept\n---\nLinks to [[zulu]] and [[alpha]].")
        kg.write("zulu", "---\ntype: concept\n---\nZ node.")
        kg.write("alpha", "---\ntype: concept\n---\nA node.")
        result = kg.read("hub", depth=1)
        alpha_pos = result.index("--- [[alpha]] ---")
        zulu_pos = result.index("--- [[zulu]] ---")
        assert alpha_pos < zulu_pos


class TestReadDepthTwo:
    def test_transitive(self, chain_kg):
        result = chain_kg.read("a", depth=2)
        assert "Node A links to [[b]]." in result
        assert "--- [[b]] ---" in result
        assert "--- [[c]] ---" in result
        assert "Node C is a leaf." in result


class TestReadCycles:
    def test_cycle_handled(self, kg):
        kg.write("x", "---\ntype: concept\n---\nX links to [[y]].")
        kg.write("y", "---\ntype: concept\n---\nY links to [[x]].")
        result = kg.read("x", depth=5)
        # x content appears once (root), y content once (linked)
        assert result.count("X links to [[y]].") == 1
        assert result.count("--- [[y]] ---") == 1
        # x should not appear as a linked section since it's the root
        assert "--- [[x]] ---" not in result


class TestReadEdgeCases:
    def test_unresolved_skipped(self, kg):
        kg.write("a", "---\ntype: concept\n---\nLinks to [[nonexistent]].")
        result = kg.read("a", depth=1)
        # Should just be the root content, no error
        assert "Links to [[nonexistent]]." in result
        assert "---" not in result.split("\n", 1)[-1] or "--- [[" not in result

    def test_diamond_dedup(self, kg):
        """A -> B, A -> C, B -> D, C -> D. D should appear only once."""
        kg.write("a", "---\ntype: concept\n---\n[[b]] and [[c]].")
        kg.write("b", "---\ntype: concept\n---\nB links to [[d]].")
        kg.write("c", "---\ntype: concept\n---\nC links to [[d]].")
        kg.write("d", "---\ntype: concept\n---\nD is shared.")
        result = kg.read("a", depth=2)
        assert result.count("--- [[d]] ---") == 1

    def test_leaf_node_safe(self, kg):
        kg.write("leaf", "---\ntype: concept\n---\nNo links here.")
        result = kg.read("leaf", depth=3)
        assert result == kg.cat("leaf")
