"""Tests for flat node CRUD: touch, write, cat, rm, mv, cp, exists, ls, tree, find, grep."""

import pytest

from kaybee.core import KnowledgeGraph


# -----------------------------------------------------------------------
# touch
# -----------------------------------------------------------------------


class TestTouch:
    def test_creates_node(self, kg):
        kg.touch("hello", "world")
        assert kg.exists("hello")
        assert kg.cat("hello") == "world"

    def test_empty_node(self, kg):
        kg.touch("empty")
        assert kg.exists("empty")
        assert kg.cat("empty") == ""

    def test_auto_slugifies(self, kg):
        kg.touch("Hello World", "content")
        assert kg.exists("hello-world")
        assert kg.cat("hello-world") == "content"

    def test_touch_existing_no_content_is_noop(self, kg):
        kg.touch("f", "original")
        kg.touch("f")  # no content
        assert kg.cat("f") == "original"

    def test_touch_existing_with_content_overwrites(self, kg):
        kg.touch("f", "old")
        kg.touch("f", "new")
        assert kg.cat("f") == "new"

    def test_returns_self(self, kg):
        assert kg.touch("a") is kg


# -----------------------------------------------------------------------
# write / cat
# -----------------------------------------------------------------------


class TestWriteCat:
    def test_write_new(self, kg):
        kg.write("readme", "hello")
        assert kg.cat("readme") == "hello"

    def test_write_overwrite(self, kg):
        kg.touch("f", "old")
        kg.write("f", "new")
        assert kg.cat("f") == "new"

    def test_write_creates_missing_node(self, kg):
        kg.write("brand-new", "data")
        assert kg.cat("brand-new") == "data"

    def test_cat_nonexistent_raises(self, kg):
        with pytest.raises(KeyError):
            kg.cat("nope")

    def test_cat_reconstructs_frontmatter(self, kg):
        kg.write("doc", "---\ntype: concept\n---\nBody.")
        result = kg.cat("doc")
        assert "type: concept" in result
        assert "Body." in result

    def test_write_returns_self(self, kg):
        assert kg.write("x", "y") is kg

    def test_write_auto_slugifies(self, kg):
        kg.write("My Note", "content")
        assert kg.exists("my-note")


# -----------------------------------------------------------------------
# exists
# -----------------------------------------------------------------------


class TestExists:
    def test_nonexistent(self, kg):
        assert not kg.exists("nope")

    def test_after_touch(self, kg):
        kg.touch("file", "x")
        assert kg.exists("file")


# -----------------------------------------------------------------------
# ls
# -----------------------------------------------------------------------


class TestLs:
    def test_no_arg_lists_types(self, kg):
        kg.add_type("concept")
        kg.add_type("person")
        assert kg.ls() == ["concept", "person"]

    def test_ls_type(self, kg):
        kg.write("a", "---\ntype: concept\n---\nA")
        kg.write("b", "---\ntype: note\n---\nB")
        result = kg.ls("concept")
        assert result == ["a"]

    def test_ls_star(self, kg):
        kg.touch("c")
        kg.touch("a")
        kg.touch("b")
        assert kg.ls("*") == ["a", "b", "c"]

    def test_ls_empty_type(self, kg):
        kg.add_type("concept")
        assert kg.ls("concept") == []

    def test_ls_no_types(self, kg):
        assert kg.ls() == []


# -----------------------------------------------------------------------
# rm
# -----------------------------------------------------------------------


class TestRm:
    def test_rm_node(self, kg):
        kg.touch("file", "x")
        kg.rm("file")
        assert not kg.exists("file")

    def test_rm_nonexistent_raises(self, kg):
        with pytest.raises(KeyError):
            kg.rm("nope")

    def test_rm_returns_self(self, kg):
        kg.touch("x")
        assert kg.rm("x") is kg


# -----------------------------------------------------------------------
# mv / cp
# -----------------------------------------------------------------------


class TestMvCp:
    def test_mv_rename(self, kg):
        kg.touch("a", "content")
        kg.mv("a", "b")
        assert not kg.exists("a")
        assert kg.cat("b") == "content"

    def test_mv_same_name_noop(self, kg):
        kg.touch("a", "x")
        kg.mv("a", "a")
        assert kg.cat("a") == "x"

    def test_mv_nonexistent_raises(self, kg):
        with pytest.raises(KeyError):
            kg.mv("nope", "dst")

    def test_mv_to_existing_raises(self, kg):
        kg.touch("a", "x")
        kg.touch("b", "y")
        with pytest.raises(FileExistsError):
            kg.mv("a", "b")

    def test_mv_auto_slugifies_dst(self, kg):
        kg.touch("a", "x")
        kg.mv("a", "My New Name")
        assert kg.exists("my-new-name")

    def test_mv_returns_self(self, kg):
        kg.touch("a", "x")
        assert kg.mv("a", "b") is kg

    def test_cp_node(self, kg):
        kg.touch("a", "content")
        kg.cp("a", "b")
        assert kg.cat("a") == "content"
        assert kg.cat("b") == "content"

    def test_cp_self_raises(self, kg):
        kg.touch("a", "x")
        with pytest.raises(ValueError):
            kg.cp("a", "a")

    def test_cp_nonexistent_raises(self, kg):
        with pytest.raises(KeyError):
            kg.cp("nope", "dst")

    def test_cp_to_existing_raises(self, kg):
        kg.touch("a", "x")
        kg.touch("b", "y")
        with pytest.raises(FileExistsError):
            kg.cp("a", "b")

    def test_cp_returns_self(self, kg):
        kg.touch("a", "x")
        assert kg.cp("a", "b") is kg


