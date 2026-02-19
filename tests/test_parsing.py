"""Tests for YAML frontmatter parsing and wikilink extraction."""

import pytest

from grapy.core import (
    _parse_yaml_subset,
    extract_wikilinks,
    parse_frontmatter,
)


# -----------------------------------------------------------------------
# _parse_yaml_subset
# -----------------------------------------------------------------------


class TestParseYamlSubset:
    def test_simple_key_value(self):
        assert _parse_yaml_subset("key: value") == {"key": "value"}

    def test_multiple_keys(self):
        result = _parse_yaml_subset("a: 1\nb: 2")
        assert result == {"a": "1", "b": "2"}

    def test_inline_list(self):
        result = _parse_yaml_subset("tags: [graph, cognition]")
        assert result == {"tags": ["graph", "cognition"]}

    def test_empty_inline_list(self):
        assert _parse_yaml_subset("tags: []") == {"tags": []}

    def test_block_list(self):
        result = _parse_yaml_subset("tags:\n  - alpha\n  - beta")
        assert result == {"tags": ["alpha", "beta"]}

    def test_nested_dict(self):
        result = _parse_yaml_subset("meta:\n  sub: val\n  other: thing")
        assert result == {"meta": {"sub": "val", "other": "thing"}}

    def test_double_quoted(self):
        assert _parse_yaml_subset('name: "hello world"') == {"name": "hello world"}

    def test_single_quoted(self):
        assert _parse_yaml_subset("name: 'hello world'") == {"name": "hello world"}

    def test_inline_comment_stripped(self):
        assert _parse_yaml_subset("key: value # comment") == {"key": "value"}

    def test_blank_lines_skipped(self):
        assert _parse_yaml_subset("a: 1\n\nb: 2") == {"a": "1", "b": "2"}

    def test_comment_lines_skipped(self):
        assert _parse_yaml_subset("# top comment\na: 1") == {"a": "1"}

    def test_empty_string(self):
        assert _parse_yaml_subset("") == {}

    def test_only_comments(self):
        assert _parse_yaml_subset("# comment 1\n# comment 2") == {}

    def test_colon_in_value(self):
        result = _parse_yaml_subset("url: http://example.com")
        assert result == {"url": "http://example.com"}

    def test_quoted_list_items(self):
        result = _parse_yaml_subset('items: ["hello world", "foo bar"]')
        assert result == {"items": ["hello world", "foo bar"]}

    def test_block_list_with_comments(self):
        yaml = "tags:\n  - alpha\n  # skip me\n  - beta"
        result = _parse_yaml_subset(yaml)
        assert result == {"tags": ["alpha", "beta"]}

    def test_multiple_types_mixed(self):
        yaml = "type: concept\ntags: [a, b]\nmeta:\n  sub: val"
        result = _parse_yaml_subset(yaml)
        assert result["type"] == "concept"
        assert result["tags"] == ["a", "b"]
        assert result["meta"] == {"sub": "val"}

    def test_no_colon_line_ignored(self):
        result = _parse_yaml_subset("no colon here\nkey: val")
        assert result == {"key": "val"}


# -----------------------------------------------------------------------
# parse_frontmatter
# -----------------------------------------------------------------------


class TestParseFrontmatter:
    def test_standard_frontmatter(self):
        text = "---\ntype: concept\ntitle: Hello\n---\nBody text here."
        meta, body = parse_frontmatter(text)
        assert meta == {"type": "concept", "title": "Hello"}
        assert body == "Body text here."

    def test_no_frontmatter(self):
        meta, body = parse_frontmatter("Just plain text.")
        assert meta == {}
        assert body == "Just plain text."

    def test_no_closing_fence(self):
        text = "---\ntype: concept\nNo closing fence"
        meta, body = parse_frontmatter(text)
        assert meta == {}
        assert body == text

    def test_empty_frontmatter(self):
        meta, body = parse_frontmatter("---\n---\nBody.")
        assert meta == {}
        assert body == "Body."

    def test_frontmatter_with_list(self):
        text = "---\ntype: concept\ntags: [a, b, c]\n---\nContent."
        meta, body = parse_frontmatter(text)
        assert meta["tags"] == ["a", "b", "c"]
        assert body == "Content."

    def test_empty_string(self):
        meta, body = parse_frontmatter("")
        assert meta == {}
        assert body == ""

    def test_only_fences_no_body(self):
        meta, body = parse_frontmatter("---\ntype: x\n---\n")
        assert meta == {"type": "x"}
        assert body == ""

    def test_multiple_fence_markers(self):
        text = "---\ntype: a\n---\nBody with ---\nmore text."
        meta, body = parse_frontmatter(text)
        assert meta["type"] == "a"
        assert "---" in body

    def test_frontmatter_preserves_body_newlines(self):
        text = "---\ntype: x\n---\nline1\nline2\nline3"
        _, body = parse_frontmatter(text)
        assert body == "line1\nline2\nline3"


# -----------------------------------------------------------------------
# extract_wikilinks
# -----------------------------------------------------------------------


class TestExtractWikilinks:
    def test_single_link(self):
        assert extract_wikilinks("See [[foo]] for details") == ["foo"]

    def test_multiple_links(self):
        assert extract_wikilinks("[[a]] and [[b]]") == ["a", "b"]

    def test_no_links(self):
        assert extract_wikilinks("plain text") == []

    def test_link_with_spaces(self):
        assert extract_wikilinks("[[Agent Traversal]]") == ["Agent Traversal"]

    def test_empty_string(self):
        assert extract_wikilinks("") == []

    def test_nested_brackets_ignored(self):
        result = extract_wikilinks("[[foo]]")
        assert result == ["foo"]

    def test_duplicate_links(self):
        result = extract_wikilinks("[[a]] then [[a]] again")
        assert result == ["a", "a"]

    def test_link_with_hyphens(self):
        assert extract_wikilinks("[[my-concept]]") == ["my-concept"]

    def test_link_at_start_and_end(self):
        result = extract_wikilinks("[[start]] middle [[end]]")
        assert result == ["start", "end"]

    def test_multiline(self):
        text = "line1 [[a]]\nline2 [[b]]"
        assert extract_wikilinks(text) == ["a", "b"]

    def test_unclosed_bracket(self):
        assert extract_wikilinks("[[unclosed") == []

    def test_empty_brackets(self):
        assert extract_wikilinks("[[]]") == []
