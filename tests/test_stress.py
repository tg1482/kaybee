"""Stress tests for the thin-index + uniform type tables architecture.

Exercises correctness and performance at scale: 100k+ nodes, bulk writes,
type switching, cross-type queries, grep across union tables, tag scanning,
and validator gatekeeper under load.
"""

import time
import sqlite3

import pytest

from kaybee.core import KnowledgeGraph
from kaybee.constraints import Validator, ValidationError, requires_field, requires_tag, freeze_schema

pytestmark = pytest.mark.stress


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def timed(fn):
    """Run fn, return (result, elapsed_seconds)."""
    t0 = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - t0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def kg():
    return KnowledgeGraph()


@pytest.fixture
def file_kg(tmp_path):
    """File-backed graph for persistence stress."""
    return KnowledgeGraph(str(tmp_path / "stress.db"))


# ═══════════════════════════════════════════════════════════════════════════
# 1. Bulk write throughput
# ═══════════════════════════════════════════════════════════════════════════


class TestBulkWriteThroughput:
    """Measure raw write speed for untyped and typed nodes."""

    def test_100k_untyped_touch(self, kg):
        """Touch 100k plain nodes."""
        _, elapsed = timed(lambda: [kg.touch(f"node-{i}", f"content-{i}") for i in range(100_000)])
        assert kg.query("SELECT COUNT(*) FROM nodes")[0][0] == 100_000
        assert kg.query("SELECT COUNT(*) FROM kaybee")[0][0] == 100_000
        print(f"\n  100k untyped touch: {elapsed:.2f}s ({100_000/elapsed:.0f} ops/s)")

    def test_100k_typed_write(self, kg):
        """Write 100k typed nodes across 10 types."""
        def do():
            for i in range(100_000):
                t = i % 10
                kg.write(f"item-{i}", f"---\ntype: type-{t}\nfield: val-{i}\n---\nbody-{i}")
        _, elapsed = timed(do)
        assert kg.query("SELECT COUNT(*) FROM nodes")[0][0] == 100_000
        # Each type table should have 10k nodes
        for t in range(10):
            safe = f"type_{t}"
            count = kg.query(f"SELECT COUNT(*) FROM {safe}")[0][0]
            assert count == 10_000
        print(f"\n  100k typed write: {elapsed:.2f}s ({100_000/elapsed:.0f} ops/s)")

    def test_50k_mixed_untyped_and_typed(self, kg):
        """Mix of untyped and typed writes."""
        def do():
            for i in range(50_000):
                if i % 3 == 0:
                    kg.touch(f"plain-{i}", f"content-{i}")
                else:
                    t = i % 5
                    kg.write(f"typed-{i}", f"---\ntype: cat-{t}\nidx: {i}\n---\nbody")
        _, elapsed = timed(do)
        total = kg.query("SELECT COUNT(*) FROM nodes")[0][0]
        assert total == 50_000
        print(f"\n  50k mixed write: {elapsed:.2f}s ({50_000/elapsed:.0f} ops/s)")


# ═══════════════════════════════════════════════════════════════════════════
# 2. Thin index correctness at scale
# ═══════════════════════════════════════════════════════════════════════════


