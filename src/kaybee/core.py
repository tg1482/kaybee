"""SQLite-native knowledge graph with YAML frontmatter and wikilink support.

Flat architecture — nodes are identified by name (auto-slugified), grouped by
``type``.  No directories, no paths, no hierarchy.
"""

from __future__ import annotations

import json
import re
import sqlite3
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

_RESERVED_TYPE_NAMES = frozenset({"nodes", "_types", "_links"})

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS nodes (
    name    TEXT PRIMARY KEY,
    type    TEXT NOT NULL DEFAULT 'kaybee'
);
CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);

CREATE TABLE IF NOT EXISTS kaybee (
    name    TEXT PRIMARY KEY,
    content TEXT DEFAULT ''
);

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


class KnowledgeGraph:
    """A flat SQLite-native knowledge graph.

    Nodes are identified by name (auto-slugified).  ``type`` is the sole
    grouping mechanism — no directories, no paths.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db = sqlite3.connect(db_path)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._validator = None
        self._init_schema()

    def _init_schema(self) -> None:
        self._db.executescript(_SCHEMA_SQL)
        self._db.commit()

    # ------------------------------------------------------------------
    # Internal: type-table management
    # ------------------------------------------------------------------

    def _ensure_type_table(self, type_name: str, keys: list[str]) -> None:
        safe = _safe_ident(type_name)
        if type_name != "kaybee" and type_name in _RESERVED_TYPE_NAMES:
            raise ValueError(f"Reserved type name: '{type_name}'")
        if type_name == "kaybee" and safe != "kaybee":
            raise ValueError(f"Reserved type name: '{type_name}'")
        self._db.execute(
            f"CREATE TABLE IF NOT EXISTS {safe} (name TEXT PRIMARY KEY, content TEXT)"
        )
        existing = {
            row[1]
            for row in self._db.execute(f"PRAGMA table_info({safe})").fetchall()
        }
        for key in keys:
            col = _safe_ident(key)
            if col not in existing:
                self._db.execute(f"ALTER TABLE {safe} ADD COLUMN {col} TEXT")

    def _upsert_type_row(self, type_name: str, name: str, content: str, meta: dict) -> None:
        safe = _safe_ident(type_name)
        keys = [k for k in meta if k != "type"]
        self._ensure_type_table(type_name, keys)

        cols = ["name", "content"] + [_safe_ident(k) for k in keys]
        placeholders = ", ".join(["?"] * len(cols))
        col_str = ", ".join(cols)
        vals = [name, content] + [json.dumps(v) if isinstance(v, (list, dict)) else str(v) for v in (meta[k] for k in keys)]

        self._db.execute(
            f"INSERT OR REPLACE INTO {safe} ({col_str}) VALUES ({placeholders})",
            vals,
        )

    def _delete_type_row(self, type_name: str, name: str) -> None:
        safe = _safe_ident(type_name)
        try:
            self._db.execute(f"DELETE FROM {safe} WHERE name = ?", (name,))
        except sqlite3.OperationalError:
            pass

    def _delete_from_type_table(self, type_name: str, name: str) -> None:
        if type_name == "kaybee":
            try:
                self._db.execute("DELETE FROM kaybee WHERE name = ?", (name,))
            except sqlite3.OperationalError:
                pass
        else:
            self._delete_type_row(type_name, name)

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
        safe = _safe_ident(type_name)

        try:
            data_row = self._db.execute(
                f"SELECT * FROM {safe} WHERE name = ?", (name,)
            ).fetchone()
        except sqlite3.OperationalError:
            return ("", {"type": type_name} if type_name != "kaybee" else {})

        if data_row is None:
            return ("", {"type": type_name} if type_name != "kaybee" else {})

        col_names = [
            desc[1] for desc in self._db.execute(f"PRAGMA table_info({safe})").fetchall()
        ]
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

    def _grep_all_content(self) -> list[tuple[str, str]]:
        """Return (name, content) pairs across all type tables."""
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
        union_sql = " UNION ALL ".join(parts)
        return self._db.execute(union_sql).fetchall()

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
            self._delete_from_type_table(old_type, name)

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
        self._db.commit()

    # ------------------------------------------------------------------
    # Type management
    # ------------------------------------------------------------------

    def add_type(self, type_name: str) -> "KnowledgeGraph":
        """Register a type (idempotent)."""
        self._db.execute("INSERT OR IGNORE INTO _types (type_name) VALUES (?)", (type_name,))
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
        self._db.commit()
        return self

    def types(self) -> list[str]:
        """Return sorted list of registered types."""
        rows = self._db.execute("SELECT type_name FROM _types ORDER BY type_name").fetchall()
        return [r[0] for r in rows]

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
            self._db.execute(
                "INSERT OR IGNORE INTO kaybee (name, content) VALUES (?, '')",
                (name,),
            )
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
            self._delete_from_type_table(row[0], name)

        self._db.execute("DELETE FROM _links WHERE source_name = ?", (name,))
        self._db.execute(
            "UPDATE _links SET target_resolved = NULL WHERE target_resolved = ?", (name,)
        )
        self._db.execute("DELETE FROM nodes WHERE name = ?", (name,))
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

        # Read data from type table
        content, meta = self._read_node_data(old_name)
        type_row = self._db.execute(
            "SELECT type FROM nodes WHERE name = ?", (old_name,)
        ).fetchone()
        type_name = type_row[0]

        # Delete old from type table and index
        self._delete_from_type_table(type_name, old_name)
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
        type_row = self._db.execute(
            "SELECT type FROM nodes WHERE name = ?", (src,)
        ).fetchone()
        type_name = type_row[0]

        self._db.execute(
            "INSERT INTO nodes (name, type) VALUES (?, ?)",
            (dst, type_name),
        )
        self._upsert_type_row(type_name, dst, content, meta)

        self._sync_links(dst, content)
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
            "SELECT k.name, k.content FROM kaybee k "
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

        if type:
            # Single type: query that type table directly
            safe = _safe_ident(type)
            try:
                rows = self._db.execute(
                    f"SELECT name, content FROM {safe} ORDER BY name"
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
        else:
            # All types: union across all type tables
            rows = self._grep_all_content()

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
    # Operations
    # ------------------------------------------------------------------

    def ln(self, source: str, dest: str) -> "KnowledgeGraph":
        dest = slugify(dest)
        if self.exists(dest):
            raise FileExistsError(f"Node already exists: {dest}")

        # Insert into thin index
        self._db.execute(
            "INSERT INTO nodes (name, type) VALUES (?, 'kaybee')",
            (dest,),
        )
        # Store link_target as a real column on kaybee table
        self._ensure_type_table("kaybee", ["link_target"])
        self._upsert_type_row("kaybee", dest, "", {"link_target": source})
        self._db.commit()
        return self

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
        results: list[str] = []

        rows = self._db.execute(
            "SELECT source_name FROM _links WHERE target_resolved = ?", (name,)
        ).fetchall()
        results.extend(r[0] for r in rows)

        # Check if kaybee table has link_target column
        try:
            cols = {
                row[1]
                for row in self._db.execute("PRAGMA table_info(kaybee)").fetchall()
            }
            if "link_target" in cols:
                sym_rows = self._db.execute(
                    "SELECT name FROM kaybee WHERE link_target = ?",
                    (name,),
                ).fetchall()
                results.extend(r[0] for r in sym_rows if r[0] not in results)
        except sqlite3.OperationalError:
            pass

        return results

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

        # Scan type tables that have a 'tags' column
        tag_map: dict[str, list[str]] = {}
        type_rows = self._db.execute(
            "SELECT DISTINCT type FROM nodes"
        ).fetchall()
        for (t,) in type_rows:
            safe = _safe_ident(t)
            try:
                cols = {
                    row[1]
                    for row in self._db.execute(f"PRAGMA table_info({safe})").fetchall()
                }
            except sqlite3.OperationalError:
                continue
            if "tags" not in cols:
                continue
            try:
                rows = self._db.execute(
                    f"SELECT name, tags FROM {safe} WHERE tags IS NOT NULL"
                ).fetchall()
            except sqlite3.OperationalError:
                continue
            for rname, tags_val in rows:
                if tags_val is None:
                    continue
                # Parse JSON-encoded tag list
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

    def query(self, sql: str, params: tuple = ()) -> list[tuple]:
        return self._db.execute(sql, params).fetchall()

    # ------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Shell command registration
# ---------------------------------------------------------------------------

def _cmd_ls(args: list[str], _stdin: str, tree: Any) -> str:
    if not args:
        return "\n".join(tree.ls())
    return "\n".join(tree.ls(args[0]))


def _cmd_cat(args: list[str], stdin: str, tree: Any) -> str:
    if not args:
        return stdin
    if len(args) == 1:
        return tree.cat(args[0])
    return "\n".join(tree.cat(a) for a in args)


def _cmd_touch(args: list[str], stdin: str, tree: Any) -> str:
    if len(args) < 1:
        raise ValueError("touch requires a name")
    name = args[0]
    content = " ".join(args[1:]) if len(args) > 1 else stdin
    tree.touch(name, content)
    return ""


def _cmd_write(args: list[str], stdin: str, tree: Any) -> str:
    if len(args) < 1:
        raise ValueError("write requires a name")
    name = args[0]
    content = " ".join(args[1:]) if len(args) > 1 else stdin
    tree.write(name, content)
    return ""


def _cmd_rm(args: list[str], _stdin: str, tree: Any) -> str:
    if not args:
        raise ValueError("rm requires a name")
    tree.rm(args[0])
    return ""


def _cmd_mv(args: list[str], _stdin: str, tree: Any) -> str:
    if len(args) != 2:
        raise ValueError("mv requires old_name and new_name")
    tree.mv(args[0], args[1])
    return ""


def _cmd_cp(args: list[str], _stdin: str, tree: Any) -> str:
    if len(args) != 2:
        raise ValueError("cp requires source and destination")
    tree.cp(args[0], args[1])
    return ""


def _cmd_ln(args: list[str], _stdin: str, tree: Any) -> str:
    if len(args) != 2:
        raise ValueError("ln requires source and dest")
    tree.ln(args[0], args[1])
    return ""


def _cmd_tree(_args: list[str], _stdin: str, tree: Any) -> str:
    return tree.tree()


def _cmd_find(args: list[str], _stdin: str, tree: Any) -> str:
    name = None
    type_ = None

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "-name":
            if i + 1 >= len(args):
                raise ValueError("find -name requires a pattern")
            name = args[i + 1]
            i += 2
            continue
        if arg == "-type":
            if i + 1 >= len(args):
                raise ValueError("find -type requires a type name")
            type_ = args[i + 1]
            i += 2
            continue
        if arg.startswith("-"):
            raise ValueError(f"unknown find option: {arg}")
        i += 1

    return "\n".join(tree.find(name=name, type=type_))


def _cmd_grep(args: list[str], stdin: str, tree: Any) -> str:
    ignore_case = False
    invert = False
    count = False
    line_mode = False
    pattern: str | None = None
    type_filter: str | None = None
    flags_done = False

    i = 0
    while i < len(args):
        arg = args[i]

        if not flags_done:
            if arg == "--":
                flags_done = True
                i += 1
                continue
            if arg == "-t" or arg == "--type":
                if i + 1 >= len(args):
                    raise ValueError("grep -t requires a type name")
                type_filter = args[i + 1]
                i += 2
                continue
            if arg.startswith("-") and arg != "-":
                for flag in arg[1:]:
                    if flag == "i":
                        ignore_case = True
                    elif flag == "v":
                        invert = True
                    elif flag == "c":
                        count = True
                    elif flag == "n":
                        line_mode = True
                    else:
                        raise ValueError(f"unknown grep flag: -{flag}")
                i += 1
                continue

        if pattern is None:
            pattern = arg
        i += 1

    if pattern is None:
        if stdin:
            return stdin
        raise ValueError("grep requires a pattern")

    if stdin and type_filter is None:
        flags = re.IGNORECASE if ignore_case else 0
        regex = re.compile(pattern, flags)
        matched_lines = stdin.splitlines()
        if line_mode:
            result_lines = []
            for lineno, line in enumerate(matched_lines, 1):
                if bool(regex.search(line)) != invert:
                    result_lines.append(f"{lineno}:{line}")
            return "\n".join(result_lines)
        matched = [line for line in matched_lines if bool(regex.search(line)) != invert]
        if count:
            return str(len(matched))
        return "\n".join(matched)

    if line_mode:
        results = tree.grep(
            pattern,
            type=type_filter,
            ignore_case=ignore_case,
            invert=invert,
            lines=True,
        )
        return "\n".join(results)

    results = tree.grep(
        pattern,
        type=type_filter,
        content=True,
        ignore_case=ignore_case,
        invert=invert,
        count=count,
    )

    if count:
        return str(results)
    if isinstance(results, int):
        return str(results)
    return "\n".join(results)


def _cmd_info(args: list[str], _stdin: str, tree: Any) -> str:
    if not args:
        raise ValueError("info requires a name")
    info = tree.info(args[0])
    return "\n".join(f"{key}: {value}" for key, value in info.items())


def _cmd_sed(args: list[str], _stdin: str, tree: Any) -> str:
    ignore_case = False
    count = 0
    positional = []

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "-i":
            ignore_case = True
        elif arg == "-c" and i + 1 < len(args):
            count = int(args[i + 1])
            i += 1
        elif arg.startswith("-"):
            raise ValueError(f"unknown sed option: {arg}")
        else:
            positional.append(arg)
        i += 1

    if len(positional) != 3:
        raise ValueError("sed requires: name pattern replacement")

    name, pattern, replacement = positional
    content = tree.cat(name)
    flags = re.IGNORECASE if ignore_case else 0
    new_content = re.sub(pattern, replacement, content, count=count, flags=flags)
    tree.write(name, new_content)
    return ""


def _cmd_meta(args: list[str], _stdin: str, tree: Any) -> str:
    if not args:
        raise ValueError("meta requires a name")
    meta = tree.frontmatter(args[0])
    return "\n".join(f"{k}: {v}" for k, v in meta.items())


def _cmd_body(args: list[str], _stdin: str, tree: Any) -> str:
    if not args:
        raise ValueError("body requires a name")
    return tree.body(args[0])


def _cmd_links(args: list[str], _stdin: str, tree: Any) -> str:
    if not args:
        raise ValueError("links requires a name")
    name = args[0]
    rows = tree._db.execute(
        "SELECT target_name, target_resolved FROM _links WHERE source_name = ?", (name,)
    ).fetchall()
    out_lines = []
    for target, resolved in rows:
        if resolved:
            out_lines.append(f"[[{target}]] -> {resolved}")
        else:
            out_lines.append(f"[[{target}]] -> (unresolved)")
    return "\n".join(out_lines)


def _cmd_backlinks(args: list[str], _stdin: str, tree: Any) -> str:
    if not args:
        raise ValueError("backlinks requires a name")
    results = tree.backlinks(args[0])
    return "\n".join(results)


def _cmd_resolve(args: list[str], _stdin: str, tree: Any) -> str:
    if not args:
        raise ValueError("resolve requires a name")
    exact = "--exact" in args
    name = args[0]
    result = tree.resolve_wikilink(name, fuzzy=not exact)
    if result is None:
        raise KeyError(f"Cannot resolve: {name}")
    return result


def _cmd_schema(_args: list[str], _stdin: str, tree: Any) -> str:
    s = tree.schema()
    out_lines = []
    for type_name, keys in sorted(s.items()):
        out_lines.append(f"{type_name}: {', '.join(keys) if keys else '(no fields)'}")
    return "\n".join(out_lines)


def _cmd_query(args: list[str], _stdin: str, tree: Any) -> str:
    if not args:
        raise ValueError("query requires SQL")
    sql = " ".join(args)
    rows = tree.query(sql)
    return "\n".join("\t".join(str(c) for c in row) for row in rows)


def _cmd_addtype(args: list[str], _stdin: str, tree: Any) -> str:
    if not args:
        raise ValueError("addtype requires a type name")
    tree.add_type(args[0])
    return ""


def _cmd_rmtype(args: list[str], _stdin: str, tree: Any) -> str:
    if not args:
        raise ValueError("rmtype requires a type name")
    tree.remove_type(args[0])
    return ""


def _cmd_types(_args: list[str], _stdin: str, tree: Any) -> str:
    return "\n".join(tree.types())


def _cmd_tags(args: list[str], _stdin: str, tree: Any) -> str:
    if args:
        tag_list = tree.tags(args[0])
        return "\n".join(tag_list) if isinstance(tag_list, list) else ""
    tag_map = tree.tags()
    out_lines = []
    for tag, names in sorted(tag_map.items()):
        out_lines.append(f"{tag}: {', '.join(sorted(names))}")
    return "\n".join(out_lines)


def _cmd_read(args: list[str], stdin: str, tree: Any) -> str:
    depth = 0
    name: str | None = None

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "-d" and i + 1 < len(args):
            depth = int(args[i + 1])
            i += 2
            continue
        if name is None:
            name = arg
        i += 1

    if name is None:
        if stdin:
            return stdin
        raise ValueError("read requires a name")

    return tree.read(name, depth=depth)


def _cmd_help(_args: list[str], _stdin: str, _tree: Any) -> str:
    return """Available commands:
  ls [type|*]           List types or nodes of a type
  cat <name>            Show node content
  touch <name> [content]  Create node
  write <name> [content]  Write to node
  rm <name>             Remove node
  mv <old> <new>        Rename node
  cp <src> <dst>        Copy node
  ln <source> <dest>    Create symlink node
  tree                  Type-grouped view
  find [-name regex] [-type type]
  grep <pattern> [-t type] [-i] [-v] [-c] [-n]
  info <name>           Show node metadata
  sed <name> <pat> <rep> [-i] [-c n]

  addtype <type>        Register a type
  rmtype <type>         Unregister a type (must be empty)
  types                 List registered types
  tags [name]           Show tags for a node or all tags

  meta <name>           Show frontmatter key-value pairs
  body <name>           Show content without frontmatter
  links <name>          Show outgoing [[wikilinks]]
  backlinks <name>      Show what points TO this node
  resolve <name> [--exact]  Resolve a wikilink name
  schema                Show all types and their fields
  query <sql>           Run SQL query

  read <name> [-d depth]  Read node with linked content
  echo <text>           Print text
  printf <fmt> [args]   Print formatted text
  help                  Show this help

