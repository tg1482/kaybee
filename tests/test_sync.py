"""Tests for sync_push and sync_pull with scope injection.

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
        return FakeMySQLCursor(self._db)

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


class FakeMySQLConnV2(FakeMySQLConn):
    """Version that returns column-name-only rows for SHOW COLUMNS."""

    def cursor(self):
        return FakeMySQLCursorPragmaAsList(self._db)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mysql_conn():
    return FakeMySQLConnV2()


@pytest.fixture
def kg():
    return KnowledgeGraph()


# ---------------------------------------------------------------------------
# Push tests
# ---------------------------------------------------------------------------

class TestSyncPush:
    def test_push_basic(self, kg, mysql_conn):
        kg.touch("alpha", "hello")
        kg.touch("beta", "world")
        count = sync_push(kg, mysql_conn, scope={"team_id": "eng"})
        assert count == 2

        # Verify data in MySQL
        cur = mysql_conn.cursor()
        cur.execute("SELECT * FROM kaybee")
        rows = cur.fetchall()
        assert len(rows) == 2

    def test_push_scope_injected(self, kg, mysql_conn):
        kg.touch("node1", "content1")
        sync_push(kg, mysql_conn, scope={"team_id": "eng"})

        cur = mysql_conn.cursor()
        cur.execute("SELECT * FROM kaybee WHERE team_id = ?", ("eng",))
        rows = cur.fetchall()
        assert len(rows) == 1

    def test_push_typed_nodes(self, kg, mysql_conn):
        kg.add_type("concept")
        kg.write("idea", "---\ntype: concept\ntags: [ai]\n---\nSome concept")
        count = sync_push(kg, mysql_conn, scope={"user_id": "u1"})
        assert count >= 1

        cur = mysql_conn.cursor()
        cur.execute("SELECT * FROM concept WHERE user_id = ?", ("u1",))
        rows = cur.fetchall()
        assert len(rows) == 1

    def test_push_idempotent(self, kg, mysql_conn):
        kg.touch("a", "data")
        sync_push(kg, mysql_conn, scope={"team_id": "eng"})
        sync_push(kg, mysql_conn, scope={"team_id": "eng"})

        cur = mysql_conn.cursor()
        cur.execute("SELECT * FROM kaybee WHERE team_id = ?", ("eng",))
        rows = cur.fetchall()
        assert len(rows) == 1

    def test_push_empty_graph(self, kg, mysql_conn):
        count = sync_push(kg, mysql_conn, scope={"team_id": "eng"})
        assert count == 0

    def test_push_multi_scope(self, kg, mysql_conn):
        kg.touch("doc", "content")
        sync_push(kg, mysql_conn, scope={"team_id": "eng", "env": "prod"})

        cur = mysql_conn.cursor()
        cur.execute("SELECT * FROM kaybee WHERE team_id = ? AND env = ?", ("eng", "prod"))
        rows = cur.fetchall()
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# Pull tests
# ---------------------------------------------------------------------------

class TestSyncPull:
    def test_pull_basic(self, kg, mysql_conn):
        # Push first, then pull into a fresh KG
        kg.touch("alpha", "hello")
        kg.touch("beta", "world")
        sync_push(kg, mysql_conn, scope={"team_id": "eng"})

        kg2 = KnowledgeGraph()
        # Ensure kaybee table exists in kg2 (it does by default)
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

        # The local table should NOT have team_id column
        cols = [
            r[1] for r in kg2._db.execute("PRAGMA table_info(kaybee)").fetchall()
        ]
        assert "team_id" not in cols

    def test_roundtrip_content_preserved(self, kg, mysql_conn):
        kg.touch("note", "hello world")
        sync_push(kg, mysql_conn, scope={"team_id": "eng"})

        kg2 = KnowledgeGraph()
        sync_pull(kg2, mysql_conn, scope={"team_id": "eng"})
        assert kg2.cat("note") == "hello world"

    def test_pull_no_data(self, kg, mysql_conn):
        # Push some data with scope
        kg.touch("a", "x")
        sync_push(kg, mysql_conn, scope={"team_id": "eng"})

        # Pull with different scope — no match
        kg2 = KnowledgeGraph()
        count = sync_pull(kg2, mysql_conn, scope={"team_id": "sales"})
        assert count == 0


# ---------------------------------------------------------------------------
# Push + Pull round-trip
# ---------------------------------------------------------------------------

class TestSyncRoundTrip:
    def test_full_roundtrip(self, kg, mysql_conn):
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
