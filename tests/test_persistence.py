"""Tests for KnowledgeGraph persistence (on-disk SQLite)."""

import pytest

from kaybee.core import KnowledgeGraph


class TestPersistence:
    @pytest.fixture(params=["multi", "single"])
    def mode(self, request):
        return request.param

    def test_basic_roundtrip(self, tmp_path, mode):
        db = str(tmp_path / "test.db")
        kg = KnowledgeGraph(db, mode=mode)
        kg.write("note", "---\ntype: note\n---\nPersisted.")

        kg2 = KnowledgeGraph(db, mode=mode)
        assert kg2.exists("note")
        assert kg2.frontmatter("note") == {"type": "note"}
        assert kg2.body("note") == "Persisted."

    def test_links_persist(self, tmp_path, mode):
        db = str(tmp_path / "test.db")
        kg = KnowledgeGraph(db, mode=mode)
        kg.touch("target", "exists")
        kg.write("source", "Links to [[target]].")

        kg2 = KnowledgeGraph(db, mode=mode)
        assert kg2.wikilinks("source") == ["target"]
        bl = kg2.backlinks("target")
        assert "source" in bl

    def test_type_tables_persist(self, tmp_path, mode):
        db = str(tmp_path / "test.db")
        kg = KnowledgeGraph(db, mode=mode)
        kg.write("item", "---\ntype: concept\ndescription: test\n---\nBody.")

        kg2 = KnowledgeGraph(db, mode=mode)
        t = kg2.data_table("concept")
        rows = kg2.query(f"SELECT name, description FROM {t} WHERE name = 'item'")
        assert rows == [("item", "test")]

    def test_types_persist(self, tmp_path, mode):
        db = str(tmp_path / "test.db")
        kg = KnowledgeGraph(db, mode=mode)
        kg.add_type("concept")
        kg.add_type("person")

        kg2 = KnowledgeGraph(db, mode=mode)
        assert kg2.types() == ["concept", "person"]

    def test_rm_persists(self, tmp_path, mode):
        db = str(tmp_path / "test.db")
        kg = KnowledgeGraph(db, mode=mode)
        kg.touch("file", "data")
        kg.rm("file")

        kg2 = KnowledgeGraph(db, mode=mode)
        assert not kg2.exists("file")

    def test_graph_persists(self, tmp_path, mode):
        db = str(tmp_path / "test.db")
        kg = KnowledgeGraph(db, mode=mode)
        kg.write("a", "Links to [[b]].")
        kg.write("b", "Links to [[a]].")

        kg2 = KnowledgeGraph(db, mode=mode)
        g = kg2.graph()
        assert "a" in g
        assert "b" in g

    def test_schema_persists(self, tmp_path, mode):
        db = str(tmp_path / "test.db")
        kg = KnowledgeGraph(db, mode=mode)
        kg.write("a", "---\ntype: concept\ndescription: test\n---\nA")

        kg2 = KnowledgeGraph(db, mode=mode)
        s = kg2.schema()
        assert "concept" in s
        assert "description" in s["concept"]
