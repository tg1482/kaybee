"""Edge cases and corner cases for KnowledgeGraph."""

import pytest

from grapy.core import KnowledgeGraph


class TestContentEdgeCases:
    def test_empty_content(self, kg):
        kg.touch("empty")
        assert kg.cat("empty") == ""
        assert kg.body("empty") == ""
        assert kg.frontmatter("empty") == {}

    def test_only_frontmatter_no_body(self, kg):
        kg.write("meta-only", "---\ntype: concept\n---\n")
        assert kg.frontmatter("meta-only") == {"type": "concept"}
        assert kg.body("meta-only") == ""

    def test_content_with_dashes(self, kg):
        kg.write("note", "Some text with --- in the middle")
        assert kg.cat("note") == "Some text with --- in the middle"

    def test_unicode_content(self, kg):
        kg.write("unicode", "Hello 世界 🌍")
        assert kg.cat("unicode") == "Hello 世界 🌍"

    def test_multiline_body(self, kg):
        kg.write("multi", "---\ntype: note\n---\nLine 1\nLine 2\nLine 3")
        assert kg.body("multi") == "Line 1\nLine 2\nLine 3"

    def test_very_long_content(self, kg):
        long_text = "x" * 10000
        kg.write("long", long_text)
        assert kg.cat("long") == long_text


class TestWikilinkEdgeCases:
    def test_wikilink_to_self(self, kg):
        kg.write("note", "See [[note]].")
        links = kg.wikilinks("note")
        assert "note" in links
        rows = kg.query("SELECT target_resolved FROM _links WHERE source_name = 'note'")
        assert rows[0][0] == "note"

    def test_wikilink_with_special_chars(self, kg):
        kg.touch("my-node", "exists")
        kg.write("note", "See [[my-node]].")
        rows = kg.query("SELECT target_resolved FROM _links WHERE source_name = 'note'")
        assert rows[0][0] == "my-node"

    def test_wikilink_case_mismatch_fuzzy(self, kg):
        kg.touch("hello-world", "exists")
        kg.write("note", "See [[Hello World]].")
        rows = kg.query("SELECT target_resolved FROM _links WHERE source_name = 'note'")
        assert rows[0][0] == "hello-world"

    def test_link_context_captured(self, kg):
        kg.write("note", "First line\nSee [[target]] here\nLast line")
        rows = kg.query("SELECT context FROM _links WHERE source_name = 'note'")
        assert "See [[target]] here" in rows[0][0]


class TestTypeEdgeCases:
    def test_add_type_idempotent(self, kg):
        kg.add_type("concept")
        kg.add_type("concept")  # should not raise
        assert kg.types() == ["concept"]

    def test_remove_type_empty(self, kg):
        kg.add_type("concept")
        kg.remove_type("concept")
        assert "concept" not in kg.types()

    def test_remove_type_nonempty_raises(self, kg):
        kg.write("item", "---\ntype: concept\n---\nBody.")
        with pytest.raises(ValueError):
            kg.remove_type("concept")

    def test_write_auto_registers_type(self, kg):
        kg.write("item", "---\ntype: concept\n---\nBody.")
        assert "concept" in kg.types()

    def test_remove_type_then_readd(self, kg):
        kg.add_type("concept")
        kg.remove_type("concept")
        kg.add_type("concept")
        assert "concept" in kg.types()

    def test_add_type_returns_self(self, kg):
        assert kg.add_type("concept") is kg

    def test_remove_type_returns_self(self, kg):
        kg.add_type("concept")
        assert kg.remove_type("concept") is kg


class TestTypeChangeEdgeCases:
    def test_remove_type_from_node(self, kg):
        kg.write("item", "---\ntype: concept\n---\nBody.")
        assert kg.find_by_type("concept") == ["item"]
        kg.write("item", "No more type.")
        assert kg.find_by_type("concept") == []

    def test_add_type_later(self, kg):
        kg.write("item", "Plain text.")
        assert kg.find_by_type("concept") == []
        kg.write("item", "---\ntype: concept\n---\nNow typed.")
        assert kg.find_by_type("concept") == ["item"]

    def test_switch_between_types(self, kg):
        kg.write("item", "---\ntype: concept\n---\nA")
        kg.write("item", "---\ntype: note\n---\nB")
        kg.write("item", "---\ntype: idea\n---\nC")
        assert kg.find_by_type("concept") == []
        assert kg.find_by_type("note") == []
        assert kg.find_by_type("idea") == ["item"]


class TestRmGraphCleanup:
    def test_rm_cleans_type(self, kg):
        kg.write("item", "---\ntype: concept\n---\nBody.")
        kg.rm("item")
        assert kg.query("SELECT * FROM concept") == []

    def test_rm_cleans_links(self, kg):
        kg.write("source", "Links to [[target]].")
        kg.touch("target", "exists")
        kg.rm("source")
        rows = kg.query("SELECT * FROM _links WHERE source_name = 'source'")
        assert rows == []


class TestConcurrentOps:
    def test_rapid_writes_same_node(self, kg):
        for i in range(20):
            kg.write("file", f"---\ntype: t{i % 3}\n---\nVersion {i}")
        assert kg.exists("file")
        body = kg.body("file")
        assert "Version 19" in body

    def test_rapid_create_delete(self, kg):
        for i in range(20):
            kg.touch(f"file-{i}", f"data-{i}")
        for i in range(20):
            kg.rm(f"file-{i}")
        for i in range(20):
            assert not kg.exists(f"file-{i}")


class TestReconstructRoundtrip:
    def test_simple_roundtrip(self, kg):
        original = "---\ntype: concept\ntitle: Test\n---\nBody text."
        kg.write("doc", original)
        result = kg.cat("doc")
        assert "type: concept" in result
        assert "title: Test" in result
        assert "Body text." in result

    def test_list_roundtrip(self, kg):
        original = "---\ntype: concept\ntags: [a, b, c]\n---\nBody."
        kg.write("doc", original)
        result = kg.cat("doc")
        assert "tags:" in result
        assert "Body." in result
        from grapy.core import parse_frontmatter
        meta, body = parse_frontmatter(result)
        assert meta["tags"] == ["a", "b", "c"]
