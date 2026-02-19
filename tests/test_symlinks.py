"""Tests for KnowledgeGraph symlinks (ln command)."""

import pytest

from kaybee.core import KnowledgeGraph


class TestLn:
    def test_basic(self, kg):
        kg.touch("target", "data")
        kg.ln("target", "link")
        assert kg.exists("link")
        meta = kg.frontmatter("link")
        assert meta.get("link_target") == "target"

    def test_duplicate_raises(self, kg):
        kg.touch("file", "x")
        with pytest.raises(FileExistsError):
            kg.ln("target", "file")

    def test_link_meta_has_link_target(self, kg):
        kg.touch("target", "data")
        kg.ln("target", "link")
        meta = kg.frontmatter("link")
        assert meta.get("link_target") == "target"

    def test_backlinks_include_symlinks(self, kg):
        kg.touch("target", "data")
        kg.ln("target", "link1")
        kg.ln("target", "link2")
        bl = kg.backlinks("target")
        assert "link1" in bl
        assert "link2" in bl

    def test_ln_returns_self(self, kg):
        kg.touch("target", "data")
        assert kg.ln("target", "link") is kg

    def test_ln_auto_slugifies(self, kg):
        kg.touch("target", "data")
        kg.ln("target", "My Link")
        assert kg.exists("my-link")