class TestThinIndexCorrectness:
    """Verify the thin index + type table invariant holds at scale."""

    def test_nodes_table_has_no_content_column(self, kg):
        """The nodes table should only have name and type."""
        kg.touch("test", "data")
        cols = {row[1] for row in kg.query("PRAGMA table_info(nodes)")}
        assert cols == {"name", "type"}
        assert "content" not in cols
        assert "meta" not in cols

    def test_every_node_has_type_table_row(self, kg):
        """Every node in the index must have a corresponding type table row."""
        for i in range(1000):
            if i % 2 == 0:
                kg.touch(f"plain-{i}", f"content-{i}")
            else:
                kg.write(f"typed-{i}", f"---\ntype: concept\nfield: v{i}\n---\nbody-{i}")

        # Check all nodes have data
        index_rows = kg.query("SELECT name, type FROM nodes ORDER BY name")
        assert len(index_rows) == 1000
        for name, type_name in index_rows:
            content, meta = kg._read_node_data(name)
            assert isinstance(content, str)
            assert isinstance(meta, dict)

    def test_kaybee_not_in_types(self, kg):
        """kaybee should never appear in _types or ls()."""
        kg.touch("a", "untyped")
        kg.write("b", "---\ntype: concept\n---\nbody")
        assert "kaybee" not in kg.types()
        assert "kaybee" not in kg.ls()

    def test_untyped_display_type_is_none(self, kg):
        """info() for untyped nodes shows type=None."""
        kg.touch("plain", "text")
        info = kg.info("plain")
        assert info["type"] is None

    def test_type_table_data_matches_read(self, kg):
        """Direct SQL on type table should match _read_node_data."""
        kg.write("x", "---\ntype: concept\ndescription: hello\ntags: [a, b]\n---\nBody text")
        content, meta = kg._read_node_data("x")
        assert content == "Body text"
        assert meta["type"] == "concept"
        assert meta["description"] == "hello"
        assert meta["tags"] == ["a", "b"]

        # Direct SQL
        row = kg.query("SELECT name, content, description, tags FROM concept WHERE name = 'x'")
        assert row[0][0] == "x"
        assert row[0][1] == "Body text"
        assert row[0][2] == "hello"

    def test_no_json_blobs_anywhere(self, kg):
        """No meta column, no JSON blobs in the nodes table."""
        kg.write("x", "---\ntype: concept\ntags: [a, b]\n---\nbody")
        kg.touch("y", "plain")

        # nodes table should not have meta column
        cols = {row[1] for row in kg.query("PRAGMA table_info(nodes)")}
        assert "meta" not in cols

        # kaybee table should not have meta column
        cols = {row[1] for row in kg.query("PRAGMA table_info(kaybee)")}
        assert "meta" not in cols


# ═══════════════════════════════════════════════════════════════════════════
# 3. Read path performance
# ═══════════════════════════════════════════════════════════════════════════


class TestReadPerformance:
    """Read operations at scale."""

    def _populate(self, kg, n=10_000):
        for i in range(n):
            if i % 3 == 0:
                kg.touch(f"plain-{i}", f"content-{i}")
            else:
                t = i % 5
                kg.write(f"typed-{i}", f"---\ntype: cat-{t}\ntags: [tag-{i % 20}]\nfield: v{i}\n---\nbody-{i}")

    def test_cat_10k(self, kg):
        """cat() 10k nodes."""
        self._populate(kg, 10_000)
        _, elapsed = timed(lambda: [kg.cat(f"plain-{i}") for i in range(0, 10_000, 3)])
        count = 10_000 // 3 + 1
        print(f"\n  cat {count} nodes: {elapsed:.2f}s ({count/elapsed:.0f} ops/s)")

    def test_frontmatter_10k(self, kg):
        """frontmatter() for 10k typed nodes."""
        self._populate(kg, 10_000)
        typed_names = [f"typed-{i}" for i in range(1, 10_000, 3)]
        _, elapsed = timed(lambda: [kg.frontmatter(n) for n in typed_names[:5000]])
        print(f"\n  frontmatter 5000 nodes: {elapsed:.2f}s ({5000/elapsed:.0f} ops/s)")

    def test_info_10k(self, kg):
        """info() for 10k nodes."""
        self._populate(kg, 10_000)
        names = [f"plain-{i}" for i in range(0, 3000, 3)]
        _, elapsed = timed(lambda: [kg.info(n) for n in names])
        print(f"\n  info {len(names)} nodes: {elapsed:.2f}s ({len(names)/elapsed:.0f} ops/s)")

    def test_ls_star_100k(self, kg):
        """ls('*') with 100k nodes."""
        for i in range(100_000):
            kg.touch(f"n-{i}", f"c-{i}")
        _, elapsed = timed(lambda: kg.ls("*"))
        result = kg.ls("*")
        assert len(result) == 100_000
        print(f"\n  ls('*') 100k: {elapsed:.2f}s")


# ═══════════════════════════════════════════════════════════════════════════
# 4. Grep performance (UNION across type tables)
# ═══════════════════════════════════════════════════════════════════════════