# -----------------------------------------------------------------------
# tree
# -----------------------------------------------------------------------


class TestTree:
    def test_type_grouped(self, populated_kg):
        result = populated_kg.tree()
        assert "concept/" in result
        assert "person/" in result
        assert "spreading-activation" in result
        assert "turing" in result

    def test_untyped_section(self, populated_kg):
        result = populated_kg.tree()
        assert "(untyped)" in result
        assert "readme" in result

    def test_empty_graph(self, kg):
        assert kg.tree() == ""

    def test_content_preview_truncated(self, kg):
        kg.touch("file", "x" * 100)
        result = kg.tree()
        assert "..." in result

    def test_empty_type(self, kg):
        kg.add_type("concept")
        result = kg.tree()
        assert "concept/" in result


# -----------------------------------------------------------------------
# find
# -----------------------------------------------------------------------


class TestFind:
    def test_find_all(self, kg):
        kg.touch("alpha")
        kg.touch("beta")
        result = kg.find()
        assert "alpha" in result
        assert "beta" in result

    def test_find_by_name(self, kg):
        kg.touch("readme", "hello")
        kg.touch("notes", "world")
        result = kg.find(name="readme")
        assert "readme" in result
        assert "notes" not in result

    def test_find_by_name_regex(self, kg):
        kg.touch("readme", "hello")
        kg.touch("read-more", "world")
        result = kg.find(name="^read")
        assert "readme" in result
        assert "read-more" in result

    def test_find_by_type(self, kg):
        kg.write("a", "---\ntype: concept\n---\nA")
        kg.write("b", "---\ntype: note\n---\nB")
        result = kg.find(type="concept")
        assert result == ["a"]

    def test_find_combined(self, kg):
        kg.write("alpha", "---\ntype: concept\n---\nA")
        kg.write("beta", "---\ntype: concept\n---\nB")
        kg.write("gamma", "---\ntype: note\n---\nC")
        result = kg.find(name="alpha", type="concept")
        assert result == ["alpha"]


# -----------------------------------------------------------------------
# grep
# -----------------------------------------------------------------------


class TestGrep:
    def test_grep_name(self, kg):
        kg.touch("alpha", "x")
        kg.touch("beta", "y")
        result = kg.grep("alpha")
        assert "alpha" in result

    def test_grep_content(self, kg):
        kg.touch("file", "needle in haystack")
        result = kg.grep("needle", content=True)
        assert "file" in result

    def test_grep_count(self, kg):
        kg.touch("a", "match")
        kg.touch("b", "match")
        kg.touch("c", "nope")
        assert kg.grep("match", content=True, count=True) == 2

    def test_grep_lines(self, kg):
        kg.touch("file", "line1\nfind me\nline3")
        result = kg.grep("find", lines=True)
        assert len(result) == 1
        assert ":2:" in result[0]

    def test_grep_case_insensitive(self, kg):
        kg.touch("file", "Hello World")
        result = kg.grep("hello", content=True, ignore_case=True)
        assert "file" in result

    def test_grep_case_sensitive(self, kg):
        kg.touch("file", "Hello")
        result = kg.grep("hello", content=True, ignore_case=False)
        assert "file" not in result

    def test_grep_invert(self, kg):
        kg.touch("match", "x")
        kg.touch("other", "y")
        result = kg.grep("match", invert=True)
        assert "match" not in result
        assert "other" in result

    def test_grep_no_matches(self, kg):
        kg.touch("file", "hello")
        assert kg.grep("zzz", content=True) == []

    def test_grep_by_type(self, kg):
        kg.write("a", "---\ntype: concept\n---\ndata")
        kg.write("b", "---\ntype: note\n---\ndata")
        result = kg.grep("data", type="concept", content=True)
        assert "a" in result
        assert "b" not in result

    def test_grep_lines_multiline(self, kg):
        kg.touch("file", "aaa\nbbb\naaa\nccc")
        result = kg.grep("aaa", lines=True)
        assert len(result) == 2
        assert ":1:" in result[0]
        assert ":3:" in result[1]
