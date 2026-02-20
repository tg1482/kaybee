"""Chaos tests — creative, absurd, and adversarial edge cases for KnowledgeGraph.

Tests cover: cross-graph isolation, SQL injection, slug collisions, circular
wikilinks, self-references, names matching SQL internals, massive content,
malformed frontmatter, control characters, rapid mutation cycles, type
switching cascades, schema evolution, persistence stress, and more.
"""

import os
import re
import sqlite3
import tempfile

import pytest

from kaybee.core import KnowledgeGraph, extract_wikilinks, parse_frontmatter, slugify


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(params=["multi", "single"])
def kg(request):
    return KnowledgeGraph(mode=request.param)


@pytest.fixture(params=["multi", "single"])
def kg_pair(request):
    """Two completely independent in-memory graphs."""
    return KnowledgeGraph(mode=request.param), KnowledgeGraph(mode=request.param)


@pytest.fixture(params=["multi", "single"])
def kg_file(tmp_path, request):
    """Graph backed by a real file."""
    path = str(tmp_path / "test.db")
    return KnowledgeGraph(path, mode=request.param), path, request.param


# ══════════════════════════════════════════════════════════════════════════
# 1. Cross-graph isolation
# ══════════════════════════════════════════════════════════════════════════


class TestCrossGraphIsolation:
    """Two KnowledgeGraph instances must never leak data between them."""

    def test_touch_in_one_invisible_in_other(self, kg_pair):
        a, b = kg_pair
        a.touch("secret", "classified")
        assert not b.exists("secret")

    def test_types_do_not_leak(self, kg_pair):
        a, b = kg_pair
        a.add_type("alien")
        assert "alien" not in b.types()

    def test_wikilinks_do_not_cross(self, kg_pair):
        a, b = kg_pair
        a.touch("target", "real")
        b.write("linker", "See [[target]]")
        # b's link should not resolve to a's node
        resolved = b.resolve_wikilink("target")
        assert resolved is None

    def test_identical_names_different_content(self, kg_pair):
        a, b = kg_pair
        a.write("node", "alpha content")
        b.write("node", "beta content")
        assert a.cat("node") == "alpha content"
        assert b.cat("node") == "beta content"

    def test_rm_in_one_does_not_affect_other(self, kg_pair):
        a, b = kg_pair
        a.touch("shared-name", "A")
        b.touch("shared-name", "B")
        a.rm("shared-name")
        assert not a.exists("shared-name")
        assert b.exists("shared-name")
        assert b.cat("shared-name") == "B"

    def test_backlinks_isolated(self, kg_pair):
        a, b = kg_pair
        a.touch("target", "exists")
        a.write("source", "Links to [[target]]")
        b.touch("target", "also exists")
        assert a.backlinks("target") == ["source"]
        assert b.backlinks("target") == []

    def test_schema_isolated(self, kg_pair):
        a, b = kg_pair
        a.write("x", "---\ntype: alpha\nfield1: val\n---\nbody")
        b.write("y", "---\ntype: beta\nfield2: val\n---\nbody")
        assert "alpha" in a.schema()
        assert "beta" not in a.schema()
        assert "beta" in b.schema()
        assert "alpha" not in b.schema()

    def test_query_isolated(self, kg_pair):
        a, b = kg_pair
        a.touch("private", "secret data")
        rows = b.query("SELECT name FROM nodes")
        names = [r[0] for r in rows]
        assert "private" not in names


# ══════════════════════════════════════════════════════════════════════════
# 2. SQL injection / adversarial names
# ══════════════════════════════════════════════════════════════════════════


class TestSQLInjection:
    """Node names, types, content, and queries that try to break SQL."""

    def test_name_with_sql_keywords(self, kg):
        kg.touch("DROP TABLE nodes", "payload")
        # slugify turns it into something safe, but it should exist
        slug = slugify("DROP TABLE nodes")
        assert kg.exists(slug)
        assert kg.cat(slug) == "payload"

    def test_name_with_quotes(self, kg):
        kg.touch("it's a \"test\"", "data")
        slug = slugify("it's a \"test\"")
        assert kg.exists(slug)

    def test_name_with_semicolons(self, kg):
        kg.touch("name; DROP TABLE nodes;--", "attack")
        slug = slugify("name; DROP TABLE nodes;--")
        assert kg.exists(slug)
        # original table should still work
        kg.touch("normal", "fine")
        assert kg.exists("normal")

    def test_content_with_sql_injection(self, kg):
        evil = "'); DROP TABLE nodes; --"
        kg.write("victim", evil)
        assert kg.cat("victim") == evil
        kg.touch("proof", "still works")
        assert kg.exists("proof")

    def test_type_with_sql_injection(self, kg):
        kg.write("item", "---\ntype: '); DROP TABLE nodes;--\n---\nbody")
        # should not crash, type gets sanitized via _safe_ident
        assert kg.exists("item")

    def test_frontmatter_key_injection(self, kg):
        kg.write("item", "---\ntype: concept\n\"key); DROP TABLE nodes\": val\n---\nbody")
        assert kg.exists("item")

    def test_tag_with_sql(self, kg):
        kg.write("item", "---\ntags: [normal, \"'); DROP TABLE nodes;--\"]\n---\nbody")
        tags = kg.tags("item")
        assert len(tags) == 2

    def test_grep_pattern_injection(self, kg):
        kg.touch("node", "data")
        # grep uses Python re, not SQL LIKE, but test it doesn't crash
        results = kg.grep(".*", content=True)
        assert "node" in results


# ══════════════════════════════════════════════════════════════════════════
# 3. Node names matching SQL table names
# ══════════════════════════════════════════════════════════════════════════