class TestGrepPerformance:
    def test_grep_across_50k_mixed(self, kg):
        """grep across 50k nodes spanning 10 types + kaybee."""
        for i in range(50_000):
            if i % 4 == 0:
                kg.touch(f"plain-{i}", f"the answer is {42 if i % 100 == 0 else 0}")
            else:
                t = i % 10
                kg.write(f"typed-{i}", f"---\ntype: t-{t}\n---\nthe answer is {42 if i % 100 == 0 else 0}")

        _, elapsed = timed(lambda: kg.grep("42", content=True))
        results = kg.grep("42", content=True)
        assert len(results) >= 500  # every 100th node has 42
        print(f"\n  grep '42' across 50k: {elapsed:.2f}s, {len(results)} matches")

    def test_grep_single_type_10k(self, kg):
        """grep within a single type table (no union)."""
        for i in range(10_000):
            kg.write(f"item-{i}", f"---\ntype: article\n---\nkeyword-{i % 50}")
        _, elapsed = timed(lambda: kg.grep("keyword-7", type="article", content=True))
        results = kg.grep("keyword-7", type="article", content=True)
        assert len(results) == 200  # 10000/50
        print(f"\n  grep single type 10k: {elapsed:.2f}s, {len(results)} matches")

    def test_grep_line_mode_10k(self, kg):
        """grep with line numbers across 10k nodes."""
        for i in range(10_000):
            kg.touch(f"doc-{i}", f"line one\nfind me here\nline three")
        _, elapsed = timed(lambda: kg.grep("find me", content=True, lines=True))
        results = kg.grep("find me", content=True, lines=True)
        assert len(results) == 10_000
        print(f"\n  grep line mode 10k: {elapsed:.2f}s")


# ═══════════════════════════════════════════════════════════════════════════
# 5. Tag scanning performance
# ═══════════════════════════════════════════════════════════════════════════


class TestTagPerformance:
    def test_global_tag_map_50k(self, kg):
        """Build global tag map from 50k tagged nodes across 5 types."""
        for i in range(50_000):
            t = i % 5
            tags = [f"tag-{i % 100}", f"tag-{(i+50) % 100}"]
            tag_str = ", ".join(tags)
            kg.write(f"item-{i}", f"---\ntype: t-{t}\ntags: [{tag_str}]\n---\nbody")

        _, elapsed = timed(lambda: kg.tags())
        tag_map = kg.tags()
        assert len(tag_map) == 100  # 100 distinct tags
        total_entries = sum(len(v) for v in tag_map.values())
        assert total_entries == 100_000  # each node has 2 tags
        print(f"\n  tag map 50k nodes: {elapsed:.2f}s, {len(tag_map)} tags, {total_entries} entries")


# ═══════════════════════════════════════════════════════════════════════════
# 6. Type switching at scale
# ═══════════════════════════════════════════════════════════════════════════


class TestTypeSwitching:
    def test_switch_type_10k_times(self, kg):
        """Switch a single node's type 10k times."""
        def do():
            for i in range(10_000):
                kg.write("chameleon", f"---\ntype: type-{i % 50}\nidx: {i}\n---\nbody-{i}")
        _, elapsed = timed(do)

        meta = kg.frontmatter("chameleon")
        assert meta["type"] == "type-49"
        assert meta["idx"] == "9999"

        # Should only be in the final type table
        for t in range(50):
            safe = f"type_{t}"
            try:
                rows = kg.query(f"SELECT COUNT(*) FROM {safe} WHERE name = 'chameleon'")
                if t == 49:
                    assert rows[0][0] == 1
                else:
                    assert rows[0][0] == 0
            except sqlite3.OperationalError:
                pass
        print(f"\n  10k type switches: {elapsed:.2f}s ({10_000/elapsed:.0f} ops/s)")

    def test_bulk_type_migration(self, kg):
        """Move 10k nodes from one type to another."""
        for i in range(10_000):
            kg.write(f"item-{i}", f"---\ntype: old\nfield: v{i}\n---\nbody")

        assert kg.query("SELECT COUNT(*) FROM old")[0][0] == 10_000

        def migrate():
            for i in range(10_000):
                kg.write(f"item-{i}", f"---\ntype: new\nfield: v{i}\n---\nbody")

        _, elapsed = timed(migrate)
        assert kg.query("SELECT COUNT(*) FROM old")[0][0] == 0
        assert kg.query("SELECT COUNT(*) FROM new")[0][0] == 10_000
        print(f"\n  10k type migration: {elapsed:.2f}s ({10_000/elapsed:.0f} ops/s)")


