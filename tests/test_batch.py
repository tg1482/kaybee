"""Tests for batch write context manager."""

import pytest

from kaybee.core import KnowledgeGraph


class TestBatchBasic:
    def test_multiple_writes_persist(self):
        kg = KnowledgeGraph()
        with kg.batch() as b:
            b.write("alpha", "Alpha content.")
            b.write("beta", "Beta content.")
        assert kg.exists("alpha")
        assert kg.exists("beta")
        assert "Alpha content." in kg.cat("alpha")
        assert "Beta content." in kg.cat("beta")

    def test_empty_batch_is_noop(self):
        kg = KnowledgeGraph()
        with kg.batch() as b:
            pass
        assert kg.ls("*") == []

    def test_single_write_in_batch(self):
        kg = KnowledgeGraph()
        with kg.batch() as b:
            b.write("only", "content")
        assert kg.exists("only")


class TestBatchCrossReferences:
    def test_cross_references_resolve(self):
        kg = KnowledgeGraph()
        with kg.batch() as b:
            b.write("a", "Links to [[b]].")
            b.write("b", "Links to [[a]].")
        # Both links should resolve since both nodes exist after batch
        links_a = kg.links("a")
        links_b = kg.links("b")
        assert any(resolved == "b" for _, resolved in links_a)
        assert any(resolved == "a" for _, resolved in links_b)

    def test_forward_reference_in_batch(self):
        kg = KnowledgeGraph()
        with kg.batch() as b:
            b.write("source", "See [[target]].")
            b.write("target", "I exist.")
        links = kg.links("source")
        assert any(resolved == "target" for _, resolved in links)


class TestBatchAtomicity:
    def test_exception_rolls_back(self):
        kg = KnowledgeGraph()
        try:
            with kg.batch() as b:
                b.write("good", "content")
                raise ValueError("something went wrong")
        except ValueError:
            pass
        assert not kg.exists("good")

    def test_validation_failure_prevents_all_writes(self):
        from kaybee.constraints import Validator, ValidationError, requires_field
        kg = KnowledgeGraph()
        v = Validator()
        v.add(requires_field("concept", "description"))
        kg.set_validator(v)
        with pytest.raises(ValidationError):
            with kg.batch() as b:
                b.write("good", "---\ntype: concept\ndescription: ok\n---\nBody.")
                b.write("bad", "---\ntype: concept\n---\nNo description.")
        # Neither should be persisted since validation failed eagerly
        assert not kg.exists("good")
        assert not kg.exists("bad")


class TestBatchDuplicates:
    def test_last_write_wins(self):
        kg = KnowledgeGraph()
        with kg.batch() as b:
            b.write("node", "first version")
            b.write("node", "second version")
        assert "second version" in kg.cat("node")

    def test_duplicate_written_once(self):
        kg = KnowledgeGraph(changelog=True)
        with kg.batch() as b:
            b.write("node", "first")
            b.write("node", "second")
        entries = kg.changelog()
        write_ops = [e for e in entries if e[3] == "node" and e[2] == "node.write"]
        assert len(write_ops) == 1


class TestBatchChangelog:
    def test_changelog_entries_generated(self):
        kg = KnowledgeGraph(changelog=True)
        with kg.batch() as b:
            b.write("a", "content a")
            b.write("b", "content b")
        entries = kg.changelog()
        names = [e[3] for e in entries]
        assert "a" in names
        assert "b" in names

    def test_type_change_in_batch(self):
        kg = KnowledgeGraph(changelog=True)
        kg.write("x", "---\ntype: concept\n---\nOriginal.")
        with kg.batch() as b:
            b.write("x", "---\ntype: person\n---\nChanged.")
        entries = kg.changelog()
        ops = [e[2] for e in entries]
        assert "node.type_change" in ops


class TestBatchTypedNodes:
    def test_typed_nodes_in_batch(self):
        kg = KnowledgeGraph()
        with kg.batch() as b:
            b.write("item", "---\ntype: concept\ndescription: test\n---\nBody.")
            b.write("person", "---\ntype: person\nrole: dev\n---\nBio.")
        assert kg.find_by_type("concept") == ["item"]
        assert kg.find_by_type("person") == ["person"]
        assert "concept" in kg.types()
        assert "person" in kg.types()