class TestReservedNames:
    """Names that collide with internal SQL tables and keywords."""

    def test_node_named_nodes(self, kg):
        kg.touch("nodes", "I am a node named nodes")
        assert kg.cat("nodes") == "I am a node named nodes"

    def test_node_named_links(self, kg):
        # slugify("_links") -> "links" (strips leading _)
        kg.touch("_links", "link impersonator")
        slug = slugify("_links")
        assert kg.exists(slug)

    def test_node_named_types(self, kg):
        kg.touch("_types", "type impersonator")
        slug = slugify("_types")
        assert kg.exists(slug)

    def test_node_named_sqlite_master(self, kg):
        kg.touch("sqlite_master", "meta impersonator")
        assert kg.exists("sqlite_master")

    def test_type_named_nodes(self, kg):
        # Reserved type name "nodes" is now rejected with ValueError
        with pytest.raises(ValueError, match="Reserved type name"):
            kg.write("item", "---\ntype: nodes\n---\nbody")

    def test_type_named_select(self, kg):
        if kg._mode == "single":
            # In single mode, no per-type table is created, so SQL keyword types work
            kg.write("item", "---\ntype: SELECT\n---\nbody")
            assert kg.exists("item")
        else:
            # SQL keyword as type name — _safe_ident keeps it as "SELECT"
            # which causes a CREATE TABLE SELECT (...) syntax error
            with pytest.raises(sqlite3.OperationalError):
                kg.write("item", "---\ntype: SELECT\n---\nbody")


# ══════════════════════════════════════════════════════════════════════════
# 4. Slug collisions
# ══════════════════════════════════════════════════════════════════════════


class TestSlugCollisions:
    """Names that map to the same slug after slugification."""

    def test_case_collision(self, kg):
        kg.touch("Hello World", "first")
        # "hello world" -> same slug "hello-world" — touch sees it exists, calls write
        kg.touch("hello world", "second")
        # "second" should overwrite via write()
        assert kg.cat("hello-world") == "second"

    def test_punctuation_collision(self, kg):
        kg.touch("foo-bar", "first")
        # "foo bar" and "foo_bar" -> different slugs?
        slug1 = slugify("foo-bar")
        slug2 = slugify("foo bar")
        slug3 = slugify("foo_bar")
        # foo-bar -> foo-bar, foo bar -> foo-bar (collision!), foo_bar -> foo_bar
        assert slug1 == slug2  # both "foo-bar"
        assert slug3 == "foo_bar"

    def test_collision_overwrites_on_touch_with_content(self, kg):
        kg.touch("My Item", "original")
        kg.touch("my item", "updated")
        assert kg.cat("my-item") == "updated"

    def test_all_special_chars_become_item(self, kg):
        # Names that are entirely special characters -> "item"
        kg.touch("@#$%^&*", "special")
        assert kg.exists("item")
        assert kg.cat("item") == "special"

    def test_empty_name_becomes_item(self, kg):
        kg.touch("", "empty name")
        assert kg.exists("item")

    def test_whitespace_only_becomes_item(self, kg):
        kg.touch("   ", "spaces")
        assert kg.exists("item")

    def test_many_names_same_slug(self, kg):
        """Multiple names that all slugify to the same thing — last write wins."""
        variants = ["Hello World", "HELLO WORLD", "hello   world", "Hello---World"]
        for i, v in enumerate(variants):
            kg.touch(v, f"version-{i}")
        assert kg.cat("hello-world") == f"version-{len(variants) - 1}"


# ══════════════════════════════════════════════════════════════════════════
# 5. Circular and complex wikilink topologies
# ══════════════════════════════════════════════════════════════════════════


class TestWikilinkTopologies:
    """Cycles, self-loops, cliques, and other graph shapes."""

    def test_self_referencing_node(self, kg):
        kg.write("narcissist", "I link to [[narcissist]] myself")
        links = kg.wikilinks("narcissist")
        assert "narcissist" in links
        bl = kg.backlinks("narcissist")
        assert "narcissist" in bl

    def test_two_node_cycle(self, kg):
        kg.write("alpha", "See [[beta]]")
        kg.write("beta", "See [[alpha]]")
        assert kg.wikilinks("alpha") == ["beta"]
        assert kg.wikilinks("beta") == ["alpha"]
        assert "alpha" in kg.backlinks("beta")
        assert "beta" in kg.backlinks("alpha")

    def test_triangle_cycle(self, kg):
        kg.write("a", "links to [[b]]")
        kg.write("b", "links to [[c]]")
        kg.write("c", "links to [[a]]")
        g = kg.graph()
        assert "b" in g.get("a", [])
        assert "c" in g.get("b", [])
        assert "a" in g.get("c", [])

    def test_complete_graph_k5(self, kg):
        """Every node links to every other node (K5)."""
        names = ["n1", "n2", "n3", "n4", "n5"]
        for name in names:
            others = [f"[[{o}]]" for o in names if o != name]
            kg.write(name, f"Links: {' '.join(others)}")
        for name in names:
            links = kg.wikilinks(name)
            expected = [n for n in names if n != name]
            assert sorted(links) == sorted(expected)

    def test_star_topology(self, kg):
        """One hub links to many spokes, spokes link only back to hub."""
        kg.write("hub", " ".join(f"[[spoke-{i}]]" for i in range(20)))
        for i in range(20):
            kg.write(f"spoke-{i}", "Links to [[hub]]")
        assert len(kg.wikilinks("hub")) == 20
        bl = kg.backlinks("hub")
        assert len(bl) == 20

    def test_dangling_links(self, kg):
        """Links to nodes that don't exist."""
        kg.write("orphan-linker", "See [[ghost]] and [[phantom]] and [[void]]")
        links = kg.wikilinks("orphan-linker")
        assert sorted(links) == ["ghost", "phantom", "void"]
        # All should be unresolved
        rows = kg.query(
            "SELECT target_name, target_resolved FROM _links WHERE source_name = 'orphan-linker'"
        )
        for _, resolved in rows:
            assert resolved is None

    def test_dangling_link_becomes_resolved(self, kg):
        """Create link first, then create target — link should auto-resolve."""
        kg.write("linker", "See [[future-node]]")
        rows = kg.query(
            "SELECT target_resolved FROM _links WHERE source_name = 'linker' AND target_name = 'future-node'"
        )
        assert rows[0][0] is None
        # Now create the target
        kg.touch("future-node", "I exist now")
        rows = kg.query(
            "SELECT target_resolved FROM _links WHERE source_name = 'linker' AND target_name = 'future-node'"
        )
        assert rows[0][0] == "future-node"

    def test_link_chain_resolution(self, kg):
        """A → B → C → D — ensure full chain is tracked."""
        kg.write("a", "[[b]]")
        kg.write("b", "[[c]]")
        kg.write("c", "[[d]]")
        kg.touch("d", "end")
        assert kg.graph() == {"a": ["b"], "b": ["c"], "c": ["d"]}

    def test_duplicate_links_in_content(self, kg):
        """Same wikilink mentioned multiple times — should only appear once in _links."""
        kg.touch("target", "exists")
        kg.write("source", "See [[target]] and again [[target]] and once more [[target]]")
        links = kg.wikilinks("source")
        # wikilinks returns from _links table, PRIMARY KEY(source_name, target_name) deduplicates
        assert links.count("target") == 1

    def test_many_links_from_one_node(self, kg):
        """Single node with 100 outgoing links."""
        for i in range(100):
            kg.touch(f"t-{i}", f"target {i}")
        body = " ".join(f"[[t-{i}]]" for i in range(100))
        kg.write("mega-linker", body)
        links = kg.wikilinks("mega-linker")
        assert len(links) == 100


