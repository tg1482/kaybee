"""Push/pull sync between local SQLite KnowledgeGraph and a remote MySQL database.

Push is changelog-driven when available: only delta entries since a given
sequence number are sent to MySQL.  Falls back to full-table-scan push when
changelog is disabled.  Pull is always a full pull filtered by scope.

Locally: slug is identity, unique per table.
Globally: slug + scope (team_id, user_id, etc.) is identity.
Push: replay changelog entries (or scan tables), inject scope, upsert/delete in MySQL.
Pull: filter MySQL by scope, strip scope, write to local SQLite.

All access to KnowledgeGraph internals goes through the public API:
``kg.query()``, ``kg.commit()``, ``kg.changelog()``, ``kg.changelog_enabled``.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def _local_table_columns(kg, table: str) -> list[str]:
    """Return column names for a local SQLite table via kg.query()."""
    rows = kg.query(f"PRAGMA table_info(`{table}`)")
    return [r[1] for r in rows]


def _mysql_table_columns(cursor, table: str) -> list[str]:
    """Return column names for a MySQL table via cursor."""
    cursor.execute(f"SHOW COLUMNS FROM `{table}`")
    return [row[0] for row in cursor.fetchall()]


def _mysql_table_exists(cursor, table: str) -> bool:
    """Check if a table exists in MySQL."""
    cursor.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name = %s",
        (table,),
    )
    return cursor.fetchone()[0] > 0


def _sqlite_type_to_mysql(col_name: str) -> str:
    """Map SQLite column to a MySQL column type."""
    if col_name == "content":
        return "LONGTEXT"
    return "TEXT"


def _ensure_mysql_table(
    cursor,
    table: str,
    columns: list[str],
    scope_keys: list[str],
    unique_on: list[str],
    *,
    _cache: dict[str, set[str]] | None = None,
) -> None:
    """Create or alter the MySQL table to have all needed columns + unique key.

    When *_cache* is provided, skip repeated information_schema queries for
    tables already seen in this batch.
    """
    all_cols = list(scope_keys) + columns

    if _cache is not None and table in _cache:
        # Already confirmed to exist — only check for new columns
        existing = _cache[table]
        for col in all_cols:
            if col not in existing:
                mysql_type = _sqlite_type_to_mysql(col)
                cursor.execute(f"ALTER TABLE `{table}` ADD COLUMN `{col}` {mysql_type}")
                existing.add(col)
        return

    if not _mysql_table_exists(cursor, table):
        col_defs = []
        for col in all_cols:
            mysql_type = _sqlite_type_to_mysql(col)
            col_defs.append(f"`{col}` {mysql_type}")
        unique_cols = ", ".join(f"`{c}`" for c in unique_on)
        col_defs_str = ", ".join(col_defs)
        cursor.execute(
            f"CREATE TABLE `{table}` ({col_defs_str}, UNIQUE ({unique_cols}))"
        )
        if _cache is not None:
            _cache[table] = set(all_cols)
    else:
        existing = set(_mysql_table_columns(cursor, table))
        for col in all_cols:
            if col not in existing:
                mysql_type = _sqlite_type_to_mysql(col)
                cursor.execute(f"ALTER TABLE `{table}` ADD COLUMN `{col}` {mysql_type}")
                existing.add(col)
        if _cache is not None:
            _cache[table] = existing


def _upsert_to_mysql(
    cursor,
    table: str,
    name: str,
    content: str,
    meta: dict,
    scope: dict,
    *,
    _cache: dict[str, set[str]] | None = None,
) -> None:
    """Upsert a single row to a MySQL type table with scope injection."""
    scope_keys = list(scope.keys())
    scope_vals = list(scope.values())

    # Build column list from meta keys (excluding 'type')
    meta_keys = [k for k in meta if k != "type"]
    local_cols = ["name", "content"] + meta_keys
    unique_on = ["name"] + scope_keys

    _ensure_mysql_table(cursor, table, local_cols, scope_keys, unique_on, _cache=_cache)

    all_cols = scope_keys + local_cols
    vals = scope_vals + [name, content] + [
        json.dumps(v) if isinstance(v, (list, dict)) else str(v)
        for v in (meta[k] for k in meta_keys)
    ]

    placeholders = ", ".join(["%s"] * len(all_cols))
    col_str = ", ".join(f"`{c}`" for c in all_cols)
    update_parts = ", ".join(
        f"`{c}` = VALUES(`{c}`)" for c in all_cols if c not in unique_on
    )

    if update_parts:
        cursor.execute(
            f"INSERT INTO `{table}` ({col_str}) VALUES ({placeholders}) "
            f"ON DUPLICATE KEY UPDATE {update_parts}",
            vals,
        )
    else:
        cursor.execute(
            f"INSERT IGNORE INTO `{table}` ({col_str}) VALUES ({placeholders})",
            vals,
        )


def _delete_from_mysql(
    cursor,
    table: str,
    name: str,
    scope: dict,
    *,
    _cache: dict[str, set[str]] | None = None,
) -> None:
    """Delete a row from a MySQL type table by name + scope."""
    if _cache is not None:
        if table not in _cache:
            if not _mysql_table_exists(cursor, table):
                return
    else:
        if not _mysql_table_exists(cursor, table):
            return
    scope_keys = list(scope.keys())
    scope_vals = list(scope.values())
    where_parts = ["`name` = %s"] + [f"`{k}` = %s" for k in scope_keys]
    where = " AND ".join(where_parts)
    cursor.execute(f"DELETE FROM `{table}` WHERE {where}", [name] + scope_vals)


# ---------------------------------------------------------------------------
# Full-table-scan push (fallback when changelog is disabled)
# ---------------------------------------------------------------------------

def _sync_push_full(kg, mysql_conn, scope: dict) -> int:
    """Push all local nodes to MySQL with scope injection.

    Reads every node via the public API (mode-agnostic) and upserts to MySQL.
    Does not propagate deletes — if a node was removed locally it simply won't
    be pushed, but the stale row remains in MySQL.

    Returns 0 (no changelog position to track).
    """
    cursor = mysql_conn.cursor()
    cache: dict[str, set[str]] = {}

    for name in kg.ls("*"):
        nfo = kg.info(name)
        type_name = nfo["type"] or "kaybee"
        content = kg.body(name)
        meta = kg.frontmatter(name)
        _upsert_to_mysql(cursor, type_name, name, content, meta, scope, _cache=cache)

    mysql_conn.commit()
    cursor.close()
    return 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def sync_push(kg, mysql_conn, scope: dict, *, since_seq: int = 0) -> int:
    """Push local changes to MySQL with scope injection.

    When changelog is enabled (default), replays changelog entries since
    *since_seq* — only changed rows are sent.  Loops internally until all
    pending entries are drained, so the caller never gets a partial result.

    When changelog is disabled, falls back to a full-table-scan push that
    upserts every row.  In this mode *since_seq* is ignored and the return
    value is always 0.  Deletes are NOT propagated in full-scan mode.

    Args:
        kg: A KnowledgeGraph instance.
        mysql_conn: A MySQL connection (e.g. from mysql.connector or pymysql).
        scope: Scope dict injected into every row, e.g. {"team_id": "eng"}.
        since_seq: Only process changelog entries after this sequence number.
            Ignored when changelog is disabled.

    Returns:
        Last seq processed (caller persists this for next call).
        Returns since_seq unchanged if there are no new entries.
        Returns 0 when changelog is disabled (no position to track).
    """
    if not kg.changelog_enabled:
        return _sync_push_full(kg, mysql_conn, scope)

    cursor = mysql_conn.cursor()
    cache: dict[str, set[str]] = {}
    last_seq = since_seq

    while True:
        entries = kg.changelog(since_seq=last_seq, limit=10_000)
        if not entries:
            break

        for seq, ts, op, name, data_json in entries:
            data = json.loads(data_json) if data_json else {}

            if op == "node.write":
                type_name = data.get("type", "kaybee")
                content = data.get("content", "")
                meta = data.get("meta", {})
                _upsert_to_mysql(cursor, type_name, name, content, meta, scope, _cache=cache)

            elif op == "node.rm":
                type_name = data.get("type", "kaybee")
                _delete_from_mysql(cursor, type_name, name, scope, _cache=cache)

            elif op == "node.mv":
                type_name = data.get("type", "kaybee")
                old_name = data.get("old_name", "")
                content = data.get("content", "")
                meta = data.get("meta", {})
                _delete_from_mysql(cursor, type_name, old_name, scope, _cache=cache)
                _upsert_to_mysql(cursor, type_name, name, content, meta, scope, _cache=cache)

            elif op == "node.type_change":
                old_type = data.get("old_type", "kaybee")
                new_type = data.get("type", "kaybee")
                content = data.get("content", "")
                meta = data.get("meta", {})
                _delete_from_mysql(cursor, old_type, name, scope, _cache=cache)
                _upsert_to_mysql(cursor, new_type, name, content, meta, scope, _cache=cache)

            elif op == "node.cp":
                type_name = data.get("type", "kaybee")
                content = data.get("content", "")
                meta = data.get("meta", {})
                _upsert_to_mysql(cursor, type_name, name, content, meta, scope, _cache=cache)

            elif op == "type.add":
                scope_keys = list(scope.keys())
                unique_on = ["name"] + scope_keys
                _ensure_mysql_table(cursor, name, ["name", "content"], scope_keys, unique_on, _cache=cache)

            # type.rm: no-op (don't drop remote tables)

            last_seq = seq

    mysql_conn.commit()
    cursor.close()
    return last_seq


def _get_mysql_tables(cursor, scope_keys: list[str]) -> list[str]:
    """Discover which MySQL tables have the scope columns (i.e., were pushed by kaybee)."""
    cursor.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = DATABASE()"
    )
    all_tables = [r[0] for r in cursor.fetchall()]
    result = []
    for table in all_tables:
        cols = set(_mysql_table_columns(cursor, table))
        if all(k in cols for k in scope_keys) and "name" in cols:
            result.append(table)
    return result


def sync_pull(kg, mysql_conn, scope: dict) -> int:
    """Pull rows matching scope from MySQL into local kaybee.

    This is a full pull — all rows matching scope are fetched and written
    to the local SQLite database via ``kg.query()`` (raw SQL).  These writes
    bypass ``kg.write()`` intentionally so they do NOT generate changelog
    entries (no push-back loop).

    Args:
        kg: A KnowledgeGraph instance.
        mysql_conn: A MySQL connection.
        scope: Filter dict, e.g. {"team_id": "eng"}.

    Returns:
        Total number of rows pulled.
    """
    scope_keys = list(scope.keys())
    scope_vals = list(scope.values())
    cursor = mysql_conn.cursor()
    mysql_tables = _get_mysql_tables(cursor, scope_keys)
    total = 0

    for type_name in mysql_tables:
        if not _mysql_table_exists(cursor, type_name):
            continue

        where = " AND ".join(f"`{k}` = %s" for k in scope_keys)
        cursor.execute(f"SELECT * FROM `{type_name}` WHERE {where}", scope_vals)
        mysql_cols = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

        # Determine which columns are local (strip scope columns)
        local_cols = [c for c in mysql_cols if c not in scope_keys]
        local_idxs = [mysql_cols.index(c) for c in local_cols]

        # Ensure _data has all columns
        existing_local = set(_local_table_columns(kg, "_data"))
        for col in local_cols:
            if col not in existing_local:
                kg.query(f"ALTER TABLE _data ADD COLUMN `{col}` TEXT")
                existing_local.add(col)

        # Register type-specific fields in _type_fields
        if type_name != "kaybee":
            for col in local_cols:
                if col not in ("name", "content"):
                    kg.query(
                        "INSERT OR IGNORE INTO _type_fields (type_name, field_name) VALUES (?, ?)",
                        (type_name, col),
                    )

        col_str = ", ".join(f"`{c}`" for c in local_cols)
        placeholders = ", ".join(["?"] * len(local_cols))

        for row in rows:
            vals = tuple(row[i] for i in local_idxs)
            kg.query(
                f"INSERT OR REPLACE INTO _data ({col_str}) VALUES ({placeholders})",
                vals,
            )
            total += 1

        # Also ensure nodes index is updated for pulled rows
        if "name" in local_cols:
            for row in rows:
                name_val = row[mysql_cols.index("name")]
                existing = kg.query(
                    "SELECT 1 FROM nodes WHERE name = ?", (name_val,)
                )
                if not existing:
                    kg.query(
                        "INSERT OR IGNORE INTO nodes (name, type) VALUES (?, ?)",
                        (name_val, type_name),
                    )

    kg.commit()
    cursor.close()
    return total
