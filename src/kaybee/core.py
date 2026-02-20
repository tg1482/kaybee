"""SQLite-native knowledge graph with YAML frontmatter and wikilink support.

Flat architecture — nodes are identified by name (auto-slugified), grouped by
``type``.  No directories, no paths, no hierarchy.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from typing import Any


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def slugify(value: str) -> str:
    """Convert a string to a URL/identifier-safe slug.

    Lowercases, replaces non-alphanumeric runs with hyphens,
    strips leading/trailing hyphens. Returns "item" for empty results.

    Example:
        slugify("Hello World!")  # -> "hello-world"
        slugify("  My File (2).txt")  # -> "my-file-2-.txt"
    """
    text = value.strip().lower()
    out: list[str] = []
    prev_sep = False
    for ch in text:
        if ch.isalnum() or ch in ("_", "."):
            out.append(ch)
            prev_sep = False
        else:
            if not prev_sep and out:
                out.append("-")
                prev_sep = True
    result = "".join(out).strip("-")
    return result or "item"


# ---------------------------------------------------------------------------
# Pure functions: frontmatter parsing & wikilink extraction
# ---------------------------------------------------------------------------

_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def extract_wikilinks(text: str) -> list[str]:
    """Extract all ``[[wikilink]]`` targets from *text*."""
    return _WIKILINK_RE.findall(text)


def _parse_yaml_subset(yaml_str: str) -> dict[str, Any]:
    """Parse a minimal YAML subset into a dict.

    Supports:
    - ``key: value`` (strings, unquoted or quoted)
    - ``key: [a, b, c]`` (inline lists)
    - ``key:\\n  - a\\n  - b`` (block lists)
    - ``key:\\n  sub: val`` (one-level nested dicts)
    - ``# comments`` are ignored
    """
    result: dict[str, Any] = {}
    lines = yaml_str.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip blanks and comments
        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        # Must be a top-level key
        colon = stripped.find(":")
        if colon == -1:
            i += 1
            continue

        key = stripped[:colon].strip()
        rest = stripped[colon + 1 :].strip()

        # Remove inline comment (but not inside quotes)
        if rest and not rest.startswith("[") and not rest.startswith('"') and not rest.startswith("'"):
            comment_idx = rest.find(" #")
            if comment_idx != -1:
                rest = rest[:comment_idx].strip()

        if rest:
            # Inline value
            result[key] = _parse_yaml_value(rest)
            i += 1
        else:
            # Block value: look at indented lines below
            block_items: list[str] = []
            is_list = False
            is_dict = False
            j = i + 1
            while j < len(lines):
                bline = lines[j]
                if not bline.strip() or (not bline[0].isspace() and bline.strip() and not bline.strip().startswith("#")):
                    break
                if bline.strip().startswith("#"):
                    j += 1
                    continue
                block_items.append(bline)
                bstripped = bline.strip()
                if bstripped.startswith("- "):
                    is_list = True
                elif ":" in bstripped and not bstripped.startswith("- "):
                    is_dict = True
                j += 1

            if is_list:
                items = []
                for bl in block_items:
                    bs = bl.strip()
                    if bs.startswith("- "):
                        items.append(_unquote(bs[2:].strip()))
                result[key] = items
            elif is_dict:
                sub: dict[str, str] = {}
                for bl in block_items:
                    bs = bl.strip()
                    sc = bs.find(":")
                    if sc != -1:
                        sk = bs[:sc].strip()
                        sv = bs[sc + 1 :].strip()
                        sub[sk] = _unquote(sv)
                result[key] = sub
            else:
                # Single indented value or empty
                if block_items:
                    result[key] = _unquote(block_items[0].strip())
                else:
                    result[key] = ""
            i = j
            continue

        # Already incremented i inside the ``if rest:`` branch

    return result


def _parse_yaml_value(val: str) -> Any:
    """Parse a single YAML inline value."""
    if val.startswith("[") and val.endswith("]"):
        inner = val[1:-1].strip()
        if not inner:
            return []
        return [_unquote(item.strip()) for item in _split_yaml_list(inner)]
    return _unquote(val)


def _split_yaml_list(s: str) -> list[str]:
    """Split a YAML inline list body on commas, respecting quotes."""
    items: list[str] = []
    current: list[str] = []
    in_quote: str | None = None
    for ch in s:
        if in_quote:
            current.append(ch)
            if ch == in_quote:
                in_quote = None
        elif ch in ('"', "'"):
            in_quote = ch
            current.append(ch)
        elif ch == ",":
            items.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        items.append("".join(current).strip())
    return items


def _unquote(val: str) -> str:
    """Remove surrounding quotes from a string value."""
    if len(val) >= 2:
        if (val[0] == '"' and val[-1] == '"') or (val[0] == "'" and val[-1] == "'"):
            return val[1:-1]
    return val


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split YAML frontmatter from body text.

    Returns ``(meta_dict, body_string)``.  If there is no frontmatter the
    meta dict is empty and the full text is returned as body.
    """
    if not text.startswith("---"):
        return {}, text

    # Find closing fence
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text

    yaml_block = text[3:end].strip()
    body = text[end + 4 :].lstrip("\n")
    meta = _parse_yaml_subset(yaml_block)
    return meta, body