# ══════════════════════════════════════════════════════════════════════════
# 6. Malformed and adversarial frontmatter
# ══════════════════════════════════════════════════════════════════════════


class TestMalformedFrontmatter:
    """Content that looks like frontmatter but isn't, or is broken."""

    def test_unclosed_frontmatter(self, kg):
        """Opening --- without closing --- → treated as body."""
        kg.write("bad", "---\ntype: concept\nno closing fence")
        meta = kg.frontmatter("bad")
        assert meta == {}  # no valid frontmatter
        assert "---" in kg.cat("bad")

    def test_triple_dash_in_body(self, kg):
        """--- appearing in body after valid frontmatter."""
        text = "---\ntype: note\n---\nBody with --- dashes inside"
        kg.write("dashes", text)
        assert kg.body("dashes") == "Body with --- dashes inside"

    def test_frontmatter_with_no_keys(self, kg):
        """Empty frontmatter block."""
        kg.write("empty-fm", "---\n---\nBody here")
        assert kg.frontmatter("empty-fm") == {}
        assert kg.body("empty-fm") == "Body here"

    def test_frontmatter_with_only_comments(self, kg):
        kg.write("comments", "---\n# just a comment\n# another\n---\nBody")
        meta = kg.frontmatter("comments")
        assert meta == {}

    def test_nested_yaml_ignored(self, kg):
        """Deeply nested YAML — only one level of nesting is supported."""
        text = "---\ntype: deep\nouter:\n  inner:\n    deepest: value\n---\nBody"
        kg.write("deep", text)
        meta = kg.frontmatter("deep")
        assert meta["type"] == "deep"
        # inner nesting beyond one level treated as strings
        assert "outer" in meta

    def test_wikilinks_inside_frontmatter_values(self, kg):
        """Wikilink syntax inside a frontmatter value — should not create links."""
        text = "---\ntype: note\ndescription: See [[phantom]]\n---\nBody"
        kg.write("item", text)
        # Links come from body, not frontmatter
        links = kg.wikilinks("item")
        assert "phantom" not in links

    def test_content_that_looks_like_frontmatter(self, kg):
        """Body starts with --- but on the first line there's content before it."""
        kg.write("tricky", "not-frontmatter---\ntype: fake\n---\nBody")
        meta = kg.frontmatter("tricky")
        assert meta == {}

    def test_frontmatter_with_colon_in_value(self, kg):
        text = "---\nurl: https://example.com:8080/path\n---\nBody"
        kg.write("url-node", text)
        meta = kg.frontmatter("url-node")
        assert "https:" in meta.get("url", "") or "example" in meta.get("url", "")

    def test_frontmatter_with_empty_list(self, kg):
        text = "---\ntags: []\n---\nBody"
        kg.write("empty-tags", text)
        assert kg.tags("empty-tags") == []

    def test_frontmatter_boolean_like_values(self, kg):
        text = "---\ntype: note\ndraft: true\npublished: false\n---\nBody"
        kg.write("bools", text)
        meta = kg.frontmatter("bools")
        assert meta["draft"] == "true"
        assert meta["published"] == "false"


# ══════════════════════════════════════════════════════════════════════════
# 7. Unicode, emoji, and control characters
# ══════════════════════════════════════════════════════════════════════════


class TestUnicodeAndControlChars:
    """Exotic characters in every field."""

    def test_emoji_name(self, kg):
        # emoji are not alnum, so slugify strips them
        slug = slugify("🔥 fire 🔥")
        kg.touch("🔥 fire 🔥", "hot content")
        assert kg.exists(slug)

    def test_cjk_name(self, kg):
        # CJK characters are not alnum in many locales... depends on Python
        kg.touch("知識グラフ", "Japanese knowledge graph")
        slug = slugify("知識グラフ")
        assert kg.exists(slug)

    def test_arabic_name(self, kg):
        kg.touch("معرفة", "Arabic knowledge")
        slug = slugify("معرفة")
        assert kg.exists(slug)

    def test_emoji_in_content(self, kg):
        kg.write("emoji", "🎉🚀🌍💡🔬")
        assert "🎉" in kg.cat("emoji")

    def test_null_bytes_in_content(self, kg):
        kg.write("nulls", "before\x00after")
        content = kg.cat("nulls")
        assert "before" in content

    def test_newlines_and_tabs_in_names(self, kg):
        """Newlines/tabs in names get stripped by slugify."""
        kg.touch("hello\nworld\ttab", "messy name")
        slug = slugify("hello\nworld\ttab")
        assert kg.exists(slug)

    def test_rtl_override_chars(self, kg):
        kg.write("rtl", "Normal \u202e REVERSED \u202c back")
        assert kg.exists("rtl")

    def test_zero_width_chars(self, kg):
        kg.write("invisible", "zero\u200bwidth\u200bjoiners")
        content = kg.cat("invisible")
        assert "zero" in content

    def test_combining_characters(self, kg):
        # é as e + combining acute
        kg.touch("cafe\u0301", "coffee shop")
        slug = slugify("cafe\u0301")
        assert kg.exists(slug)

    def test_very_long_unicode_name(self, kg):
        name = "漢字" * 500
        kg.touch(name, "long cjk name")
        slug = slugify(name)
        assert kg.exists(slug)


