"""Tests for changelog-driven sync_push and full sync_pull with scope injection.

Uses a fake MySQL adapter backed by SQLite to avoid requiring a real MySQL server.
"""

import sqlite3
import pytest

from kaybee.core import KnowledgeGraph
from kaybee.sync import sync_push, sync_pull


# ---------------------------------------------------------------------------
# Fake MySQL adapter (SQLite-backed)
# ---------------------------------------------------------------------------

class FakeMySQLCursor:
    """Mimics a MySQL cursor using an SQLite connection underneath."""

    def __init__(self, sqlite_conn):
        self._db = sqlite_conn
        self.description = None
        self._last_result = None

    def execute(self, sql, params=None):
        # Translate MySQL-isms to SQLite
        sql = self._translate(sql)
        params = params or ()
        # Convert list params to tuple
        if isinstance(params, list):
            params = tuple(params)
        self._last_result = self._db.execute(sql, params)
        if self._last_result.description:
            self.description = self._last_result.description

    def fetchall(self):
        return self._last_result.fetchall()

    def fetchone(self):
        return self._last_result.fetchone()

    def close(self):
        pass

    def _translate(self, sql: str) -> str:
        # SHOW COLUMNS -> pragma-based query
        if sql.strip().upper().startswith("SHOW COLUMNS"):
            table = sql.split("`")[1]
            return f"PRAGMA table_info(`{table}`)"

        # information_schema — listing all tables
        if "information_schema.tables" in sql.lower() and "table_name" in sql.lower() and "COUNT" not in sql.upper():
            return (
                "SELECT name FROM sqlite_master "
                "WHERE type='table'"
            )

        # information_schema check -> sqlite_master (existence check)
        if "information_schema.tables" in sql.lower():
            return (
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type='table' AND name=?"
            )

        # ON DUPLICATE KEY UPDATE -> INSERT OR REPLACE
        if "ON DUPLICATE KEY UPDATE" in sql:
            insert_part = sql.split("ON DUPLICATE KEY UPDATE")[0].strip()
            insert_part = insert_part.replace("INSERT INTO", "INSERT OR REPLACE INTO", 1)
            sql = insert_part

        # INSERT IGNORE -> INSERT OR IGNORE
        sql = sql.replace("INSERT IGNORE INTO", "INSERT OR IGNORE INTO")

        # %s -> ? for SQLite parameter binding
        sql = sql.replace("%s", "?")

        return sql


class FakeMySQLConn:
    """Mimics a MySQL connection using SQLite."""

    def __init__(self):
        self._db = sqlite3.connect(":memory:")

    def cursor(self):
        return FakeMySQLCursorPragmaAsList(self._db)

    def commit(self):
        self._db.commit()


class FakeMySQLCursorPragmaAsList(FakeMySQLCursor):
    """Override to make PRAGMA table_info return (col_name,) tuples for SHOW COLUMNS."""

    def fetchall(self):
        rows = self._last_result.fetchall()
        # If this was a PRAGMA table_info call, transform to (name,) format
        if rows and len(rows) > 0 and len(rows[0]) == 6:
            return [(r[1],) for r in rows]
        return rows


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mysql_conn():
    return FakeMySQLConn()


@pytest.fixture
def kg():
    return KnowledgeGraph()


# ---------------------------------------------------------------------------
# Push tests — changelog-driven
# ---------------------------------------------------------------------------