# ---------------------------------------------------------------------------
# KnowledgeGraph
# ---------------------------------------------------------------------------

_RESERVED_TYPE_NAMES = frozenset({"nodes", "_types", "_links", "_changelog", "_data", "_type_fields"})

_SCHEMA_SQL_COMMON = """
CREATE TABLE IF NOT EXISTS nodes (
    name    TEXT PRIMARY KEY,
    type    TEXT NOT NULL DEFAULT 'kaybee'
);
CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);

CREATE TABLE IF NOT EXISTS _types (
    type_name TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS _links (
    source_name      TEXT NOT NULL,
    target_name      TEXT NOT NULL,
    target_resolved  TEXT,
    context          TEXT,
    PRIMARY KEY (source_name, target_name)
);
CREATE INDEX IF NOT EXISTS idx_links_target ON _links(target_resolved);
"""

_SCHEMA_SQL_MULTI = """
CREATE TABLE IF NOT EXISTS kaybee (
    name    TEXT PRIMARY KEY,
    content TEXT DEFAULT ''
);
"""

_SCHEMA_SQL_SINGLE = """
CREATE TABLE IF NOT EXISTS _data (
    name    TEXT PRIMARY KEY,
    content TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS _type_fields (
    type_name  TEXT NOT NULL,
    field_name TEXT NOT NULL,
    PRIMARY KEY (type_name, field_name)
);
"""

# user_version values: 0 or 1 = multi, 2 = single
_USER_VERSION_MULTI = 1
_USER_VERSION_SINGLE = 2