# ══════════════════════════════════════════════════════════════════════════
# 8. Rapid mutation cycles
# ══════════════════════════════════════════════════════════════════════════


class TestRapidMutations:
    """Stress-test create/delete/rename/copy cycles."""

    def test_create_delete_recreate_100_times(self, kg):
        for i in range(100):
            kg.touch("phoenix", f"life-{i}")
            kg.rm("phoenix")
        kg.touch("phoenix", "final")
        assert kg.cat("phoenix") == "final"

    def test_mv_chain(self, kg):
        """Rename a node 50 times in sequence."""
        kg.touch("name-0", "traveling node")
        for i in range(50):
            kg.mv(f"name-{i}", f"name-{i+1}")
        assert kg.exists("name-50")
        assert not kg.exists("name-0")
        assert kg.cat("name-50") == "traveling node"

    def test_mv_preserves_links(self, kg):
        """Renaming a node should update all backlinks."""
        kg.touch("target", "the target")
        kg.write("linker", "See [[target]]")
        kg.mv("target", "new-target")
        # The link resolution should update
        rows = kg.query(
            "SELECT target_resolved FROM _links WHERE source_name = 'linker'"
        )
        assert rows[0][0] == "new-target"

    def test_cp_then_rm_original(self, kg):
        """Copy a node then remove the original."""
        kg.write("original", "---\ntype: note\n---\nSome content with [[other]]")
        kg.touch("other", "exists")
        kg.cp("original", "clone")
        kg.rm("original")
        assert not kg.exists("original")
        assert kg.exists("clone")
        assert kg.body("clone") == "Some content with [[other]]"

    def test_write_overwrite_100_types(self, kg):
        """Switch a node's type 100 times."""
        for i in range(100):
            kg.write("chameleon", f"---\ntype: type-{i}\n---\nbody-{i}")
        meta = kg.frontmatter("chameleon")
        assert meta["type"] == "type-99"
        assert kg.body("chameleon") == "body-99"
        # Old types should not list this node
        assert kg.find_by_type("type-0") == []
        assert kg.find_by_type("type-50") == []
        assert kg.find_by_type("type-99") == ["chameleon"]

    def test_touch_without_content_preserves_existing(self, kg):
        kg.write("keeper", "precious content")
        kg.touch("keeper")  # no content — should not overwrite
        assert kg.cat("keeper") == "precious content"

    def test_write_empty_string_clears_content(self, kg):
        kg.write("full", "---\ntype: note\n---\nbig body")
        kg.write("full", "")
        assert kg.cat("full") == ""
        assert kg.frontmatter("full") == {}

    def test_rm_nonexistent_raises(self, kg):
        with pytest.raises(KeyError):
            kg.rm("ghost")

    def test_mv_to_existing_raises(self, kg):
        kg.touch("a", "first")
        kg.touch("b", "second")
        with pytest.raises(FileExistsError):
            kg.mv("a", "b")

    def test_cp_to_existing_raises(self, kg):
        kg.touch("a", "first")
        kg.touch("b", "second")
        with pytest.raises(FileExistsError):
            kg.cp("a", "b")

    def test_cp_to_self_raises(self, kg):
        kg.touch("a", "data")
        with pytest.raises(ValueError):
            kg.cp("a", "a")


# ══════════════════════════════════════════════════════════════════════════
# 9. Type system abuse
# ══════════════════════════════════════════════════════════════════════════


class TestTypeSystemAbuse:
    """Adversarial type names, cascading type changes, schema evolution."""

    def test_type_with_spaces(self, kg):
        kg.write("item", "---\ntype: my cool type\n---\nbody")
        assert kg.find_by_type("my cool type") == ["item"]

    def test_type_with_special_chars(self, kg):
        kg.write("item", "---\ntype: type-with-dashes_and.dots\n---\nbody")
        assert kg.find_by_type("type-with-dashes_and.dots") == ["item"]

    def test_type_empty_string(self, kg):
        kg.write("item", "---\ntype: \n---\nbody")
        meta = kg.frontmatter("item")
        # empty type -> either empty string or None behavior
        assert kg.exists("item")

    def test_remove_type_still_has_nodes(self, kg):
        kg.write("a", "---\ntype: concept\n---\nA")
        kg.write("b", "---\ntype: concept\n---\nB")
        with pytest.raises(ValueError, match="2 node"):
            kg.remove_type("concept")

    def test_schema_evolution_add_fields(self, kg):
        """Add new frontmatter fields to an existing type over time."""
        kg.write("v1", "---\ntype: entity\ntitle: First\n---\nbody")
        kg.write("v2", "---\ntype: entity\ntitle: Second\ncolor: blue\n---\nbody")
        kg.write("v3", "---\ntype: entity\ntitle: Third\ncolor: red\nweight: 10\n---\nbody")
        schema = kg.schema()
        assert "entity" in schema
        fields = schema["entity"]
        # "name" and "content" are excluded from schema (they're built-in columns)
        assert "title" in fields
        assert "color" in fields
        assert "weight" in fields

    def test_many_types(self, kg):
        """Create 50 different types."""
        for i in range(50):
            kg.write(f"node-{i}", f"---\ntype: type-{i}\n---\nbody-{i}")
        assert len(kg.types()) == 50
        for i in range(50):
            assert kg.find_by_type(f"type-{i}") == [f"node-{i}"]

    def test_type_change_cleans_old_table(self, kg):
        """When a node changes type, it should be removed from the old type table."""
        kg.write("x", "---\ntype: alpha\nfield: val\n---\nbody")
        if kg._mode == "single":
            rows = kg.query("SELECT * FROM _data WHERE name = 'x'")
            assert len(rows) == 1
            kg.write("x", "---\ntype: beta\nfield: val\n---\nbody")
            # In single mode, the row still exists but with new type in nodes
            rows = kg.query("SELECT * FROM _data WHERE name = 'x'")
            assert len(rows) == 1
            assert kg.find_by_type("alpha") == []
            assert kg.find_by_type("beta") == ["x"]
        else:
            rows = kg.query("SELECT * FROM alpha WHERE name = 'x'")
            assert len(rows) == 1
            kg.write("x", "---\ntype: beta\nfield: val\n---\nbody")
            rows = kg.query("SELECT * FROM alpha WHERE name = 'x'")
            assert len(rows) == 0
            rows = kg.query("SELECT * FROM beta WHERE name = 'x'")
            assert len(rows) == 1

    def test_type_as_number_string(self, kg):
        if kg._mode == "single":
            # In single mode, no per-type table is created, so numeric types work
            kg.write("item", "---\ntype: 42\n---\nbody")
            assert kg.exists("item")
        else:
            # Numeric type names cause CREATE TABLE 42 (...) syntax error
            # because _safe_ident("42") = "42" which is not a valid identifier
            with pytest.raises(sqlite3.OperationalError):
                kg.write("item", "---\ntype: 42\n---\nbody")


