"""Push/pull sync between local SQLite KnowledgeGraph and a remote MySQL database.

Locally: slug is identity, unique per table.
Globally: slug + scope (team_id, user_id, etc.) is identity.
Push: inject scope into every row, upsert to MySQL on composite unique key.
Pull: filter MySQL by scope, strip scope, write to local SQLite.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def _get_user_tables(kg) -> list[str]:
    """Return names of user-created type tables (including 'kaybee')."""
    rows = kg._db.execute(
        "SELECT DISTINCT type FROM nodes"
    ).fetchall()
    return list({r[0] for r in rows})


def _table_columns(db, table: str) -> list[str]:
    """Return column names for a table."""
    rows = db.execute(f"PRAGMA table_info({table})").fetchall()
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


def _ensure_mysql_table(cursor, table: str, columns: list[str], scope_keys: list[str], unique_on: list[str]) -> None:
    """Create or alter the MySQL table to have all needed columns + unique key."""
    all_cols = list(scope_keys) + columns
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
    else:
        existing = set(_mysql_table_columns(cursor, table))
        for col in all_cols:
            if col not in existing:
                mysql_type = _sqlite_type_to_mysql(col)
                cursor.execute(f"ALTER TABLE `{table}` ADD COLUMN `{col}` {mysql_type}")


def sync_push(kg, mysql_conn, scope: dict, unique_on: list[str] | None = None) -> int:
    """Push all kaybee tables to MySQL with scope injection.

    Args:
        kg: A KnowledgeGraph instance.
        mysql_conn: A MySQL connection (e.g. from mysql.connector or pymysql).
        scope: Scope dict injected into every row, e.g. {"team_id": "eng"}.
        unique_on: Columns for ON DUPLICATE KEY. Defaults to ["name"] + scope keys.

    Returns:
        Total number of rows pushed.
    """
    scope_keys = list(scope.keys())
    scope_vals = list(scope.values())
    tables = _get_user_tables(kg)
    cursor = mysql_conn.cursor()
    total = 0

    for table in tables:
        cols = _table_columns(kg._db, table)
        if not cols:
            continue

        uk = unique_on if unique_on else (["name"] + scope_keys)
        _ensure_mysql_table(cursor, table, cols, scope_keys, uk)

        rows = kg._db.execute(f"SELECT * FROM `{table}`").fetchall()
        if not rows:
            continue

        all_cols = scope_keys + cols
        placeholders = ", ".join(["%s"] * len(all_cols))
        col_str = ", ".join(f"`{c}`" for c in all_cols)
        update_parts = ", ".join(
            f"`{c}` = VALUES(`{c}`)" for c in all_cols if c not in uk
        )

        for row in rows:
            vals = scope_vals + list(row)
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
            total += 1

    mysql_conn.commit()
    cursor.close()
    return total


def _get_mysql_tables(cursor, scope_keys: list[str]) -> list[str]:
    """Discover which MySQL tables have the scope columns (i.e., were pushed by kaybee)."""
    # List all tables in the database
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
    tables = _get_mysql_tables(cursor, scope_keys)
    total = 0

    for table in tables:
        if not _mysql_table_exists(cursor, table):
            continue

        where = " AND ".join(f"`{k}` = %s" for k in scope_keys)
        cursor.execute(f"SELECT * FROM `{table}` WHERE {where}", scope_vals)
        mysql_cols = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

        # Determine which columns are local (strip scope columns)
        local_cols = [c for c in mysql_cols if c not in scope_keys]
        local_idxs = [mysql_cols.index(c) for c in local_cols]

        # Ensure local table exists and has all columns
        existing_local = set(_table_columns(kg._db, table))
        if not existing_local:
            # Table doesn't exist locally — create it
            col_defs = ", ".join(f"`{c}` TEXT" for c in local_cols)
            kg._db.execute(f"CREATE TABLE IF NOT EXISTS `{table}` ({col_defs})")
            existing_local = set(local_cols)
        else:
            for col in local_cols:
                if col not in existing_local:
                    safe_col = col.replace('"', '""')
                    kg._db.execute(f'ALTER TABLE `{table}` ADD COLUMN `{safe_col}` TEXT')

        col_str = ", ".join(f"`{c}`" for c in local_cols)
        placeholders = ", ".join(["?"] * len(local_cols))

        for row in rows:
            vals = [row[i] for i in local_idxs]
            kg._db.execute(
                f"INSERT OR REPLACE INTO `{table}` ({col_str}) VALUES ({placeholders})",
                vals,
            )
            total += 1

        # Also ensure nodes index is updated for pulled rows
        if "name" in local_cols:
            name_idx = local_cols.index("name")
            for row in rows:
                name_val = row[mysql_cols.index("name")]
                # Check if already in nodes
                existing = kg._db.execute(
                    "SELECT 1 FROM nodes WHERE name = ?", (name_val,)
                ).fetchone()
                if not existing:
                    kg._db.execute(
                        "INSERT OR IGNORE INTO nodes (name, type) VALUES (?, ?)",
                        (name_val, table),
                    )

    kg._db.commit()
    cursor.close()
    return total
