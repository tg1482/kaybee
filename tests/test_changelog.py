"""Tests for the changelog feature in KnowledgeGraph."""

import json
import pytest

from kaybee.core import KnowledgeGraph


@pytest.fixture
def ckg():
    """KnowledgeGraph with changelog enabled."""
    return KnowledgeGraph(changelog=True)


class TestChangelogDisabled:
    def test_disabled_by_default(self, kg):
        kg.touch("a", "hello")
        assert kg.changelog() == []

    def test_truncate_noop_when_disabled(self, kg):
        assert kg.changelog_truncate(999) == 0


class TestChangelogEnabled:
    def test_write_logged(self, ckg):
        ckg.write("note", "hello world")
        entries = ckg.changelog()
        assert len(entries) == 1
        seq, ts, op, name, data = entries[0]
        assert op == "node.write"
        assert name == "note"
        parsed = json.loads(data)
        assert parsed["type"] == "kaybee"
        assert parsed["content"] == "hello world"

    def test_touch_empty_logged(self, ckg):
        ckg.touch("empty")
        entries = ckg.changelog()
        assert len(entries) == 1
        seq, ts, op, name, data = entries[0]
        assert op == "node.write"
        assert name == "empty"
        parsed = json.loads(data)
        assert parsed["content"] == ""

    def test_touch_with_content_logged(self, ckg):
        ckg.touch("note", "body")
        entries = ckg.changelog()
        assert len(entries) == 1
        assert entries[0][2] == "node.write"

    def test_rm_logged(self, ckg):
        ckg.touch("x")
        ckg.rm("x")
        entries = ckg.changelog()
        assert len(entries) == 2
        rm_entry = entries[1]
        assert rm_entry[2] == "node.rm"
        assert rm_entry[3] == "x"
        parsed = json.loads(rm_entry[4])
        assert parsed["type"] == "kaybee"

    def test_mv_logged(self, ckg):
        ckg.touch("old", "content")
        ckg.mv("old", "new")
        entries = ckg.changelog()
        assert len(entries) == 2
        mv_entry = entries[1]
        assert mv_entry[2] == "node.mv"
        assert mv_entry[3] == "new"
        parsed = json.loads(mv_entry[4])
        assert parsed["old_name"] == "old"

    def test_cp_logged(self, ckg):
        ckg.touch("src", "data")
        ckg.cp("src", "dst")
        entries = ckg.changelog()
        assert len(entries) == 2
        cp_entry = entries[1]
        assert cp_entry[2] == "node.cp"
        assert cp_entry[3] == "dst"
        parsed = json.loads(cp_entry[4])
        assert parsed["source"] == "src"

    def test_add_type_logged(self, ckg):
        ckg.add_type("concept")
        entries = ckg.changelog()
        assert len(entries) == 1
        assert entries[0][2] == "type.add"
        assert entries[0][3] == "concept"

    def test_remove_type_logged(self, ckg):
        ckg.add_type("concept")
        ckg.remove_type("concept")
        entries = ckg.changelog()
        assert len(entries) == 2
        assert entries[1][2] == "type.rm"
        assert entries[1][3] == "concept"


class TestChangelogQuery:
    def test_since_seq(self, ckg):
        ckg.touch("a")
        ckg.touch("b")
        ckg.touch("c")
        all_entries = ckg.changelog()
        assert len(all_entries) == 3
        # Get entries after the first
        first_seq = all_entries[0][0]
        rest = ckg.changelog(since_seq=first_seq)
        assert len(rest) == 2

    def test_limit(self, ckg):
        for i in range(10):
            ckg.touch(f"n{i}")
        entries = ckg.changelog(limit=3)
        assert len(entries) == 3

    def test_seq_monotonic(self, ckg):
        ckg.touch("a")
        ckg.touch("b")
        ckg.touch("c")
        entries = ckg.changelog()
        seqs = [e[0] for e in entries]
        assert seqs == sorted(seqs)
        assert len(set(seqs)) == len(seqs)  # all unique

    def test_timestamp_present(self, ckg):
        ckg.touch("a")
        entries = ckg.changelog()
        ts = entries[0][1]
        assert isinstance(ts, float)
        assert ts > 0


class TestChangelogTruncate:
    def test_truncate_removes_old(self, ckg):
        ckg.touch("a")
        ckg.touch("b")
        ckg.touch("c")
        entries = ckg.changelog()
        mid_seq = entries[1][0]
        deleted = ckg.changelog_truncate(before_seq=mid_seq)
        assert deleted == 1  # only seq < mid_seq
        remaining = ckg.changelog()
        assert len(remaining) == 2
        assert remaining[0][0] == mid_seq

    def test_truncate_all(self, ckg):
        ckg.touch("a")
        ckg.touch("b")
        entries = ckg.changelog()
        last_seq = entries[-1][0]
        deleted = ckg.changelog_truncate(before_seq=last_seq + 1)
        assert deleted == 2
        assert ckg.changelog() == []

    def test_truncate_none(self, ckg):
        ckg.touch("a")
        deleted = ckg.changelog_truncate(before_seq=0)
        assert deleted == 0
        assert len(ckg.changelog()) == 1


class TestChangelogTypedNodes:
    def test_typed_write_logged(self, ckg):
        ckg.add_type("concept")
        ckg.write("idea", "---\ntype: concept\ntags: [demo]\n---\nBody text")
        entries = ckg.changelog()
        # add_type + write = 2 entries
        assert len(entries) == 2
        write_entry = entries[1]
        assert write_entry[2] == "node.write"
        parsed = json.loads(write_entry[4])
        assert parsed["type"] == "concept"