# ══════════════════════════════════════════════════════════════════════════
# 10. Tags chaos
# ══════════════════════════════════════════════════════════════════════════


class TestTagsChaos:
    """Extreme tag usage."""

    def test_thousand_tags(self, kg):
        tags = ", ".join(f"tag-{i}" for i in range(1000))
        kg.write("taggy", f"---\ntags: [{tags}]\n---\nbody")
        result = kg.tags("taggy")
        assert len(result) == 1000

    def test_duplicate_tags(self, kg):
        kg.write("dupes", "---\ntags: [a, a, a, b, b]\n---\nbody")
        result = kg.tags("dupes")
        assert result == ["a", "a", "a", "b", "b"]

    def test_empty_tag(self, kg):
        kg.write("item", "---\ntags: [, , x, ]\n---\nbody")
        tags = kg.tags("item")
        # empty strings might appear
        assert "x" in tags

    def test_tag_with_special_chars(self, kg):
        kg.write("item", "---\ntags: [c++, c#, .net, node.js]\n---\nbody")
        tags = kg.tags("item")
        assert "c++" in tags
        assert "c#" in tags

    def test_global_tag_map(self, kg):
        kg.write("a", "---\ntags: [x, y]\n---\n")
        kg.write("b", "---\ntags: [y, z]\n---\n")
        kg.write("c", "---\ntags: [x, z]\n---\n")
        tag_map = kg.tags()
        assert sorted(tag_map["x"]) == ["a", "c"]
        assert sorted(tag_map["y"]) == ["a", "b"]
        assert sorted(tag_map["z"]) == ["b", "c"]

    def test_tags_not_a_list(self, kg):
        """Tags as a string instead of a list."""
        kg.write("scalar", "---\ntags: just-a-string\n---\nbody")
        result = kg.tags("scalar")
        # tags() returns [] if not a list
        assert result == []


# ══════════════════════════════════════════════════════════════════════════
# 12. Massive / stress tests
# ══════════════════════════════════════════════════════════════════════════


class TestScaleStress:
    """Performance and correctness at scale."""

    def test_500_nodes(self, kg):
        for i in range(500):
            kg.touch(f"node-{i}", f"content-{i}")
        all_nodes = kg.ls("*")
        assert len(all_nodes) == 500

    def test_deeply_linked_chain(self, kg):
        """Chain of 100 nodes, each linking to the next."""
        for i in range(100):
            next_link = f"[[chain-{i+1}]]" if i < 99 else ""
            kg.write(f"chain-{i}", f"Link: {next_link}")
        kg.touch("chain-99", "end")
        # First node links to second
        assert kg.wikilinks("chain-0") == ["chain-1"]
        # Last node has no outgoing
        assert kg.wikilinks("chain-99") == []

    def test_node_with_huge_content(self, kg):
        """1MB of content."""
        content = "x" * (1024 * 1024)
        kg.write("big", content)
        assert len(kg.cat("big")) == 1024 * 1024

    def test_node_with_many_frontmatter_fields(self, kg):
        fields = "\n".join(f"field_{i}: value_{i}" for i in range(200))
        kg.write("meta-heavy", f"---\ntype: mega\n{fields}\n---\nbody")
        meta = kg.frontmatter("meta-heavy")
        assert len(meta) > 100  # at least the fields we set

    def test_tree_output_large(self, kg):
        for i in range(50):
            kg.write(f"node-{i}", f"---\ntype: t-{i % 5}\n---\ncontent-{i}")
        output = kg.tree()
        assert len(output.splitlines()) > 50

    def test_find_regex_across_many(self, kg):
        for i in range(200):
            kg.touch(f"item-{i:04d}", f"data {i}")
        results = kg.find(name=r"item-00[0-9][0-9]")
        assert len(results) == 100  # item-0000 through item-0099

    def test_grep_across_many(self, kg):
        for i in range(200):
            kg.touch(f"doc-{i}", f"The answer is {42 if i % 10 == 0 else 0}")
        results = kg.grep("42", content=True)
        # 20 nodes have "42" in content, plus names like "doc-42", "doc-142" match
        assert len(results) >= 20


# ══════════════════════════════════════════════════════════════════════════
# 13. Persistence edge cases
# ══════════════════════════════════════════════════════════════════════════


