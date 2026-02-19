"""Tests for wikilink resolution, link extraction, backlinks, and graph adjacency."""

import pytest

from kaybee.core import KnowledgeGraph


class TestWikilinkExtraction:
    def test_links_extracted_on_write(self, kg):
        kg.write("a", "See [[target-one]] and [[target-two]].")
        links = kg.wikilinks("a")
        assert "target-one" in links
        assert "target-two" in links

    def test_no_wikilinks(self, kg):
        kg.write("plain", "No links here.")
        assert kg.wikilinks("plain") == []

    def test_wikilinks_from_body_not_frontmatter(self, kg):
        kg.write("note", "---\ntype: concept\n---\nBody with [[link]].")
        links = kg.wikilinks("note")
        assert "link" in links

    def test_wikilinks_nonexistent_returns_empty(self, kg):
        assert kg.wikilinks("nope") == []

    def test_wikilinks_on_empty_file(self, kg):
        kg.touch("empty")
        assert kg.wikilinks("empty") == []

    def test_duplicate_wikilinks_deduped_by_pk(self, kg):
        kg.write("note", "See [[target]] and also [[target]].")
        links = kg.wikilinks("note")
        assert links == ["target"]

    def test_overwrite_updates_links(self, kg):
        kg.write("note", "Links to [[a]].")
        assert kg.wikilinks("note") == ["a"]
        kg.write("note", "Now links to [[b]].")
        assert kg.wikilinks("note") == ["b"]


class TestWikilinkResolution:
    def test_resolve_exact(self, kg):
        kg.touch("agent-traversal", "content")
        result = kg.resolve_wikilink("agent-traversal")
        assert result == "agent-traversal"

    def test_resolve_fuzzy(self, kg):
        kg.touch("agent-traversal", "content")
        result = kg.resolve_wikilink("Agent Traversal", fuzzy=True)
        assert result == "agent-traversal"

    def test_resolve_no_match(self, kg):
        assert kg.resolve_wikilink("nonexistent") is None

    def test_resolve_exact_only(self, kg):
        kg.touch("agent-traversal", "content")
        result = kg.resolve_wikilink("Agent Traversal", fuzzy=False)
        assert result is None

    def test_links_resolved_on_write(self, kg):
        kg.write("target", "I exist.")
        kg.write("source", "Links to [[target]].")
        rows = kg.query(
            "SELECT target_resolved FROM _links WHERE source_name = 'source'"
        )
        assert len(rows) == 1
        assert rows[0][0] == "target"

    def test_unresolved_link(self, kg):
        kg.write("note", "See [[nonexistent]].")
        rows = kg.query("SELECT target_resolved FROM _links WHERE source_name = 'note'")
        assert rows[0][0] is None

    def test_link_resolves_later(self, kg):
        kg.write("note", "See [[target]].")
        rows = kg.query("SELECT target_resolved FROM _links WHERE source_name = 'note'")
        assert rows[0][0] is None

        kg.write("target", "I exist now.")
        rows = kg.query("SELECT target_resolved FROM _links WHERE source_name = 'note'")
        assert rows[0][0] == "target"


class TestBacklinks:
    def test_basic(self, kg):
        kg.write("a", "Links to [[b]].")
        kg.write("b", "Target.")
        bl = kg.backlinks("b")
        assert "a" in bl

    def test_bidirectional(self, kg):
        kg.write("a", "Links to [[b]].")
        kg.write("b", "Links to [[a]].")
        assert "b" in kg.backlinks("a")
        assert "a" in kg.backlinks("b")

    def test_symlink_backlinks(self, kg):
        kg.touch("target", "data")
        kg.ln("target", "link")
        bl = kg.backlinks("target")
        assert "link" in bl

    def test_no_backlinks(self, kg):
        kg.touch("isolated", "no links to me")
        assert kg.backlinks("isolated") == []

    def test_multiple_backlinks(self, kg):
        kg.touch("target", "exists")
        kg.write("a", "Links to [[target]].")
        kg.write("b", "Also [[target]].")
        bl = kg.backlinks("target")
        assert "a" in bl
        assert "b" in bl

    def test_backlinks_nonexistent(self, kg):
        bl = kg.backlinks("nope")
        assert bl == []


class TestGraphAdjacency:
    def test_basic(self, kg):
        kg.write("a", "Links to [[b]].")
        kg.write("b", "Links to [[a]].")
        g = kg.graph()
        assert "a" in g
        assert "b" in g
        assert "b" in g["a"]
        assert "a" in g["b"]

    def test_empty_graph(self, kg):
        assert kg.graph() == {}

    def test_unresolved_not_in_graph(self, kg):
        kg.write("note", "Links to [[nonexistent]].")
        g = kg.graph()
        assert g == {}

    def test_one_directional(self, kg):
        kg.touch("target", "exists")
        kg.write("source", "Links to [[target]].")
        g = kg.graph()
        assert "source" in g
        assert "target" in g["source"]
        assert "target" not in g


class TestRmCleansGraph:
    def test_rm_cleans_type_table(self, kg):
        kg.write("item", "---\ntype: concept\ndescription: test\n---\nBody.")
        assert len(kg.query("SELECT * FROM concept")) == 1
        kg.rm("item")
        assert len(kg.query("SELECT * FROM concept")) == 0

    def test_rm_cleans_outgoing_links(self, kg):
        kg.write("a", "Links to [[b]].")
        kg.write("b", "Target.")
        assert len(kg.query("SELECT * FROM _links WHERE source_name = 'a'")) == 1
        kg.rm("a")
        assert len(kg.query("SELECT * FROM _links WHERE source_name = 'a'")) == 0

    def test_rm_nullifies_incoming_links(self, kg):
        kg.write("a", "Links to [[b]].")
        kg.write("b", "Target.")
        kg.rm("b")
        rows = kg.query("SELECT target_resolved FROM _links WHERE source_name = 'a'")
        assert len(rows) == 1
        assert rows[0][0] is None


class TestMvCpGraph:
    def test_mv_preserves_type(self, kg):
        kg.write("item", "---\ntype: concept\ndescription: test\n---\nBody.")
        kg.mv("item", "moved")
        assert kg.find_by_type("concept") == ["moved"]
        rows = kg.query("SELECT name FROM concept")
        assert rows[0][0] == "moved"

    def test_mv_updates_links(self, kg):
        kg.touch("target", "exists")
        kg.write("source", "Links to [[target]].")
        kg.mv("source", "new-source")
        rows = kg.query("SELECT source_name FROM _links")
        assert rows[0][0] == "new-source"

    def test_mv_updates_incoming_links(self, kg):
        kg.write("source", "Links to [[target]].")
        kg.touch("target", "exists")
        rows = kg.query("SELECT target_resolved FROM _links WHERE source_name = 'source'")
        assert rows[0][0] == "target"
        kg.mv("target", "new-target")
        rows = kg.query("SELECT target_resolved FROM _links WHERE source_name = 'source'")
        assert rows[0][0] == "new-target"

    def test_cp_preserves_type(self, kg):
        kg.write("item", "---\ntype: concept\ndescription: test\n---\nBody.")
        kg.cp("item", "copy")
        result = kg.find_by_type("concept")
        assert "item" in result
        assert "copy" in result

    def test_cp_copies_links(self, kg):
        kg.touch("target", "exists")
        kg.write("source", "Links to [[target]].")
        kg.cp("source", "copy")
        rows = kg.query("SELECT source_name FROM _links WHERE source_name = 'copy'")
        assert len(rows) == 1