class TestSyncPush:
    def test_push_write_only_sends_changed(self, kg, mysql_conn):
        """Write 3 nodes, push all, write 1 more, push delta — only 1 new row."""
        kg.touch("a", "alpha")
        kg.touch("b", "beta")
        kg.touch("c", "gamma")
        last_seq = sync_push(kg, mysql_conn, scope={"team_id": "eng"})

        # All 3 should be in MySQL
        cur = mysql_conn.cursor()
        cur.execute("SELECT name FROM kaybee ORDER BY name")
        names = [r[0] for r in cur.fetchall()]
        assert names == ["a", "b", "c"]

        # Write one more node
        kg.touch("d", "delta")
        last_seq2 = sync_push(kg, mysql_conn, scope={"team_id": "eng"}, since_seq=last_seq)
        assert last_seq2 > last_seq

        cur.execute("SELECT name FROM kaybee ORDER BY name")
        names = [r[0] for r in cur.fetchall()]
        assert names == ["a", "b", "c", "d"]

    def test_push_rm_deletes_remote(self, kg, mysql_conn):
        """Write + push, rm + push — row gone from MySQL."""
        kg.touch("ephemeral", "will be removed")
        last_seq = sync_push(kg, mysql_conn, scope={"team_id": "eng"})

        cur = mysql_conn.cursor()
        cur.execute("SELECT COUNT(*) FROM kaybee WHERE name = ?", ("ephemeral",))
        assert cur.fetchone()[0] == 1

        kg.rm("ephemeral")
        sync_push(kg, mysql_conn, scope={"team_id": "eng"}, since_seq=last_seq)

        cur.execute("SELECT COUNT(*) FROM kaybee WHERE name = ?", ("ephemeral",))
        assert cur.fetchone()[0] == 0

    def test_push_mv_updates_remote(self, kg, mysql_conn):
        """Write + push, mv + push — old name gone, new name present."""
        kg.touch("old-name", "content")
        last_seq = sync_push(kg, mysql_conn, scope={"team_id": "eng"})

        kg.mv("old-name", "new-name")
        sync_push(kg, mysql_conn, scope={"team_id": "eng"}, since_seq=last_seq)

        cur = mysql_conn.cursor()
        cur.execute("SELECT COUNT(*) FROM kaybee WHERE name = ?", ("old-name",))
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT COUNT(*) FROM kaybee WHERE name = ?", ("new-name",))
        assert cur.fetchone()[0] == 1

    def test_push_returns_last_seq(self, kg, mysql_conn):
        """Return value matches last changelog entry seq."""
        kg.touch("x", "data")
        last_seq = sync_push(kg, mysql_conn, scope={"team_id": "eng"})
        entries = kg.changelog()
        assert last_seq == entries[-1][0]

    def test_push_noop_returns_same_seq(self, kg, mysql_conn):
        """No changes after initial push — returns since_seq."""
        kg.touch("x", "data")
        last_seq = sync_push(kg, mysql_conn, scope={"team_id": "eng"})
        result = sync_push(kg, mysql_conn, scope={"team_id": "eng"}, since_seq=last_seq)
        assert result == last_seq

    def test_push_scope_injected(self, kg, mysql_conn):
        """Scope columns present in MySQL rows."""
        kg.touch("node1", "content1")
        sync_push(kg, mysql_conn, scope={"team_id": "eng"})

        cur = mysql_conn.cursor()
        cur.execute("SELECT * FROM kaybee WHERE team_id = ?", ("eng",))
        rows = cur.fetchall()
        assert len(rows) == 1

    def test_push_typed_nodes(self, kg, mysql_conn):
        """Typed nodes land in their own MySQL table."""
        kg.add_type("concept")
        kg.write("idea", "---\ntype: concept\ntags: [ai]\n---\nSome concept")
        sync_push(kg, mysql_conn, scope={"user_id": "u1"})

        cur = mysql_conn.cursor()
        cur.execute("SELECT * FROM concept WHERE user_id = ?", ("u1",))
        rows = cur.fetchall()
        assert len(rows) == 1

    def test_push_empty_changelog(self, kg, mysql_conn):
        """No changelog entries — returns 0."""
        result = sync_push(kg, mysql_conn, scope={"team_id": "eng"})
        assert result == 0

    def test_push_cp_upserts_dst(self, kg, mysql_conn):
        """Copy operation upserts the destination node."""
        kg.touch("src", "source content")
        last_seq = sync_push(kg, mysql_conn, scope={"team_id": "eng"})

        kg.cp("src", "dst")
        sync_push(kg, mysql_conn, scope={"team_id": "eng"}, since_seq=last_seq)

        cur = mysql_conn.cursor()
        cur.execute("SELECT COUNT(*) FROM kaybee WHERE name = ?", ("dst",))
        assert cur.fetchone()[0] == 1