class TestPersistenceStress:
    """File-backed graph: open/close cycles, corruption resilience."""

    @pytest.fixture(params=["multi", "single"])
    def mode(self, request):
        return request.param

    def test_survives_reopen(self, tmp_path, mode):
        path = str(tmp_path / "persist.db")
        kg1 = KnowledgeGraph(path, mode=mode)
        kg1.write("node", "---\ntype: note\n---\nHello")
        kg1._db.close()

        kg2 = KnowledgeGraph(path, mode=mode)
        assert kg2.exists("node")
        assert kg2.cat("node") == "---\ntype: note\n---\nHello"
        kg2._db.close()

    def test_type_tables_survive_reopen(self, tmp_path, mode):
        path = str(tmp_path / "types.db")
        kg1 = KnowledgeGraph(path, mode=mode)
        kg1.write("x", "---\ntype: concept\nfield: val\n---\nbody")
        kg1._db.close()

        kg2 = KnowledgeGraph(path, mode=mode)
        assert kg2.find_by_type("concept") == ["x"]
        schema = kg2.schema()
        assert "concept" in schema
        kg2._db.close()

    def test_links_survive_reopen(self, tmp_path, mode):
        path = str(tmp_path / "links.db")
        kg1 = KnowledgeGraph(path, mode=mode)
        kg1.touch("target", "exists")
        kg1.write("source", "See [[target]]")
        kg1._db.close()

        kg2 = KnowledgeGraph(path, mode=mode)
        assert kg2.wikilinks("source") == ["target"]
        assert "source" in kg2.backlinks("target")
        kg2._db.close()

    def test_many_open_close_cycles(self, tmp_path, mode):
        path = str(tmp_path / "cycles.db")
        for i in range(20):
            kg = KnowledgeGraph(path, mode=mode)
            kg.touch(f"node-{i}", f"cycle-{i}")
            kg._db.close()

        final = KnowledgeGraph(path, mode=mode)
        for i in range(20):
            assert final.exists(f"node-{i}")
            assert final.cat(f"node-{i}") == f"cycle-{i}"
        final._db.close()

    def test_concurrent_mutations_across_reopens(self, tmp_path, mode):
        path = str(tmp_path / "mutate.db")
        kg = KnowledgeGraph(path, mode=mode)
        kg.write("evolving", "---\ntype: v1\n---\nfirst")
        kg._db.close()

        kg = KnowledgeGraph(path, mode=mode)
        kg.write("evolving", "---\ntype: v2\nfield: new\n---\nsecond")
        kg._db.close()

        kg = KnowledgeGraph(path, mode=mode)
        assert kg.frontmatter("evolving")["type"] == "v2"
        assert kg.body("evolving") == "second"
        kg._db.close()


# ══════════════════════════════════════════════════════════════════════════
# 14. Query API abuse
# ══════════════════════════════════════════════════════════════════════════


class TestQueryAbuse:
    """Direct SQL query edge cases."""

    def test_select_all_nodes(self, kg):
        kg.touch("a", "1")
        kg.touch("b", "2")
        rows = kg.query("SELECT name FROM nodes ORDER BY name")
        assert [r[0] for r in rows] == ["a", "b"]

    def test_query_empty_graph(self, kg):
        rows = kg.query("SELECT * FROM nodes")
        assert rows == []

    def test_query_nonexistent_table(self, kg):
        with pytest.raises(sqlite3.OperationalError):
            kg.query("SELECT * FROM nonexistent_table")

    def test_query_with_params(self, kg):
        kg.touch("target", "data")
        t = kg.data_table()
        rows = kg.query(f"SELECT content FROM {t} WHERE name = ?", ("target",))
        assert rows[0][0] == "data"

    def test_query_returns_link_info(self, kg):
        kg.touch("b", "exists")
        kg.write("a", "See [[b]]")
        rows = kg.query(
            "SELECT source_name, target_name, target_resolved FROM _links"
        )
        assert len(rows) == 1
        assert rows[0] == ("a", "b", "b")


# ══════════════════════════════════════════════════════════════════════════
# 15. Edge cases in search: find, grep
# ══════════════════════════════════════════════════════════════════════════


class TestSearchEdgeCases:
    def test_find_no_match(self, kg):
        kg.touch("apple", "fruit")
        assert kg.find(name="zzz") == []

    def test_find_by_type_no_match(self, kg):
        kg.touch("apple", "fruit")
        assert kg.find(type="nonexistent") == []

    def test_grep_empty_pattern(self, kg):
        kg.touch("a", "hello")
        # empty pattern matches everything
        results = kg.grep("", content=True)
        assert "a" in results

    def test_grep_regex_special_chars(self, kg):
        kg.touch("math", "price is $100.00")
        results = kg.grep(r"\$\d+\.\d+", content=True)
        assert "math" in results

    def test_grep_invert(self, kg):
        kg.touch("yes", "match this")
        kg.touch("no", "other content")
        results = kg.grep("match", content=True, invert=True)
        assert "no" in results
        assert "yes" not in results

    def test_grep_count(self, kg):
        for i in range(10):
            kg.touch(f"item-{i}", f"data-{i}")
        count = kg.grep("item", count=True)
        assert count == 10

    def test_grep_line_mode(self, kg):
        kg.write("multi", "line one\nline two\nline three")
        results = kg.grep("two", content=True, lines=True)
        assert any("two" in r for r in results)

    def test_find_regex(self, kg):
        kg.touch("alpha-1", "a")
        kg.touch("alpha-2", "b")
        kg.touch("beta-1", "c")
        results = kg.find(name=r"^alpha")
        assert sorted(results) == ["alpha-1", "alpha-2"]

    def test_grep_by_type(self, kg):
        kg.write("a", "---\ntype: cat\n---\nmeow")
        kg.write("b", "---\ntype: dog\n---\nmeow")
        results = kg.grep("meow", type="cat", content=True)
        assert results == ["a"]


# ══════════════════════════════════════════════════════════════════════════
# 16. Edge cases in info
# ══════════════════════════════════════════════════════════════════════════