Command chaining:
  cmd1 | cmd2           Pipe output
  cmd1 ; cmd2           Sequential (continue on failure)
  cmd1 && cmd2          Sequential (stop on failure)
  cmd1 || cmd2          Run cmd2 only if cmd1 fails"""


GRAPH_COMMANDS: dict[str, Any] = {
    "ls": _cmd_ls,
    "cat": _cmd_cat,
    "touch": _cmd_touch,
    "write": _cmd_write,
    "rm": _cmd_rm,
    "mv": _cmd_mv,
    "cp": _cmd_cp,
    "ln": _cmd_ln,
    "tree": _cmd_tree,
    "find": _cmd_find,
    "grep": _cmd_grep,
    "info": _cmd_info,
    "sed": _cmd_sed,
    "help": _cmd_help,
    "meta": _cmd_meta,
    "body": _cmd_body,
    "links": _cmd_links,
    "backlinks": _cmd_backlinks,
    "resolve": _cmd_resolve,
    "schema": _cmd_schema,
    "query": _cmd_query,
    "addtype": _cmd_addtype,
    "rmtype": _cmd_rmtype,
    "types": _cmd_types,
    "tags": _cmd_tags,
    "read": _cmd_read,
}

GRAPH_HELP = """
Graph commands (KnowledgeGraph):
  meta <name>              Show frontmatter key-value pairs
  body <name>              Show content without frontmatter
  links <name>             Show outgoing [[wikilinks]]
  backlinks <name>         Show what points TO this node
  resolve <name> [--exact] Resolve a wikilink name
  schema                   Show all types and their fields
  query <sql>              Run SQL query
  addtype <type>           Register a type
  rmtype <type>            Unregister a type
  types                    List registered types
  tags [name]              Show tags
  read <name> [-d depth]   Read node with linked content"""


def register_graph_commands(commands: dict) -> None:
    """Merge graph commands into a shell COMMANDS dict.

    Overrides base commands (ls, cat, etc.) with graph-aware versions
    and removes directory-based commands that don't apply.
    """
    commands.update(GRAPH_COMMANDS)
    # Remove directory-based commands that don't apply to flat graph
    for cmd in ("cd", "pwd", "mkdir", "du", "readlink"):
        commands.pop(cmd, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_ident(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)


def _regexp(pattern: str, string: str) -> bool:
    if string is None:
        return False
    return bool(re.search(pattern, string, re.IGNORECASE))