# ---------------------------------------------------------------------------
# Pull tests
# ---------------------------------------------------------------------------

class TestSyncPull:
    def test_pull_basic(self, kg, mysql_conn):
        kg.touch("alpha", "hello")
        kg.touch("beta", "world")
        sync_push(kg, mysql_conn, scope={"team_id": "eng"})

        kg2 = KnowledgeGraph()
        count = sync_pull(kg2, mysql_conn, scope={"team_id": "eng"})
        assert count == 2
        assert kg2.exists("alpha")
        assert kg2.exists("beta")

    def test_pull_scope_filter(self, kg, mysql_conn):
        kg.touch("shared", "data")
        sync_push(kg, mysql_conn, scope={"team_id": "eng"})

        kg2 = KnowledgeGraph()
        kg2.touch("other", "x")
        sync_push(kg2, mysql_conn, scope={"team_id": "sales"})

        kg3 = KnowledgeGraph()
        count = sync_pull(kg3, mysql_conn, scope={"team_id": "eng"})
        assert count == 1
        assert kg3.exists("shared")
        assert not kg3.exists("other")

    def test_pull_strips_scope(self, kg, mysql_conn):
        kg.touch("doc", "content")
        sync_push(kg, mysql_conn, scope={"team_id": "eng"})

        kg2 = KnowledgeGraph()
        sync_pull(kg2, mysql_conn, scope={"team_id": "eng"})

        cols = [
            r[1] for r in kg2._db.execute("PRAGMA table_info(kaybee)").fetchall()
        ]
        assert "team_id" not in cols

    def test_pull_no_data(self, kg, mysql_conn):
        kg.touch("a", "x")
        sync_push(kg, mysql_conn, scope={"team_id": "eng"})

        kg2 = KnowledgeGraph()
        count = sync_pull(kg2, mysql_conn, scope={"team_id": "sales"})
        assert count == 0


# ---------------------------------------------------------------------------
# Push + Pull round-trip
# ---------------------------------------------------------------------------

class TestSyncRoundTrip:
    def test_roundtrip(self, kg, mysql_conn):
        """Push then pull into fresh KG — content preserved."""
        kg.add_type("concept")
        kg.write("idea", "---\ntype: concept\ntags: [demo]\n---\nGreat idea")
        kg.touch("readme", "Welcome")

        sync_push(kg, mysql_conn, scope={"team_id": "eng"})

        kg2 = KnowledgeGraph()
        kg2.add_type("concept")
        sync_pull(kg2, mysql_conn, scope={"team_id": "eng"})

        assert kg2.exists("readme")
        assert kg2.exists("idea")
        assert kg2.cat("readme") == "Welcome"

    def test_roundtrip_content_preserved(self, kg, mysql_conn):
        kg.touch("note", "hello world")
        sync_push(kg, mysql_conn, scope={"team_id": "eng"})

        kg2 = KnowledgeGraph()
        sync_pull(kg2, mysql_conn, scope={"team_id": "eng"})
        assert kg2.cat("note") == "hello world"


# ---------------------------------------------------------------------------
# Full-table fallback (changelog disabled)
# ---------------------------------------------------------------------------

