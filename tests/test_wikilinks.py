"""Tests for wikilink resolution, link extraction, backlinks, and graph adjacency."""

import pytest

from kaybee.core import KnowledgeGraph, slugify


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
        t = "_data"
        assert len(kg.query(f"SELECT * FROM {t} WHERE name = 'item'")) == 1
        kg.rm("item")
        assert len(kg.query(f"SELECT * FROM {t} WHERE name = 'item'")) == 0

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
        t = "_data"
        rows = kg.query(f"SELECT name FROM {t} WHERE name = 'moved'")
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


class TestSlugIndex:
    def test_slug_populated_on_write(self, kg):
        kg.write("hello-world", "content")
        rows = kg.query("SELECT slug FROM nodes WHERE name = 'hello-world'")
        assert rows[0][0] == "hello-world"

    def test_slug_populated_on_touch(self, kg):
        kg.touch("my-node")
        rows = kg.query("SELECT slug FROM nodes WHERE name = 'my-node'")
        assert rows[0][0] == "my-node"

    def test_slug_populated_on_mv(self, kg):
        kg.touch("old-name", "content")
        kg.mv("old-name", "new-name")
        rows = kg.query("SELECT slug FROM nodes WHERE name = 'new-name'")
        assert rows[0][0] == "new-name"

    def test_slug_populated_on_cp(self, kg):
        kg.touch("original", "content")
        kg.cp("original", "copy")
        rows = kg.query("SELECT slug FROM nodes WHERE name = 'copy'")
        assert rows[0][0] == "copy"

    def test_resolve_uses_slug_index(self, kg):
        kg.touch("agent-traversal", "content")
        result = kg.resolve_wikilink("Agent Traversal", fuzzy=True)
        assert result == "agent-traversal"

    def test_migration_backfill(self, tmp_path):
        """Simulate opening an old DB without slug column."""
        import sqlite3
        db_path = str(tmp_path / "test.db")
        # Create a DB with old schema (no slug column)
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS nodes (
                name TEXT PRIMARY KEY,
                type TEXT NOT NULL DEFAULT 'kaybee'
            );
            CREATE TABLE IF NOT EXISTS _types (type_name TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS _links (
                source_name TEXT NOT NULL,
                target_name TEXT NOT NULL,
                target_resolved TEXT,
                context TEXT,
                PRIMARY KEY (source_name, target_name)
            );
            CREATE TABLE IF NOT EXISTS _data (
                name TEXT PRIMARY KEY,
                content TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS _type_fields (
                type_name TEXT NOT NULL,
                field_name TEXT NOT NULL,
                PRIMARY KEY (type_name, field_name)
            );
        """)
        conn.execute("INSERT INTO nodes (name, type) VALUES ('existing-node', 'kaybee')")
        conn.execute("INSERT INTO _data (name, content) VALUES ('existing-node', 'hello')")
        conn.commit()
        conn.close()
        # Open with KnowledgeGraph — migration should backfill slug
        kg = KnowledgeGraph(db_path)
        rows = kg.query("SELECT slug FROM nodes WHERE name = 'existing-node'")
        assert rows[0][0] == slugify("existing-node")
