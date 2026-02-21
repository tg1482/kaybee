"""Tests for info(), query(), and tags() methods."""

import pytest

from kaybee.core import KnowledgeGraph


class TestInfo:
    def test_basic_info(self, kg):
        kg.touch("file", "hello")
        info = kg.info("file")
        assert info["name"] == "file"
        assert info["type"] is None
        assert info["content_length"] == 5
        assert info["has_content"] is True

    def test_typed_node_info(self, kg):
        kg.write("item", "---\ntype: concept\ntags: [a, b]\n---\nBody.")
        info = kg.info("item")
        assert info["type"] == "concept"
        assert info["tags"] == ["a", "b"]

    def test_untyped_node_info(self, kg):
        kg.touch("plain", "text")
        info = kg.info("plain")
        assert info["type"] is None
        assert info["tags"] == []

    def test_nonexistent_raises(self, kg):
        with pytest.raises(KeyError):
            kg.info("nope")

    def test_empty_file_info(self, kg):
        kg.touch("empty")
        info = kg.info("empty")
        assert info["content_length"] == 0
        assert info["has_content"] is False

    def test_info_meta(self, kg):
        kg.write("item", "---\ntype: concept\ndescription: test\n---\nBody.")
        info = kg.info("item")
        assert info["meta"]["type"] == "concept"
        assert info["meta"]["description"] == "test"


class TestQuery:
    def test_basic(self, kg):
        kg.touch("file", "hello")
        t = "_data"
        rows = kg.query(f"SELECT name, content FROM {t} WHERE name = 'file'")
        assert rows == [("file", "hello")]

    def test_with_params(self, kg):
        kg.touch("a", "x")
        kg.touch("b", "y")
        t = "_data"
        rows = kg.query(f"SELECT name FROM {t} WHERE content = ?", ("x",))
        assert rows == [("a",)]

    def test_empty_result(self, kg):
        rows = kg.query("SELECT name FROM nodes WHERE name = 'nope'")
        assert rows == []

    def test_count(self, kg):
        kg.touch("a")
        kg.touch("b")
        rows = kg.query("SELECT COUNT(*) FROM nodes")
        assert rows[0][0] == 2

    def test_join(self, populated_kg):
        rows = populated_kg.query(
            "SELECT l.source_name, l.target_resolved FROM _links l "
            "JOIN nodes n ON n.name = l.source_name "
            "WHERE n.type = 'person'"
        )
        assert len(rows) >= 1
        assert rows[0][0] == "turing"


class TestTags:
    def test_tags_for_node(self, kg):
        kg.write("item", "---\ntype: concept\ntags: [graph, cognition]\n---\nBody.")
        result = kg.tags("item")
        assert result == ["graph", "cognition"]

    def test_tags_for_untagged_node(self, kg):
        kg.touch("plain", "no tags")
        assert kg.tags("plain") == []

    def test_tags_map(self, kg):
        kg.write("a", "---\ntype: concept\ntags: [graph, cognition]\n---\nA")
        kg.write("b", "---\ntype: concept\ntags: [graph, nlp]\n---\nB")
        tag_map = kg.tags()
        assert "graph" in tag_map
        assert "a" in tag_map["graph"]
        assert "b" in tag_map["graph"]
        assert "cognition" in tag_map
        assert "nlp" in tag_map

    def test_tags_empty_graph(self, kg):
        assert kg.tags() == {}

    def test_tags_nonexistent_raises(self, kg):
        with pytest.raises(KeyError):
            kg.tags("nope")