# ═══════════════════════════════════════════════════════════════════════════
# 7. Schema evolution at scale
# ═══════════════════════════════════════════════════════════════════════════


class TestSchemaEvolution:
    def test_accumulate_100_columns(self, kg):
        """Write nodes that progressively add columns to a type table."""
        for i in range(100):
            fields = "\n".join(f"field_{j}: val_{j}" for j in range(i + 1))
            kg.write(f"node-{i}", f"---\ntype: wide\n{fields}\n---\nbody-{i}")

        cols = {row[1] for row in kg.query("PRAGMA table_info(wide)")}
        assert len(cols) >= 102  # name + content + 100 fields
        # All nodes should still be readable
        for i in range(100):
            content, meta = kg._read_node_data(f"node-{i}")
            assert content == f"body-{i}"
            assert meta["field_0"] == "val_0"

    def test_sparse_wide_kaybee_table(self, kg):
        """Untyped nodes with different frontmatter fields create sparse kaybee table."""
        for i in range(1000):
            field_name = f"field_{i % 50}"
            kg.write(f"sparse-{i}", f"---\n{field_name}: value-{i}\n---\nbody-{i}")

        cols = {row[1] for row in kg.query("PRAGMA table_info(kaybee)")}
        assert len(cols) >= 52  # name + content + 50 unique fields
        # Spot check
        content, meta = kg._read_node_data("sparse-0")
        assert meta["field_0"] == "value-0"
        assert content == "body-0"


# ═══════════════════════════════════════════════════════════════════════════
# 8. Wikilinks at scale
# ═══════════════════════════════════════════════════════════════════════════


class TestWikilinksAtScale:
    def test_10k_nodes_with_links(self, kg):
        """10k nodes, each linking to 2 neighbors."""
        for i in range(10_000):
            prev_link = f"[[node-{i-1}]]" if i > 0 else ""
            next_link = f"[[node-{i+1}]]" if i < 9999 else ""
            kg.write(f"node-{i}", f"---\ntype: chain\n---\n{prev_link} {next_link}")

        # Check link count
        link_count = kg.query("SELECT COUNT(*) FROM _links")[0][0]
        assert link_count >= 19_998  # each internal node has 2 links

        # Check backlinks for a middle node
        bl = kg.backlinks("node-5000")
        assert "node-4999" in bl or "node-5001" in bl

    def test_dense_graph_100_nodes(self, kg):
        """100 nodes, each links to 10 others."""
        for i in range(100):
            links = " ".join(f"[[node-{(i+j) % 100}]]" for j in range(1, 11))
            kg.write(f"node-{i}", f"---\ntype: dense\n---\n{links}")

        g = kg.graph()
        assert len(g) == 100
        for name, targets in g.items():
            assert len(targets) == 10


# ═══════════════════════════════════════════════════════════════════════════
# 9. Delete and cleanup at scale
# ═══════════════════════════════════════════════════════════════════════════


class TestDeleteAtScale:
    def test_rm_10k_nodes(self, kg):
        """Create then delete 10k nodes."""
        for i in range(10_000):
            kg.touch(f"temp-{i}", f"data-{i}")

        assert kg.query("SELECT COUNT(*) FROM nodes")[0][0] == 10_000

        def do():
            for i in range(10_000):
                kg.rm(f"temp-{i}")

        _, elapsed = timed(do)
        assert kg.query("SELECT COUNT(*) FROM nodes")[0][0] == 0
        assert kg.query("SELECT COUNT(*) FROM kaybee")[0][0] == 0
        print(f"\n  rm 10k nodes: {elapsed:.2f}s ({10_000/elapsed:.0f} ops/s)")

    def test_rm_typed_cleans_type_table(self, kg):
        """Deleting typed nodes removes them from type tables."""
        for i in range(5000):
            kg.write(f"item-{i}", f"---\ntype: ephemeral\n---\nbody-{i}")

        assert kg.query("SELECT COUNT(*) FROM ephemeral")[0][0] == 5000

        for i in range(5000):
            kg.rm(f"item-{i}")

        assert kg.query("SELECT COUNT(*) FROM nodes")[0][0] == 0
        assert kg.query("SELECT COUNT(*) FROM ephemeral")[0][0] == 0


# ═══════════════════════════════════════════════════════════════════════════
# 10. mv/cp at scale
# ═══════════════════════════════════════════════════════════════════════════