class TestSyncPushFullFallback:
    @pytest.fixture
    def kg_no_cl(self):
        return KnowledgeGraph(changelog=False)

    def test_fallback_pushes_all_rows(self, kg_no_cl, mysql_conn):
        """With changelog disabled, sync_push still pushes all rows."""
        kg_no_cl.touch("a", "alpha")
        kg_no_cl.touch("b", "beta")
        result = sync_push(kg_no_cl, mysql_conn, scope={"team_id": "eng"})
        assert result == 0  # no seq to track

        cur = mysql_conn.cursor()
        cur.execute("SELECT name FROM kaybee ORDER BY name")
        names = [r[0] for r in cur.fetchall()]
        assert names == ["a", "b"]

    def test_fallback_returns_zero(self, kg_no_cl, mysql_conn):
        """Full-table push returns 0 (no changelog position)."""
        kg_no_cl.touch("x", "data")
        assert sync_push(kg_no_cl, mysql_conn, scope={"team_id": "eng"}) == 0

    def test_fallback_idempotent(self, kg_no_cl, mysql_conn):
        """Repeated full-table pushes don't duplicate rows."""
        kg_no_cl.touch("x", "data")
        sync_push(kg_no_cl, mysql_conn, scope={"team_id": "eng"})
        sync_push(kg_no_cl, mysql_conn, scope={"team_id": "eng"})

        cur = mysql_conn.cursor()
        cur.execute("SELECT COUNT(*) FROM kaybee WHERE name = ?", ("x",))
        assert cur.fetchone()[0] == 1

    def test_fallback_scope_injected(self, kg_no_cl, mysql_conn):
        """Full-table push still injects scope columns."""
        kg_no_cl.touch("node1", "content1")
        sync_push(kg_no_cl, mysql_conn, scope={"team_id": "eng"})

        cur = mysql_conn.cursor()
        cur.execute("SELECT * FROM kaybee WHERE team_id = ?", ("eng",))
        rows = cur.fetchall()
        assert len(rows) == 1

    def test_fallback_typed_nodes(self, kg_no_cl, mysql_conn):
        """Full-table push handles typed tables."""
        kg_no_cl.add_type("concept")
        kg_no_cl.write("idea", "---\ntype: concept\ntags: [ai]\n---\nBody")
        sync_push(kg_no_cl, mysql_conn, scope={"user_id": "u1"})

        cur = mysql_conn.cursor()
        cur.execute("SELECT * FROM concept WHERE user_id = ?", ("u1",))
        rows = cur.fetchall()
        assert len(rows) == 1

    def test_fallback_empty_graph(self, kg_no_cl, mysql_conn):
        """Empty graph pushes nothing."""
        assert sync_push(kg_no_cl, mysql_conn, scope={"team_id": "eng"}) == 0

    def test_fallback_roundtrip(self, kg_no_cl, mysql_conn):
        """Full-table push then pull into fresh KG."""
        kg_no_cl.touch("note", "hello")
        sync_push(kg_no_cl, mysql_conn, scope={"team_id": "eng"})

        kg2 = KnowledgeGraph(changelog=False)
        count = sync_pull(kg2, mysql_conn, scope={"team_id": "eng"})
        assert count == 1
        assert kg2.cat("note") == "hello"


# ---------------------------------------------------------------------------
# Drain loop (changelog entries beyond single batch)
# ---------------------------------------------------------------------------

class TestSyncPushDrainLoop:
    def test_push_drains_all_entries(self, kg, mysql_conn):
        """sync_push loops until all changelog entries are consumed."""
        # Create enough entries to exceed a small batch.
        # We can't easily set the internal limit, but we can verify
        # that ALL entries are processed by creating many nodes and
        # checking they all land in MySQL.
        for i in range(25):
            kg.touch(f"n{i:03d}", f"content-{i}")

        last_seq = sync_push(kg, mysql_conn, scope={"team_id": "eng"})

        # Verify all 25 are in MySQL
        cur = mysql_conn.cursor()
        cur.execute("SELECT COUNT(*) FROM kaybee")
        assert cur.fetchone()[0] == 25

        # Verify last_seq matches the actual last changelog entry
        entries = kg.changelog()
        assert last_seq == entries[-1][0]

        # A subsequent push with that seq should be a no-op
        assert sync_push(kg, mysql_conn, scope={"team_id": "eng"}, since_seq=last_seq) == last_seq