class KnowledgeGraph:
    """A flat SQLite-native knowledge graph.

    Nodes are identified by name (auto-slugified).  ``type`` is the sole
    grouping mechanism — no directories, no paths.
    """

    def __init__(self, db_path: str = ":memory:", *, mode: str = "multi", changelog: bool = True) -> None:
        if mode not in ("multi", "single"):
            raise ValueError(f"Invalid mode: '{mode}'. Must be 'multi' or 'single'.")
        self._mode = mode
        self._db = sqlite3.connect(db_path)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._validator = None
        self._changelog = changelog
        self._init_schema()

    def _init_schema(self) -> None:
        expected_version = _USER_VERSION_MULTI if self._mode == "multi" else _USER_VERSION_SINGLE
        current_version = self._db.execute("PRAGMA user_version").fetchone()[0]

        # Version 0 = fresh database (never stamped), accept any mode
        if current_version != 0:
            if current_version != expected_version:
                mode_label = "multi" if current_version == _USER_VERSION_MULTI else "single"
                raise ValueError(
                    f"Database was created with mode='{mode_label}' "
                    f"but opened with mode='{self._mode}'."
                )

        self._db.executescript(_SCHEMA_SQL_COMMON)
        if self._mode == "multi":
            self._db.executescript(_SCHEMA_SQL_MULTI)
        else:
            self._db.executescript(_SCHEMA_SQL_SINGLE)

        self._db.execute(f"PRAGMA user_version = {expected_version}")
        if self._changelog:
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS _changelog ("
                "seq INTEGER PRIMARY KEY AUTOINCREMENT, "
                "ts REAL NOT NULL, "
                "op TEXT NOT NULL, "
                "name TEXT NOT NULL, "
                "data TEXT)"
            )
        self._db.commit()

    def _log(self, op: str, name: str, data: dict | None = None) -> None:
        if not self._changelog:
            return
        self._db.execute(
            "INSERT INTO _changelog (ts, op, name, data) VALUES (?, ?, ?, ?)",
            (time.time(), op, name, json.dumps(data) if data else None),
        )

    # ------------------------------------------------------------------
    # Internal: type-table management
    # ------------------------------------------------------------------

    def data_table(self, type_name: str = "kaybee") -> str:
        """Return the SQL table name where *type_name*'s data lives.

        In single mode every type maps to ``_data``.
        In multi mode each type has its own table (sanitised via _safe_ident).

        Useful for callers that need to run raw SQL via ``query()``.
        """
        if self._mode == "single":
            return "_data"
        return _safe_ident(type_name)

    def _ensure_type_table(self, type_name: str, keys: list[str]) -> None:
        if type_name != "kaybee" and type_name in _RESERVED_TYPE_NAMES:
            raise ValueError(f"Reserved type name: '{type_name}'")
        if type_name == "kaybee" and _safe_ident(type_name) != "kaybee":
            raise ValueError(f"Reserved type name: '{type_name}'")

        table = self.data_table(type_name)

        if self._mode == "multi":
            self._db.execute(
                f"CREATE TABLE IF NOT EXISTS {table} (name TEXT PRIMARY KEY, content TEXT)"
            )

        existing = {
            row[1]
            for row in self._db.execute(f"PRAGMA table_info({table})").fetchall()
        }
        for key in keys:
            col = _safe_ident(key)
            if col not in existing:
                self._db.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
            if self._mode == "single" and type_name != "kaybee":
                self._db.execute(
                    "INSERT OR IGNORE INTO _type_fields (type_name, field_name) VALUES (?, ?)",
                    (type_name, col),
                )

    def _upsert_type_row(self, type_name: str, name: str, content: str, meta: dict) -> None:
        keys = [k for k in meta if k != "type"]
        self._ensure_type_table(type_name, keys)

        target_table = self.data_table(type_name)
        cols = ["name", "content"] + [_safe_ident(k) for k in keys]
        placeholders = ", ".join(["?"] * len(cols))
        col_str = ", ".join(cols)
        vals = [name, content] + [json.dumps(v) if isinstance(v, (list, dict)) else str(v) for v in (meta[k] for k in keys)]

        self._db.execute(
            f"INSERT OR REPLACE INTO {target_table} ({col_str}) VALUES ({placeholders})",
            vals,
        )

    def _delete_data_row(self, type_name: str, name: str) -> None:
        table = self.data_table(type_name)
        try:
            self._db.execute(f"DELETE FROM {table} WHERE name = ?", (name,))
        except sqlite3.OperationalError:
            pass

    def _content_rows(self, type_name: str | None = None) -> list[tuple[str, str]]:
        """Return ``(name, content)`` pairs, optionally filtered by type.

        Single centralised content scanner used by ``grep`` and ``tags``.
        """
        if type_name is not None:
            table = self.data_table(type_name)
            if self._mode == "single":
                return self._db.execute(
                    f"SELECT d.name, d.content FROM {table} d "
                    "JOIN nodes n ON n.name = d.name "
                    "WHERE n.type = ? ORDER BY d.name",
                    (type_name,),
                ).fetchall()
            try:
                return self._db.execute(
                    f"SELECT name, content FROM {table} ORDER BY name"
                ).fetchall()
            except sqlite3.OperationalError:
                return []

        # All types
        if self._mode == "single":
            return self._db.execute("SELECT name, content FROM _data").fetchall()

        type_rows = self._db.execute(
            "SELECT DISTINCT type FROM nodes"
        ).fetchall()
        if not type_rows:
            return []
        parts: list[str] = []
        for (t,) in type_rows:
            safe = _safe_ident(t)
            try:
                self._db.execute(f"SELECT 1 FROM {safe} LIMIT 0")
                parts.append(f"SELECT name, content FROM {safe}")
            except sqlite3.OperationalError:
                continue
        if not parts:
            return []
        return self._db.execute(" UNION ALL ".join(parts)).fetchall()

    def _read_node_data(self, name: str) -> tuple[str, dict]:
        """Read content and meta from the node's type table.

        Returns ``(content, meta_dict)`` where meta_dict includes ``type``
        for typed nodes (not kaybee).
        """
        row = self._db.execute(
            "SELECT type FROM nodes WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            raise KeyError(name)
        type_name = row[0]

        source_table = self.data_table(type_name)

        try:
            data_row = self._db.execute(
                f"SELECT * FROM {source_table} WHERE name = ?", (name,)
            ).fetchone()
        except sqlite3.OperationalError:
            return ("", {"type": type_name} if type_name != "kaybee" else {})

        if data_row is None:
            return ("", {"type": type_name} if type_name != "kaybee" else {})

        col_names = [
            desc[1] for desc in self._db.execute(f"PRAGMA table_info({source_table})").fetchall()
        ]

        # In single mode, filter to only columns relevant to this type
        if self._mode == "single" and type_name != "kaybee":
            type_fields = {
                r[0] for r in self._db.execute(
                    "SELECT field_name FROM _type_fields WHERE type_name = ?",
                    (type_name,),
                ).fetchall()
            }
        else:
            type_fields = None

        content = ""
        meta: dict[str, Any] = {}
        for col, val in zip(col_names, data_row):
            if col == "name":
                continue
            if col == "content":
                content = val or ""
                continue
            if val is None:
                continue
            # In single mode, skip columns not belonging to this type
            if type_fields is not None and col not in type_fields:
                continue
            # Try to parse JSON-encoded values (lists/dicts)
            parsed = val
            if isinstance(val, str):
                try:
                    candidate = json.loads(val)
                    if isinstance(candidate, (list, dict)):
                        parsed = candidate
                except (json.JSONDecodeError, ValueError):
                    pass
            meta[col] = parsed

        if type_name != "kaybee":
            meta["type"] = type_name

        return (content, meta)

    @staticmethod
    def _display_type(type_name: str) -> str | None:
        """Return None if 'kaybee', else the type name."""
        return None if type_name == "kaybee" else type_name


    # ------------------------------------------------------------------
    # Validator integration
    # ------------------------------------------------------------------

    def set_validator(self, validator: Any) -> "KnowledgeGraph":
        """Attach a Validator for pre-write gatekeeper checks."""
        self._validator = validator
        return self

    def clear_validator(self) -> "KnowledgeGraph":
        """Remove the attached Validator (restore freeform mode)."""
        self._validator = None
        return self

    # ------------------------------------------------------------------
    # Internal: link management
    # ------------------------------------------------------------------

    def _sync_links(self, name: str, body: str) -> None:
        self._db.execute("DELETE FROM _links WHERE source_name = ?", (name,))
        targets = extract_wikilinks(body)
        for target in targets:
            resolved = self.resolve_wikilink(target, fuzzy=True)
            ctx = ""
            for line in body.splitlines():
                if f"[[{target}]]" in line:
                    ctx = line.strip()
                    break
            self._db.execute(
                "INSERT OR REPLACE INTO _links (source_name, target_name, target_resolved, context) VALUES (?, ?, ?, ?)",
                (name, target, resolved, ctx),
            )

    def _re_resolve_links_to(self, name: str) -> None:
        slug = slugify(name)
        rows = self._db.execute(
            "SELECT source_name, target_name FROM _links WHERE target_resolved IS NULL OR target_resolved = ?",
            (name,),
        ).fetchall()
        for source_name, target_name in rows:
            resolved = self.resolve_wikilink(target_name, fuzzy=True)
            self._db.execute(
                "UPDATE _links SET target_resolved = ? WHERE source_name = ? AND target_name = ?",
                (resolved, source_name, target_name),
            )

    # ------------------------------------------------------------------
    # Internal: node write helper
    # ------------------------------------------------------------------

    def _write_node(self, name: str, content: str) -> None:
        meta, body = parse_frontmatter(content)
        effective_type = meta.get("type") or "kaybee"

        # Pre-write validator check (structural rules only)
        if self._validator is not None:
            from .constraints import ValidationError
            violations = self._validator.validate_structural(name, meta)
            if violations:
                raise ValidationError(violations)

        old = self._db.execute("SELECT type FROM nodes WHERE name = ?", (name,)).fetchone()
        old_type = old[0] if old else None

        # Handle type change: delete from old type table
        if old_type and old_type != effective_type:
            self._delete_data_row(old_type, name)

        # Thin index: name + type only
        self._db.execute(
            "INSERT OR REPLACE INTO nodes (name, type) VALUES (?, ?)",
            (name, effective_type),
        )

        # Store data in type table (works for both kaybee and typed tables)
        self._upsert_type_row(effective_type, name, body, meta)

        # Auto-register typed nodes in _types (not kaybee)
        if effective_type != "kaybee":
            self._db.execute("INSERT OR IGNORE INTO _types (type_name) VALUES (?)", (effective_type,))

        self._sync_links(name, body)
        self._re_resolve_links_to(name)
        self._log("node.write", name, {"type": effective_type, "content": body, "meta": meta})
        self._db.commit()

    # ------------------------------------------------------------------
    # Type management
    # ------------------------------------------------------------------

    def add_type(self, type_name: str) -> "KnowledgeGraph":
        """Register a type (idempotent)."""
        self._db.execute("INSERT OR IGNORE INTO _types (type_name) VALUES (?)", (type_name,))
        self._log("type.add", type_name)
        self._db.commit()
        return self

    def remove_type(self, type_name: str) -> "KnowledgeGraph":
        """Unregister a type.  Fails if nodes of this type exist."""
        count = self._db.execute(
            "SELECT COUNT(*) FROM nodes WHERE type = ?", (type_name,)
        ).fetchone()[0]
        if count > 0:
            raise ValueError(f"Cannot remove type '{type_name}': {count} node(s) still exist")
        self._db.execute("DELETE FROM _types WHERE type_name = ?", (type_name,))
        self._log("type.rm", type_name)
        self._db.commit()
        return self

    def types(self) -> list[str]:
        """Return sorted list of registered types."""
        rows = self._db.execute("SELECT type_name FROM _types ORDER BY type_name").fetchall()
        return [r[0] for r in rows]

    # ------------------------------------------------------------------
    # Changelog
    # ------------------------------------------------------------------

    def changelog(self, since_seq: int = 0, limit: int = 100) -> list[tuple]:
        """Read changelog entries as (seq, ts, op, name, data) tuples.

        Returns entries with seq > since_seq, up to *limit* rows.
        """
        if not self._changelog:
            return []
        rows = self._db.execute(
            "SELECT seq, ts, op, name, data FROM _changelog "
            "WHERE seq > ? ORDER BY seq LIMIT ?",
            (since_seq, limit),
        ).fetchall()
        return rows

    def changelog_truncate(self, before_seq: int) -> int:
        """Delete changelog entries with seq < before_seq. Returns rows deleted."""
        if not self._changelog:
            return 0
        cur = self._db.execute(
            "DELETE FROM _changelog WHERE seq < ?", (before_seq,)
        )
        self._db.commit()
        return cur.rowcount

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def touch(self, name: str, content: str = "") -> "KnowledgeGraph":
        name = slugify(name)
        if self.exists(name):
            if content:
                return self.write(name, content)
            return self

        if content:
            self._write_node(name, content)
        else:
            self._db.execute(
                "INSERT OR IGNORE INTO nodes (name, type) VALUES (?, 'kaybee')",
                (name,),
            )
            self._upsert_type_row("kaybee", name, "", {})
            self._log("node.write", name, {"type": "kaybee", "content": "", "meta": {}})
            self._db.commit()
        return self

    def write(self, name: str, content: str) -> "KnowledgeGraph":
        name = slugify(name)
        self._write_node(name, content)
        return self

    def cat(self, name: str) -> str:
        content, meta = self._read_node_data(name)
        if meta:
            return self._reconstruct(meta, content)
        return content

    @staticmethod
    def _reconstruct(meta: dict, body: str) -> str:
        if not meta:
            return body
        lines = ["---"]
        for key, val in meta.items():
            if isinstance(val, list):
                lines.append(f"{key}: [{', '.join(str(v) for v in val)}]")
            elif isinstance(val, dict):
                lines.append(f"{key}:")
                for sk, sv in val.items():
                    lines.append(f"  {sk}: {sv}")
            else:
                lines.append(f"{key}: {val}")
        lines.append("---")
        if body:
            lines.append(body)
        return "\n".join(lines)

    def exists(self, name: str) -> bool:
        row = self._db.execute("SELECT 1 FROM nodes WHERE name = ?", (name,)).fetchone()
        return row is not None

    def rm(self, name: str) -> "KnowledgeGraph":
        if not self.exists(name):
            raise KeyError(name)

        row = self._db.execute("SELECT type FROM nodes WHERE name = ?", (name,)).fetchone()
        if row and row[0]:
            self._delete_data_row(row[0], name)

        type_name = row[0] if row else "kaybee"
        self._db.execute("DELETE FROM _links WHERE source_name = ?", (name,))
        self._db.execute(
            "UPDATE _links SET target_resolved = NULL WHERE target_resolved = ?", (name,)
        )
        self._db.execute("DELETE FROM nodes WHERE name = ?", (name,))
        self._log("node.rm", name, {"type": type_name})
        self._db.commit()
        return self

    def mv(self, old_name: str, new_name: str) -> "KnowledgeGraph":
        if not self.exists(old_name):
            raise KeyError(old_name)

        new_name = slugify(new_name)
        if old_name == new_name:
            return self

        if self.exists(new_name):
            raise FileExistsError(f"Node already exists: {new_name}")

        content, meta = self._read_node_data(old_name)
        type_name = meta.get("type", "kaybee")

        self._delete_data_row(type_name, old_name)
        self._db.execute("DELETE FROM nodes WHERE name = ?", (old_name,))

        # Insert new into index and type table
        self._db.execute(
            "INSERT INTO nodes (name, type) VALUES (?, ?)",
            (new_name, type_name),
        )
        # meta from _read_node_data includes 'type' for typed nodes; pass as-is
        self._upsert_type_row(type_name, new_name, content, meta)

        # Update links
        self._db.execute(
            "UPDATE _links SET source_name = ? WHERE source_name = ?", (new_name, old_name)
        )
        self._db.execute(
            "UPDATE _links SET target_resolved = ? WHERE target_resolved = ?", (new_name, old_name)
        )

        self._log("node.mv", new_name, {"old_name": old_name, "type": type_name, "content": content, "meta": meta})
        self._db.commit()
        return self

    def cp(self, src: str, dst: str) -> "KnowledgeGraph":
        if not self.exists(src):
            raise KeyError(src)

        dst = slugify(dst)
        if src == dst:
            raise ValueError(f"Cannot copy to self: {src}")

        if self.exists(dst):
            raise FileExistsError(f"Node already exists: {dst}")

        content, meta = self._read_node_data(src)
        type_name = meta.get("type", "kaybee")

        self._db.execute(
            "INSERT INTO nodes (name, type) VALUES (?, ?)",
            (dst, type_name),
        )
        self._upsert_type_row(type_name, dst, content, meta)

        self._sync_links(dst, content)
        self._log("node.cp", dst, {"source": src, "type": type_name, "content": content, "meta": meta})
        self._db.commit()
        return self

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def ls(self, type_name: str | None = None) -> list[str]:
        """List types or nodes.

        - ``ls()`` → registered types
        - ``ls("concept")`` → node names of that type
        - ``ls("*")`` → all node names
        """
        if type_name is None:
            return self.types()
        if type_name == "*":
            rows = self._db.execute("SELECT name FROM nodes ORDER BY name").fetchall()
            return [r[0] for r in rows]
        rows = self._db.execute(
            "SELECT name FROM nodes WHERE type = ? ORDER BY name", (type_name,)
        ).fetchall()
        return [r[0] for r in rows]

    def tree(self) -> str:
        """Type-grouped tree view."""
        lines: list[str] = []
        typed_names: set[str] = set()

        for t in self.types():
            names = self.ls(t)
            if not names:
                lines.append(f"{t}/")
                continue
            lines.append(f"{t}/")
            for idx, name in enumerate(names):
                typed_names.add(name)
                is_last = idx == len(names) - 1
                connector = "\u2514\u2500\u2500 " if is_last else "\u251c\u2500\u2500 "
                try:
                    content, _ = self._read_node_data(name)
                except KeyError:
                    content = ""
                if content:
                    preview = content[:50] + ("..." if len(content) > 50 else "")
                    lines.append(f"{connector}{name}: {preview}")
                else:
                    lines.append(f"{connector}{name}")

        # Untyped nodes (kaybee type)
        untyped_rows = self._db.execute(
            f"SELECT k.name, k.content FROM {self.data_table()} k "
            "JOIN nodes n ON n.name = k.name "
            "WHERE n.type = 'kaybee' ORDER BY k.name"
        ).fetchall()
        if untyped_rows:
            lines.append("(untyped)")
            for idx, (name, content) in enumerate(untyped_rows):
                is_last = idx == len(untyped_rows) - 1
                connector = "\u2514\u2500\u2500 " if is_last else "\u251c\u2500\u2500 "
                if content:
                    preview = content[:50] + ("..." if len(content) > 50 else "")
                    lines.append(f"{connector}{name}: {preview}")
                else:
                    lines.append(f"{connector}{name}")

        return "\n".join(lines)

    def find(self, name: str | None = None, type: str | None = None) -> list[str]:
        """Find nodes by name pattern and/or type."""
        conditions: list[str] = []
        params: list[Any] = []

        if name:
            self._db.create_function("REGEXP", 2, _regexp)
            conditions.append("name REGEXP ?")
            params.append(name)

        if type:
            conditions.append("type = ?")
            params.append(type)

        where = " AND ".join(conditions) if conditions else "1"
        query = f"SELECT name FROM nodes WHERE {where} ORDER BY name"
        rows = self._db.execute(query, params).fetchall()
        return [r[0] for r in rows]

    def grep(
        self,
        pattern: str,
        type: str | None = None,
        content: bool = False,
        ignore_case: bool = True,
        invert: bool = False,
        count: bool = False,
        lines: bool = False,
    ) -> list[str] | int:
        flags = re.IGNORECASE if ignore_case else 0
        regex = re.compile(pattern, flags)
        rows = self._content_rows(type)

        results: list[str] = []

        if lines:
            for rname, rcontent in rows:
                if rcontent:
                    for lineno, line in enumerate(rcontent.splitlines(), 1):
                        matched = bool(regex.search(line))
                        if invert:
                            matched = not matched
                        if matched:
                            results.append(f"{rname}:{lineno}:{line}")
            return results

        for rname, rcontent in rows:
            matches = bool(regex.search(rname))
            if not matches and content and rcontent:
                matches = bool(regex.search(rcontent))
            if invert:
                matches = not matches
            if matches:
                results.append(rname)

        return len(results) if count else results

    def info(self, name: str) -> dict:
        content, meta = self._read_node_data(name)
        type_row = self._db.execute(
            "SELECT type FROM nodes WHERE name = ?", (name,)
        ).fetchone()
        type_name = self._display_type(type_row[0])
        tags = meta.get("tags", [])

        return {
            "name": name,
            "type": type_name,
            "meta": meta,
            "tags": tags if isinstance(tags, list) else [],
            "content_length": len(content) if content else 0,
            "has_content": bool(content),
        }

    # ------------------------------------------------------------------
    # Graph API
    # ------------------------------------------------------------------

    def frontmatter(self, name: str) -> dict:
        _, meta = self._read_node_data(name)
        return meta

    def body(self, name: str) -> str:
        content, _ = self._read_node_data(name)
        return content

    def wikilinks(self, name: str) -> list[str]:
        rows = self._db.execute(
            "SELECT target_name FROM _links WHERE source_name = ?", (name,)
        ).fetchall()
        return [r[0] for r in rows]

    def links(self, name: str) -> list[tuple[str, str | None]]:
        """Return outgoing wikilinks with their resolved node (if any)."""
        rows = self._db.execute(
            "SELECT target_name, target_resolved FROM _links WHERE source_name = ?",
            (name,),
        ).fetchall()
        return [(target, resolved) for target, resolved in rows]

    def resolve_wikilink(self, name: str, fuzzy: bool = True) -> str | None:
        """Resolve a wikilink name to a node name.

        Exact match first, then fuzzy via slugify.
        """
        row = self._db.execute(
            "SELECT name FROM nodes WHERE name = ?", (name,)
        ).fetchone()
        if row:
            return row[0]

        if not fuzzy:
            return None

        target_slug = slugify(name)
        rows = self._db.execute("SELECT name FROM nodes").fetchall()
        for (rname,) in rows:
            if slugify(rname) == target_slug:
                return rname
        return None

    def backlinks(self, name: str) -> list[str]:
        rows = self._db.execute(
            "SELECT source_name FROM _links WHERE target_resolved = ?", (name,)
        ).fetchall()
        return [r[0] for r in rows]

    def read(self, name: str, depth: int = 0) -> str:
        """Read a node with progressive disclosure of linked content.

        - ``depth=0``: same as ``cat(name)``
        - ``depth=1``: main content + content of direct wikilink targets
        - ``depth=N``: recursive to N levels

        Cycles are handled via a visited set. Linked nodes are sorted
        alphabetically for deterministic output.
        """
        if depth <= 0:
            return self.cat(name)

        visited: set[str] = set()
        sections: list[str] = []
        self._read_recursive(name, depth, visited, sections, is_root=True)
        return "\n".join(sections)

    def _read_recursive(
        self,
        name: str,
        depth: int,
        visited: set[str],
        sections: list[str],
        is_root: bool = False,
    ) -> None:
        if name in visited:
            return
        visited.add(name)

        content = self.cat(name)
        if is_root:
            sections.append(content)
        else:
            sections.append(f"--- [[{name}]] ---")
            sections.append(content)

        if depth <= 0:
            return

        # Get resolved link targets from _links table
        rows = self._db.execute(
            "SELECT target_resolved FROM _links WHERE source_name = ? AND target_resolved IS NOT NULL",
            (name,),
        ).fetchall()
        targets = sorted(set(r[0] for r in rows))

        for target in targets:
            if target not in visited and self.exists(target):
                self._read_recursive(target, depth - 1, visited, sections)

    def find_by_type(self, type_name: str) -> list[str]:
        rows = self._db.execute(
            "SELECT name FROM nodes WHERE type = ? ORDER BY name", (type_name,)
        ).fetchall()
        return [r[0] for r in rows]

    def tags(self, name: str | None = None) -> list[str] | dict[str, list[str]]:
        """Get tags for a node, or a tag->names mapping for all nodes.

        - ``tags("x")`` -> list of tags on node x
        - ``tags()`` -> ``{tag: [name, ...]}``
        """
        if name is not None:
            meta = self.frontmatter(name)
            t = meta.get("tags", [])
            return t if isinstance(t, list) else []

        tag_map: dict[str, list[str]] = {}
        tables = (
            [self.data_table()]
            if self._mode == "single"
            else [_safe_ident(t) for (t,) in self._db.execute("SELECT DISTINCT type FROM nodes").fetchall()]
        )
        for table in tables:
            try:
                cols = {r[1] for r in self._db.execute(f"PRAGMA table_info({table})").fetchall()}
            except sqlite3.OperationalError:
                continue
            if "tags" not in cols:
                continue
            for rname, tags_val in self._db.execute(
                f"SELECT name, tags FROM {table} WHERE tags IS NOT NULL"
            ).fetchall():
                try:
                    node_tags = json.loads(tags_val)
                except (json.JSONDecodeError, ValueError):
                    continue
                if isinstance(node_tags, list):
                    for tag in node_tags:
                        tag_map.setdefault(tag, []).append(rname)
        return tag_map

    def schema(self) -> dict[str, list[str]]:
        types = self._db.execute(
            "SELECT DISTINCT type FROM nodes WHERE type != 'kaybee' ORDER BY type"
        ).fetchall()
        result: dict[str, list[str]] = {}

        if self._mode == "single":
            for (t,) in types:
                fields = self._db.execute(
                    "SELECT field_name FROM _type_fields WHERE type_name = ? ORDER BY field_name",
                    (t,),
                ).fetchall()
                result[t] = [r[0] for r in fields]
            return result

        for (t,) in types:
            safe = _safe_ident(t)
            try:
                cols = self._db.execute(f"PRAGMA table_info({safe})").fetchall()
                keys = [c[1] for c in cols if c[1] not in ("name", "content")]
                result[t] = keys
            except sqlite3.OperationalError:
                result[t] = []
        return result

    def graph(self) -> dict[str, list[str]]:
        rows = self._db.execute(
            "SELECT source_name, target_resolved FROM _links WHERE target_resolved IS NOT NULL"
        ).fetchall()
        adj: dict[str, list[str]] = {}
        for src, tgt in rows:
            adj.setdefault(src, []).append(tgt)
        return adj

    @property
    def changelog_enabled(self) -> bool:
        """Whether changelog recording is active."""
        return self._changelog

    def commit(self) -> None:
        """Commit pending database changes."""
        self._db.commit()

    def query(self, sql: str, params: tuple = ()) -> list[tuple]:
        return self._db.execute(sql, params).fetchall()

    # ------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_ident(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)


def _regexp(pattern: str, string: str) -> bool:
    if string is None:
        return False
    return bool(re.search(pattern, string, re.IGNORECASE))