class TestInfoEdgeCases:
    def test_info_nonexistent(self, kg):
        with pytest.raises(KeyError):
            kg.info("ghost")

    def test_info_empty_node(self, kg):
        kg.touch("empty")
        info = kg.info("empty")
        assert info["name"] == "empty"
        assert info["type"] is None
        assert info["tags"] == []
        assert info["content_length"] == 0
        assert info["has_content"] is False

    def test_info_rich_node(self, kg):
        kg.write("rich", "---\ntype: concept\ntags: [a, b]\n---\nSome content")
        info = kg.info("rich")
        assert info["type"] == "concept"
        assert info["tags"] == ["a", "b"]
        assert info["has_content"] is True
        assert info["content_length"] > 0

    def test_info_tags_not_list(self, kg):
        kg.write("bad", "---\ntags: scalar\n---\nbody")
        info = kg.info("bad")
        assert info["tags"] == []  # tags must be a list


# ══════════════════════════════════════════════════════════════════════════
# 17. Frontmatter round-trip integrity
# ══════════════════════════════════════════════════════════════════════════


class TestFrontmatterRoundtrip:
    """Write content with frontmatter, cat it back, parse again — should match."""

    def test_simple_roundtrip(self, kg):
        original = "---\ntype: note\ntitle: Hello\n---\nBody"
        kg.write("doc", original)
        result = kg.cat("doc")
        meta, body = parse_frontmatter(result)
        assert meta["type"] == "note"
        assert meta["title"] == "Hello"
        assert body == "Body"

    def test_list_roundtrip(self, kg):
        original = "---\ntags: [x, y, z]\n---\nBody"
        kg.write("doc", original)
        result = kg.cat("doc")
        meta, body = parse_frontmatter(result)
        assert meta["tags"] == ["x", "y", "z"]

    def test_nested_dict_roundtrip(self, kg):
        original = "---\ntype: note\naddress:\n  city: NYC\n  zip: 10001\n---\nBody"
        kg.write("doc", original)
        result = kg.cat("doc")
        meta, body = parse_frontmatter(result)
        assert meta["type"] == "note"
        assert isinstance(meta["address"], dict)
        assert meta["address"]["city"] == "NYC"

    def test_write_then_body_then_frontmatter(self, kg):
        kg.write("doc", "---\ntype: note\nfoo: bar\n---\nThe body")
        assert kg.body("doc") == "The body"
        assert kg.frontmatter("doc") == {"type": "note", "foo": "bar"}

    def test_multiple_writes_frontmatter_update(self, kg):
        kg.write("doc", "---\ntype: note\n---\nv1")
        kg.write("doc", "---\ntype: concept\nauthor: me\n---\nv2")
        meta = kg.frontmatter("doc")
        assert meta["type"] == "concept"
        assert meta["author"] == "me"
        assert kg.body("doc") == "v2"


# ══════════════════════════════════════════════════════════════════════════
# 18. Wikilink resolution after graph mutations
# ══════════════════════════════════════════════════════════════════════════


class TestWikilinkResolutionAfterMutations:
    """Links should re-resolve when the graph changes."""

    def test_create_target_resolves_dangling(self, kg):
        kg.write("a", "See [[b]]")
        assert kg.query(
            "SELECT target_resolved FROM _links WHERE source_name = 'a'"
        )[0][0] is None
        kg.touch("b", "now exists")
        assert kg.query(
            "SELECT target_resolved FROM _links WHERE source_name = 'a'"
        )[0][0] == "b"

    def test_rm_target_unresolves_link(self, kg):
        kg.touch("b", "exists")
        kg.write("a", "See [[b]]")
        assert kg.query(
            "SELECT target_resolved FROM _links WHERE source_name = 'a'"
        )[0][0] == "b"
        kg.rm("b")
        rows = kg.query(
            "SELECT target_resolved FROM _links WHERE source_name = 'a'"
        )
        assert rows[0][0] is None

    def test_mv_target_updates_resolution(self, kg):
        kg.touch("old-name", "target")
        kg.write("linker", "See [[old-name]]")
        kg.mv("old-name", "new-name")
        rows = kg.query(
            "SELECT target_resolved FROM _links WHERE source_name = 'linker'"
        )
        assert rows[0][0] == "new-name"

    def test_rewrite_source_clears_old_links(self, kg):
        kg.touch("target-a", "a")
        kg.touch("target-b", "b")
        kg.write("source", "Link to [[target-a]]")
        assert kg.wikilinks("source") == ["target-a"]
        kg.write("source", "Now link to [[target-b]]")
        assert kg.wikilinks("source") == ["target-b"]
        # Old link should be gone
        rows = kg.query(
            "SELECT target_name FROM _links WHERE source_name = 'source'"
        )
        assert [r[0] for r in rows] == ["target-b"]

    def test_fuzzy_resolution_case_insensitive(self, kg):
        kg.touch("my-node", "exists")
        kg.write("linker", "See [[My Node]]")
        rows = kg.query(
            "SELECT target_resolved FROM _links WHERE source_name = 'linker'"
        )
        assert rows[0][0] == "my-node"


# ══════════════════════════════════════════════════════════════════════════
# 19. Absurd but valid usage patterns
# ══════════════════════════════════════════════════════════════════════════


