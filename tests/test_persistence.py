"""Tests for KnowledgeGraph persistence (on-disk SQLite)."""

import pytest

from grapy.core import KnowledgeGraph


class TestPersistence:
    def test_basic_roundtrip(self, tmp_path):
        db = str(tmp_path / "test.db")
        kg = KnowledgeGraph(db)
        kg.write("note", "---\ntype: note\n---\nPersisted.")

        kg2 = KnowledgeGraph(db)
        assert kg2.exists("note")
        assert kg2.frontmatter("note") == {"type": "note"}
        assert kg2.body("note") == "Persisted."

    def test_links_persist(self, tmp_path):
        db = str(tmp_path / "test.db")
        kg = KnowledgeGraph(db)
        kg.touch("target", "exists")
        kg.write("source", "Links to [[target]].")

        kg2 = KnowledgeGraph(db)
        assert kg2.wikilinks("source") == ["target"]
        bl = kg2.backlinks("target")
        assert "source" in bl

    def test_type_tables_persist(self, tmp_path):
        db = str(tmp_path / "test.db")
        kg = KnowledgeGraph(db)
        kg.write("item", "---\ntype: concept\ndescription: test\n---\nBody.")

        kg2 = KnowledgeGraph(db)
        rows = kg2.query("SELECT name, description FROM concept")
        assert rows == [("item", "test")]

    def test_types_persist(self, tmp_path):
        db = str(tmp_path / "test.db")
        kg = KnowledgeGraph(db)
        kg.add_type("concept")
        kg.add_type("person")

        kg2 = KnowledgeGraph(db)
        assert kg2.types() == ["concept", "person"]

    def test_rm_persists(self, tmp_path):
        db = str(tmp_path / "test.db")
        kg = KnowledgeGraph(db)
        kg.touch("file", "data")
        kg.rm("file")

        kg2 = KnowledgeGraph(db)
        assert not kg2.exists("file")

    def test_graph_persists(self, tmp_path):
        db = str(tmp_path / "test.db")
        kg = KnowledgeGraph(db)
        kg.write("a", "Links to [[b]].")
        kg.write("b", "Links to [[a]].")

        kg2 = KnowledgeGraph(db)
        g = kg2.graph()
        assert "a" in g
        assert "b" in g

    def test_schema_persists(self, tmp_path):
        db = str(tmp_path / "test.db")
        kg = KnowledgeGraph(db)
        kg.write("a", "---\ntype: concept\ndescription: test\n---\nA")

        kg2 = KnowledgeGraph(db)
        s = kg2.schema()
        assert "concept" in s
        assert "description" in s["concept"]