class TestMvCpAtScale:
    def test_mv_5k_nodes(self, kg):
        """Rename 5k nodes."""
        for i in range(5000):
            kg.write(f"old-{i}", f"---\ntype: movable\nfield: v{i}\n---\nbody-{i}")

        def do():
            for i in range(5000):
                kg.mv(f"old-{i}", f"new-{i}")

        _, elapsed = timed(do)
        assert not kg.exists("old-0")
        assert kg.exists("new-0")
        assert kg.frontmatter("new-0")["field"] == "v0"
        assert kg.query("SELECT COUNT(*) FROM movable")[0][0] == 5000
        print(f"\n  mv 5k nodes: {elapsed:.2f}s ({5000/elapsed:.0f} ops/s)")

    def test_cp_5k_nodes(self, kg):
        """Copy 5k nodes."""
        for i in range(5000):
            kg.write(f"src-{i}", f"---\ntype: copyable\nfield: v{i}\n---\nbody-{i}")

        def do():
            for i in range(5000):
                kg.cp(f"src-{i}", f"dst-{i}")

        _, elapsed = timed(do)
        assert kg.query("SELECT COUNT(*) FROM nodes")[0][0] == 10_000
        assert kg.query("SELECT COUNT(*) FROM copyable")[0][0] == 10_000
        print(f"\n  cp 5k nodes: {elapsed:.2f}s ({5000/elapsed:.0f} ops/s)")


# ═══════════════════════════════════════════════════════════════════════════
# 11. Validator gatekeeper under load
# ═══════════════════════════════════════════════════════════════════════════


class TestGatekeeperPerformance:
    def test_gatekeeper_allows_10k_valid_writes(self, kg):
        """Validator attached, all writes valid — measure overhead."""
        v = Validator()
        v.add(requires_field("concept", "description"))
        v.add(requires_tag("concept"))
        kg.set_validator(v)

        def do():
            for i in range(10_000):
                kg.write(f"item-{i}", f"---\ntype: concept\ndescription: d{i}\ntags: [t{i}]\n---\nbody")

        _, elapsed = timed(do)
        assert kg.query("SELECT COUNT(*) FROM nodes")[0][0] == 10_000
        print(f"\n  10k valid writes with validator: {elapsed:.2f}s ({10_000/elapsed:.0f} ops/s)")

    def test_gatekeeper_blocks_10k_invalid_writes(self, kg):
        """Validator blocks invalid writes — none should persist."""
        v = Validator()
        v.add(requires_field("concept", "description"))
        kg.set_validator(v)

        blocked = 0
        for i in range(10_000):
            try:
                kg.write(f"bad-{i}", f"---\ntype: concept\n---\nno description")
            except ValidationError:
                blocked += 1

        assert blocked == 10_000
        assert kg.query("SELECT COUNT(*) FROM nodes")[0][0] == 0

    def test_gatekeeper_skips_relational_rules(self, kg):
        """Relational rules don't fire pre-write, so no perf penalty."""
        from kaybee.constraints import requires_link
        v = Validator()
        v.add(requires_link("concept"))  # structural=False
        v.add(requires_field("concept", "description"))  # structural=True
        kg.set_validator(v)

        def do():
            for i in range(10_000):
                kg.write(f"item-{i}", f"---\ntype: concept\ndescription: d{i}\n---\nbody")

        _, elapsed = timed(do)
        assert kg.query("SELECT COUNT(*) FROM nodes")[0][0] == 10_000
        print(f"\n  10k writes with mixed rules: {elapsed:.2f}s ({10_000/elapsed:.0f} ops/s)")


# ═══════════════════════════════════════════════════════════════════════════
# 12. Persistence stress at scale
# ═══════════════════════════════════════════════════════════════════════════


