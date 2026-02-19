"""Tests for frontmatter integration: type tables, metadata, body extraction, cat reconstruction."""

import pytest

from grapy.core import KnowledgeGraph


class TestFrontmatterWrite:
    def test_write_with_frontmatter(self, kg):
        kg.write(
            "item",
            "---\ntype: concept\ndescription: How activation propagates\ntags: [graph, cognition]\n---\nBody text.",
        )
        meta = kg.frontmatter("item")
        assert meta["type"] == "concept"
        assert meta["description"] == "How activation propagates"
        assert meta["tags"] == ["graph", "cognition"]

    def test_body_strips_frontmatter(self, kg):
        kg.write("note", "---\ntype: note\n---\nJust the body.")
        assert kg.body("note") == "Just the body."

    def test_cat_reconstructs_full(self, kg):
        kg.write("doc", "---\ntype: concept\ntitle: Hello\n---\nBody here.")
        result = kg.cat("doc")
        assert "type: concept" in result
        assert "title: Hello" in result
        assert "Body here." in result

    def test_write_no_frontmatter(self, kg):
        kg.write("plain", "Just plain text.")
        assert kg.frontmatter("plain") == {}
        assert kg.body("plain") == "Just plain text."

    def test_frontmatter_nonexistent_raises(self, kg):
        with pytest.raises(KeyError):
            kg.frontmatter("nope")

    def test_body_nonexistent_raises(self, kg):
        with pytest.raises(KeyError):
            kg.body("nope")

    def test_empty_file_meta_and_body(self, kg):
        kg.touch("empty")
        assert kg.frontmatter("empty") == {}
        assert kg.body("empty") == ""


class TestTypeTables:
    def test_type_table_created(self, kg):
        kg.write("item", "---\ntype: concept\ndescription: test\n---\nBody.")
        rows = kg.query("SELECT name, description FROM concept")
        assert len(rows) == 1
        assert rows[0] == ("item", "test")

    def test_type_table_columns_extended(self, kg):
        kg.write("a", "---\ntype: concept\ndescription: first\n---\nA.")
        kg.write("b", "---\ntype: concept\npriority: high\n---\nB.")
        rows = kg.query("SELECT name, description, priority FROM concept ORDER BY name")
        assert len(rows) == 2

    def test_multiple_types(self, kg):
        kg.write("a", "---\ntype: concept\n---\nA")
        kg.write("b", "---\ntype: note\n---\nB")
        assert len(kg.query("SELECT * FROM concept")) == 1
        assert len(kg.query("SELECT * FROM note")) == 1

    def test_overwrite_changes_type(self, kg):
        kg.write("item", "---\ntype: concept\n---\nOld.")
        assert kg.find_by_type("concept") == ["item"]
        kg.write("item", "---\ntype: note\n---\nNew.")
        assert kg.find_by_type("concept") == []
        assert kg.find_by_type("note") == ["item"]

    def test_overwrite_same_type(self, kg):
        kg.write("item", "---\ntype: concept\ndescription: v1\n---\nV1.")
        kg.write("item", "---\ntype: concept\ndescription: v2\n---\nV2.")
        rows = kg.query("SELECT description FROM concept WHERE name = 'item'")
        assert rows[0][0] == "v2"

    def test_list_value_in_type_table(self, kg):
        kg.write("item", "---\ntype: concept\ntags: [a, b]\n---\nBody.")
        rows = kg.query("SELECT tags FROM concept WHERE name = 'item'")
        assert "a" in rows[0][0]
        assert "b" in rows[0][0]


class TestFindByType:
    def test_basic(self, kg):
        kg.write("a", "---\ntype: concept\n---\nA")
        kg.write("b", "---\ntype: note\n---\nB")
        kg.write("c", "---\ntype: concept\n---\nC")
        result = kg.find_by_type("concept")
        assert "a" in result
        assert "c" in result
        assert "b" not in result

    def test_no_matches(self, kg):
        assert kg.find_by_type("nonexistent") == []

    def test_sorted(self, kg):
        kg.write("z", "---\ntype: t\n---\nZ")
        kg.write("a", "---\ntype: t\n---\nA")
        result = kg.find_by_type("t")
        assert result == ["a", "z"]


class TestSchema:
    def test_basic(self, kg):
        kg.write("a", "---\ntype: concept\ndescription: test\ntags: [x]\n---\nA")
        kg.write("b", "---\ntype: note\npriority: high\n---\nB")
        s = kg.schema()
        assert "concept" in s
        assert "note" in s
        assert "description" in s["concept"]
        assert "tags" in s["concept"]
        assert "priority" in s["note"]

    def test_empty_schema(self, kg):
        assert kg.schema() == {}

    def test_type_with_no_extra_fields(self, kg):
        kg.write("a", "---\ntype: minimal\n---\nBody.")
        s = kg.schema()
        assert "minimal" in s
        assert isinstance(s["minimal"], list)