class TestAbsurdUsage:
    """Creative misuse that should still work (or fail gracefully)."""

    def test_graph_as_key_value_store(self, kg):
        """Use KnowledgeGraph as a simple key-value store."""
        for i in range(100):
            kg.touch(f"key-{i}", f"value-{i}")
        for i in range(100):
            assert kg.cat(f"key-{i}") == f"value-{i}"

    def test_graph_as_todo_list(self, kg):
        """Store a TODO list with tags for status."""
        kg.write("task-1", "---\ntype: task\ntags: [done]\n---\nBuy milk")
        kg.write("task-2", "---\ntype: task\ntags: [pending]\n---\nClean house")
        kg.write("task-3", "---\ntype: task\ntags: [done, urgent]\n---\nFile taxes")
        done = [n for n in kg.find_by_type("task") if "done" in kg.tags(n)]
        assert sorted(done) == ["task-1", "task-3"]

    def test_graph_as_social_network(self, kg):
        """Model a social network with wikilinks as friend connections."""
        users = ["alice", "bob", "carol", "dave"]
        kg.write("alice", "---\ntype: user\n---\nFriends: [[bob]] [[carol]]")
        kg.write("bob", "---\ntype: user\n---\nFriends: [[alice]] [[dave]]")
        kg.write("carol", "---\ntype: user\n---\nFriends: [[alice]]")
        kg.write("dave", "---\ntype: user\n---\nFriends: [[bob]] [[carol]]")
        # Alice's friends
        assert sorted(kg.wikilinks("alice")) == ["bob", "carol"]
        # Who follows bob?
        bl = kg.backlinks("bob")
        assert "alice" in bl
        assert "dave" in bl

    def test_self_referential_encyclopedia(self, kg):
        """Every node references every other node — dense graph."""
        names = [f"entry-{i}" for i in range(10)]
        for name in names:
            others = [f"[[{n}]]" for n in names]
            kg.write(name, f"---\ntype: entry\n---\n{' '.join(others)}")
        g = kg.graph()
        for name in names:
            assert len(g[name]) == 10  # including self

    def test_content_is_python_code(self, kg):
        code = '''def hello():
    print("Hello, World!")
    return {"key": [1, 2, 3]}
'''
        kg.write("snippet", code)
        assert "def hello" in kg.cat("snippet")

    def test_content_is_json(self, kg):
        import json
        data = {"nodes": [1, 2, 3], "edges": {"a": "b"}}
        kg.write("json-data", json.dumps(data))
        recovered = json.loads(kg.cat("json-data"))
        assert recovered == data

    def test_content_is_sql(self, kg):
        sql = "SELECT * FROM nodes; DROP TABLE nodes; --"
        kg.write("evil-sql", sql)
        assert kg.cat("evil-sql") == sql
        # Graph still works
        kg.touch("proof", "works")
        assert kg.exists("proof")

    def test_content_is_yaml(self, kg):
        """Content that is valid YAML but not intended as frontmatter."""
        yaml_content = "key: value\nlist:\n  - a\n  - b"
        kg.write("yaml-body", yaml_content)
        # No frontmatter fences, so it's all body
        assert kg.frontmatter("yaml-body") == {}
        assert kg.cat("yaml-body") == yaml_content

    def test_node_name_is_a_number(self, kg):
        kg.touch("42", "the answer")
        assert kg.cat("42") == "the answer"

    def test_node_name_is_very_long(self, kg):
        name = "a" * 10000
        kg.touch(name, "long name")
        slug = slugify(name)
        assert kg.exists(slug)

    def test_node_name_with_dots(self, kg):
        kg.touch("file.txt", "text file")
        assert kg.exists("file.txt")
        assert kg.cat("file.txt") == "text file"

    def test_all_nodes_link_nowhere(self, kg):
        """Every node has dangling links."""
        for i in range(10):
            kg.write(f"island-{i}", f"See [[nonexistent-{i}]]")
        g = kg.graph()
        # No resolved links → empty graph
        assert g == {}

    def test_diamond_dependency(self, kg):
        """A → B, A → C, B → D, C → D (diamond shape)."""
        kg.write("a", "[[b]] [[c]]")
        kg.write("b", "[[d]]")
        kg.write("c", "[[d]]")
        kg.touch("d", "end")
        bl = kg.backlinks("d")
        assert sorted(bl) == ["b", "c"]
        assert sorted(kg.wikilinks("a")) == ["b", "c"]


# ══════════════════════════════════════════════════════════════════════════
# 20. Slugify edge cases
# ══════════════════════════════════════════════════════════════════════════


class TestSlugifyEdgeCases:
    def test_empty_string(self):
        assert slugify("") == "item"

    def test_only_spaces(self):
        assert slugify("   ") == "item"

    def test_only_special_chars(self):
        assert slugify("!@#$%^&*()") == "item"

    def test_preserves_dots(self):
        assert slugify("file.txt") == "file.txt"

    def test_preserves_underscores(self):
        assert slugify("hello_world") == "hello_world"

    def test_lowercases(self):
        assert slugify("HELLO") == "hello"

    def test_consecutive_separators(self):
        assert slugify("a---b") == "a-b"

    def test_leading_trailing_special(self):
        assert slugify("---hello---") == "hello"

    def test_mixed_unicode(self):
        result = slugify("café résumé")
        assert "caf" in result  # at minimum

    def test_numbers_only(self):
        assert slugify("12345") == "12345"

    def test_number_with_dots(self):
        assert slugify("3.14.159") == "3.14.159"


# ══════════════════════════════════════════════════════════════════════════
# 21. Extract wikilinks edge cases
# ══════════════════════════════════════════════════════════════════════════


class TestExtractWikilinksEdgeCases:
    def test_empty_string(self):
        assert extract_wikilinks("") == []

    def test_no_wikilinks(self):
        assert extract_wikilinks("plain text with [brackets] but not wiki") == []

    def test_single_bracket(self):
        assert extract_wikilinks("[[hello]]") == ["hello"]

    def test_multiple_on_one_line(self):
        assert extract_wikilinks("[[a]] and [[b]] and [[c]]") == ["a", "b", "c"]

    def test_nested_brackets(self):
        # [[outer [[inner]]]] - regex [^\]]+ greedily gets "outer [[inner"
        result = extract_wikilinks("[[outer [[inner]]]]")
        assert result == ["outer [[inner"]

    def test_empty_wikilink(self):
        # [[]] — regex [^\]]+ requires at least one char, so no match
        result = extract_wikilinks("[[]]")
        assert result == []

    def test_wikilink_with_spaces(self):
        assert extract_wikilinks("[[hello world]]") == ["hello world"]

    def test_wikilink_with_special_chars(self):
        assert extract_wikilinks("[[file.txt]]") == ["file.txt"]

    def test_unclosed_wikilink(self):
        assert extract_wikilinks("[[unclosed") == []

    def test_wikilink_spanning_lines(self):
        # [^\]]+ matches newlines, so this actually works
        assert extract_wikilinks("[[multi\nline]]") == ["multi\nline"]