class TestPersistenceAtScale:
    def test_50k_nodes_survive_reopen(self, tmp_path):
        """Write 50k nodes, close, reopen, verify all data."""
        path = str(tmp_path / "big.db")
        kg1 = KnowledgeGraph(path)
        for i in range(50_000):
            if i % 2 == 0:
                kg1.touch(f"plain-{i}", f"content-{i}")
            else:
                kg1.write(f"typed-{i}", f"---\ntype: t-{i % 5}\nfield: v{i}\n---\nbody-{i}")
        kg1._db.close()

        kg2 = KnowledgeGraph(path)
        assert kg2.query("SELECT COUNT(*) FROM nodes")[0][0] == 50_000

        # Spot check
        assert kg2.cat("plain-0") == "content-0"
        assert kg2.body("typed-1") == "body-1"
        assert kg2.frontmatter("typed-1")["type"] == "t-1"
        assert kg2.info("plain-100")["type"] is None
        assert kg2.info("typed-101")["type"] == "t-1"
        kg2._db.close()

    def test_incremental_writes_across_reopens(self, tmp_path):
        """Write in batches across 10 reopen cycles."""
        path = str(tmp_path / "incremental.db")
        for batch in range(10):
            kg = KnowledgeGraph(path)
            for i in range(1000):
                idx = batch * 1000 + i
                kg.write(f"item-{idx}", f"---\ntype: batch-{batch}\n---\nbody-{idx}")
            kg._db.close()

        kg = KnowledgeGraph(path)
        assert kg.query("SELECT COUNT(*) FROM nodes")[0][0] == 10_000
        assert len(kg.types()) == 10
        for batch in range(10):
            assert len(kg.find_by_type(f"batch-{batch}")) == 1000
        kg._db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 13. Tree and schema at scale
# ═══════════════════════════════════════════════════════════════════════════


class TestTreeSchemaAtScale:
    def test_tree_with_20_types_1k_each(self, kg):
        """tree() with 20 types, 1000 nodes each = 20k nodes."""
        for i in range(20_000):
            t = i % 20
            kg.write(f"node-{i}", f"---\ntype: type-{t}\n---\ncontent-{i}")

        _, elapsed = timed(lambda: kg.tree())
        output = kg.tree()
        lines = output.splitlines()
        assert len(lines) >= 20_000  # at least one line per node
        print(f"\n  tree 20k nodes: {elapsed:.2f}s, {len(lines)} lines")

    def test_schema_with_50_types(self, kg):
        """schema() with 50 types, each with different fields."""
        for t in range(50):
            fields = "\n".join(f"field_{t}_{j}: val" for j in range(t + 1))
            kg.write(f"node-{t}", f"---\ntype: type-{t}\n{fields}\n---\nbody")

        _, elapsed = timed(lambda: kg.schema())
        s = kg.schema()
        assert len(s) == 50
        for t in range(50):
            assert len(s[f"type-{t}"]) == t + 1
        print(f"\n  schema 50 types: {elapsed:.2f}s")


# ═══════════════════════════════════════════════════════════════════════════
# 14. Direct SQL verification
# ═══════════════════════════════════════════════════════════════════════════


class TestDirectSQLVerification:
    """Verify the new data model via raw SQL at scale."""

    def test_query_type_table_directly(self, kg):
        """Users can query type tables with real SQL columns."""
        for i in range(1000):
            kg.write(f"item-{i}", f"---\ntype: product\nprice: {i * 10}\ncategory: cat-{i % 5}\n---\ndescription-{i}")

        # Real SQL column queries
        rows = kg.query("SELECT name, price, category FROM product WHERE category = 'cat-0' ORDER BY name")
        assert len(rows) == 200

        # Aggregate
        rows = kg.query("SELECT category, COUNT(*) FROM product GROUP BY category ORDER BY category")
        assert len(rows) == 5
        for _, count in rows:
            assert count == 200

    def test_query_kaybee_table_directly(self, kg):
        """Users can query the kaybee table for untyped nodes."""
        for i in range(1000):
            kg.write(f"note-{i}", f"---\nmood: {['happy', 'sad', 'neutral'][i % 3]}\n---\ncontent-{i}")

        rows = kg.query("SELECT name, mood FROM kaybee WHERE mood = 'happy' ORDER BY name")
        assert len(rows) == 334  # ceil(1000/3)

    def test_nodes_index_only_has_name_type(self, kg):
        """SELECT * FROM nodes returns only name and type."""
        kg.write("a", "---\ntype: concept\ndescription: hello\n---\nbody")
        kg.touch("b", "plain text")

        rows = kg.query("SELECT * FROM nodes ORDER BY name")
        assert len(rows) == 2
        # Each row should be (name, type)
        assert rows[0] == ("a", "concept")
        assert rows[1] == ("b", "kaybee")
