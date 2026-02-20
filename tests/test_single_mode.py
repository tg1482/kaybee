"""Tests specific to single-table storage mode."""

import pytest

from kaybee.core import KnowledgeGraph


class TestConstructor:
    def test_single_mode_creates_data_table(self):
        kg = KnowledgeGraph(mode="single")
        tables = {r[0] for r in kg.query("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "_data" in tables
        assert "_type_fields" in tables
        assert "kaybee" not in tables

    def test_multi_mode_creates_kaybee_table(self):
        kg = KnowledgeGraph(mode="multi")
        tables = {r[0] for r in kg.query("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "kaybee" in tables
        assert "_data" not in tables

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="Invalid mode"):
            KnowledgeGraph(mode="bad")

    def test_default_mode_is_multi(self):
        kg = KnowledgeGraph()
        assert kg._mode == "multi"


class TestModeMismatch:
    def test_reopen_with_wrong_mode_raises(self, tmp_path):
        db = str(tmp_path / "test.db")
        kg = KnowledgeGraph(db, mode="single")
        kg.touch("x", "data")
        kg._db.close()

        with pytest.raises(ValueError, match="mode='single'.*mode='multi'"):
            KnowledgeGraph(db, mode="multi")

    def test_reopen_with_same_mode_ok(self, tmp_path):
        db = str(tmp_path / "test.db")
        kg = KnowledgeGraph(db, mode="single")
        kg.touch("x", "data")
        kg._db.close()

        kg2 = KnowledgeGraph(db, mode="single")
        assert kg2.exists("x")
        kg2._db.close()


class TestTypeFieldsTracking:
    def test_type_fields_recorded(self):
        kg = KnowledgeGraph(mode="single")
        kg.write("item", "---\ntype: concept\ndescription: hello\ntags: [a]\n---\nBody")
        rows = kg.query(
            "SELECT field_name FROM _type_fields WHERE type_name = 'concept' ORDER BY field_name"
        )
        field_names = [r[0] for r in rows]
        assert "description" in field_names
        assert "tags" in field_names

    def test_untyped_fields_not_in_type_fields(self):
        kg = KnowledgeGraph(mode="single")
        kg.write("plain", "---\nmood: happy\n---\nBody")
        rows = kg.query("SELECT * FROM _type_fields")
        assert len(rows) == 0

    def test_multiple_types_tracked_separately(self):
        kg = KnowledgeGraph(mode="single")
        kg.write("a", "---\ntype: concept\ndescription: hello\n---\nA")
        kg.write("b", "---\ntype: person\nrole: dev\n---\nB")

        concept_fields = {
            r[0] for r in kg.query(
                "SELECT field_name FROM _type_fields WHERE type_name = 'concept'"
            )
        }
        person_fields = {
            r[0] for r in kg.query(
                "SELECT field_name FROM _type_fields WHERE type_name = 'person'"
            )
        }
        assert "description" in concept_fields
        assert "role" in person_fields
        assert "role" not in concept_fields
        assert "description" not in person_fields


class TestCrossTypeColumns:
    def test_nulls_for_irrelevant_fields(self):
        kg = KnowledgeGraph(mode="single")
        kg.write("a", "---\ntype: concept\ndescription: hello\n---\nA")
        kg.write("b", "---\ntype: person\nrole: dev\n---\nB")

        # _data table has both description and role columns
        row_a = kg.query("SELECT description, role FROM _data WHERE name = 'a'")
        assert row_a[0][0] == "hello"
        assert row_a[0][1] is None  # role is NULL for concept

        row_b = kg.query("SELECT description, role FROM _data WHERE name = 'b'")
        assert row_b[0][0] is None  # description is NULL for person
        assert row_b[0][1] == "dev"

    def test_read_node_data_filters_by_type(self):
        kg = KnowledgeGraph(mode="single")
        kg.write("a", "---\ntype: concept\ndescription: hello\n---\nA")
        kg.write("b", "---\ntype: person\nrole: dev\n---\nB")

        _, meta_a = kg._read_node_data("a")
        assert "description" in meta_a
        assert "role" not in meta_a

        _, meta_b = kg._read_node_data("b")
        assert "role" in meta_b
        assert "description" not in meta_b


class TestSchema:
    def test_schema_from_type_fields(self):
        kg = KnowledgeGraph(mode="single")
        kg.write("a", "---\ntype: concept\ndescription: hello\ntags: [x]\n---\nA")
        kg.write("b", "---\ntype: person\nrole: dev\n---\nB")

        s = kg.schema()
        assert "concept" in s
        assert "person" in s
        assert "description" in s["concept"]
        assert "tags" in s["concept"]
        assert "role" in s["person"]


class TestPersistence:
    def test_single_mode_roundtrip(self, tmp_path):
        db = str(tmp_path / "test.db")
        kg = KnowledgeGraph(db, mode="single")
        kg.write("a", "---\ntype: concept\ndescription: hello\ntags: [x, y]\n---\nBody A")
        kg.touch("b", "plain text")
        kg._db.close()

        kg2 = KnowledgeGraph(db, mode="single")
        assert kg2.exists("a")
        assert kg2.exists("b")
        assert kg2.body("a") == "Body A"
        assert kg2.cat("b") == "plain text"
        assert kg2.frontmatter("a")["description"] == "hello"
        assert kg2.frontmatter("a")["tags"] == ["x", "y"]
        assert kg2.schema() == {"concept": ["description", "tags"]}
        kg2._db.close()


class TestReservedNames:
    def test_data_reserved(self):
        with pytest.raises(ValueError, match="Reserved type name"):
            kg = KnowledgeGraph(mode="single")
            kg.write("item", "---\ntype: _data\n---\nbody")

    def test_type_fields_reserved(self):
        with pytest.raises(ValueError, match="Reserved type name"):
            kg = KnowledgeGraph(mode="single")
            kg.write("item", "---\ntype: _type_fields\n---\nbody")
