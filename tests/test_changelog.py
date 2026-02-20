"""Tests for the changelog feature in KnowledgeGraph."""

import json
import pytest

from kaybee.core import KnowledgeGraph


class TestChangelogDisabled:
    @pytest.fixture
    def kg_no_changelog(self):
        """KnowledgeGraph with changelog explicitly disabled."""
        return KnowledgeGraph(changelog=False)

    def test_disabled_returns_empty(self, kg_no_changelog):
        kg_no_changelog.touch("a", "hello")
        assert kg_no_changelog.changelog() == []

    def test_truncate_noop_when_disabled(self, kg_no_changelog):
        assert kg_no_changelog.changelog_truncate(999) == 0


class TestChangelogEnabled:
    def test_write_logged(self, kg):
        kg.write("note", "hello world")
        entries = kg.changelog()
        assert len(entries) == 1
        seq, ts, op, name, data = entries[0]
        assert op == "node.write"
        assert name == "note"
        parsed = json.loads(data)
        assert parsed["type"] == "kaybee"
        assert parsed["content"] == "hello world"

    def test_touch_empty_logged(self, kg):
        kg.touch("empty")
        entries = kg.changelog()
        assert len(entries) == 1
        seq, ts, op, name, data = entries[0]
        assert op == "node.write"
        assert name == "empty"
        parsed = json.loads(data)
        assert parsed["content"] == ""

    def test_touch_with_content_logged(self, kg):
        kg.touch("note", "body")
        entries = kg.changelog()
        assert len(entries) == 1
        assert entries[0][2] == "node.write"

    def test_rm_logged(self, kg):
        kg.touch("x")
        kg.rm("x")
        entries = kg.changelog()
        assert len(entries) == 2
        rm_entry = entries[1]
        assert rm_entry[2] == "node.rm"
        assert rm_entry[3] == "x"
        parsed = json.loads(rm_entry[4])
        assert parsed["type"] == "kaybee"

    def test_mv_logged(self, kg):
        kg.touch("old", "content")
        kg.mv("old", "new")
        entries = kg.changelog()
        assert len(entries) == 2
        mv_entry = entries[1]
        assert mv_entry[2] == "node.mv"
        assert mv_entry[3] == "new"
        parsed = json.loads(mv_entry[4])
        assert parsed["old_name"] == "old"

    def test_cp_logged(self, kg):
        kg.touch("src", "data")
        kg.cp("src", "dst")
        entries = kg.changelog()
        assert len(entries) == 2
        cp_entry = entries[1]
        assert cp_entry[2] == "node.cp"
        assert cp_entry[3] == "dst"
        parsed = json.loads(cp_entry[4])
        assert parsed["source"] == "src"

    def test_add_type_logged(self, kg):
        kg.add_type("concept")
        entries = kg.changelog()
        assert len(entries) == 1
        assert entries[0][2] == "type.add"
        assert entries[0][3] == "concept"

    def test_remove_type_logged(self, kg):
        kg.add_type("concept")
        kg.remove_type("concept")
        entries = kg.changelog()
        assert len(entries) == 2
        assert entries[1][2] == "type.rm"
        assert entries[1][3] == "concept"


class TestChangelogQuery:
    def test_since_seq(self, kg):
        kg.touch("a")
        kg.touch("b")
        kg.touch("c")
        all_entries = kg.changelog()
        assert len(all_entries) == 3
        # Get entries after the first
        first_seq = all_entries[0][0]
        rest = kg.changelog(since_seq=first_seq)
        assert len(rest) == 2

    def test_limit(self, kg):
        for i in range(10):
            kg.touch(f"n{i}")
        entries = kg.changelog(limit=3)
        assert len(entries) == 3

    def test_seq_monotonic(self, kg):
        kg.touch("a")
        kg.touch("b")
        kg.touch("c")
        entries = kg.changelog()
        seqs = [e[0] for e in entries]
        assert seqs == sorted(seqs)
        assert len(set(seqs)) == len(seqs)  # all unique

    def test_timestamp_present(self, kg):
        kg.touch("a")
        entries = kg.changelog()
        ts = entries[0][1]
        assert isinstance(ts, float)
        assert ts > 0


class TestChangelogTruncate:
    def test_truncate_removes_old(self, kg):
        kg.touch("a")
        kg.touch("b")
        kg.touch("c")
        entries = kg.changelog()
        mid_seq = entries[1][0]
        deleted = kg.changelog_truncate(before_seq=mid_seq)
        assert deleted == 1  # only seq < mid_seq
        remaining = kg.changelog()
        assert len(remaining) == 2
        assert remaining[0][0] == mid_seq

    def test_truncate_all(self, kg):
        kg.touch("a")
        kg.touch("b")
        entries = kg.changelog()
        last_seq = entries[-1][0]
        deleted = kg.changelog_truncate(before_seq=last_seq + 1)
        assert deleted == 2
        assert kg.changelog() == []

    def test_truncate_none(self, kg):
        kg.touch("a")
        deleted = kg.changelog_truncate(before_seq=0)
        assert deleted == 0
        assert len(kg.changelog()) == 1


class TestChangelogTypedNodes:
    def test_typed_write_logged(self, kg):
        kg.add_type("concept")
        kg.write("idea", "---\ntype: concept\ntags: [demo]\n---\nBody text")
        entries = kg.changelog()
        # add_type + write = 2 entries
        assert len(entries) == 2
        write_entry = entries[1]
        assert write_entry[2] == "node.write"
        parsed = json.loads(write_entry[4])
        assert parsed["type"] == "concept"
