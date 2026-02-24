"""Tests for Document dataclass and make_document() factory."""

import pytest

from kaybee.core import Document, make_document, slugify


class TestDocumentConstruction:
    def test_basic_construction(self):
        doc = Document(name="hello", type="kaybee", meta={}, body="world", raw="world", refs=[])
        assert doc.name == "hello"
        assert doc.type == "kaybee"
        assert doc.meta == {}
        assert doc.body == "world"
        assert doc.raw == "world"
        assert doc.refs == []

    def test_defaults(self):
        doc = Document(name="x", type="kaybee")
        assert doc.meta == {}
        assert doc.body == ""
        assert doc.raw == ""
        assert doc.refs == []

    def test_instances_have_independent_defaults(self):
        d1 = Document(name="a", type="kaybee")
        d2 = Document(name="b", type="kaybee")
        d1.meta["key"] = "val"
        d1.refs.append("ref")
        assert d2.meta == {}
        assert d2.refs == []


class TestMakeDocumentBasic:
    def test_plain_text(self):
        doc = make_document("hello", "some body text")
        assert doc.name == "hello"
        assert doc.type == "kaybee"
        assert doc.meta == {}
        assert doc.body == "some body text"
        assert doc.raw == "some body text"
        assert doc.refs == []

    def test_empty_text(self):
        doc = make_document("empty", "")
        assert doc.name == "empty"
        assert doc.type == "kaybee"
        assert doc.meta == {}
        assert doc.body == ""
        assert doc.raw == ""
        assert doc.refs == []


class TestMakeDocumentTypeExtraction:
    def test_type_promoted_to_field(self):
        text = "---\ntype: concept\ndescription: test\n---\nBody."
        doc = make_document("node", text)
        assert doc.type == "concept"
        assert "type" not in doc.meta
        assert doc.meta == {"description": "test"}

    def test_no_type_defaults_kaybee(self):
        text = "---\ntags: [a, b]\n---\nBody."
        doc = make_document("node", text)
        assert doc.type == "kaybee"
        assert doc.meta == {"tags": ["a", "b"]}

    def test_empty_type_defaults_kaybee(self):
        text = "---\ntype: \n---\nBody."
        doc = make_document("node", text)
        assert doc.type == "kaybee"


class TestMakeDocumentRefs:
    def test_refs_extracted(self):
        text = "See [[alpha]] and [[beta]]."
        doc = make_document("note", text)
        assert "alpha" in doc.refs
        assert "beta" in doc.refs

    def test_refs_from_body_not_frontmatter(self):
        text = "---\ntype: concept\n---\nBody with [[link]]."
        doc = make_document("note", text)
        assert doc.refs == ["link"]

    def test_no_refs(self):
        doc = make_document("note", "no links here")
        assert doc.refs == []

    def test_duplicate_refs_preserved(self):
        text = "See [[a]] and [[a]] again."
        doc = make_document("note", text)
        assert doc.refs == ["a", "a"]


class TestMakeDocumentSlugify:
    def test_name_slugified(self):
        doc = make_document("Hello World", "text")
        assert doc.name == "hello-world"

    def test_already_slugified(self):
        doc = make_document("hello-world", "text")
        assert doc.name == "hello-world"

    def test_special_chars(self):
        doc = make_document("My Note (v2)", "text")
        assert doc.name == slugify("My Note (v2)")


class TestMakeDocumentEdgeCases:
    def test_unicode_body(self):
        text = "---\ntype: concept\n---\nCafé résumé naïve"
        doc = make_document("unicode", text)
        assert doc.type == "concept"
        assert "Café résumé naïve" in doc.body

    def test_unicode_name(self):
        doc = make_document("café", "text")
        assert doc.name == slugify("café")

    def test_raw_preserves_original(self):
        text = "---\ntype: concept\ntags: [a]\n---\nBody text."
        doc = make_document("node", text)
        assert doc.raw == text

    def test_frontmatter_no_closing_fence(self):
        text = "---\ntype: concept\nno closing fence"
        doc = make_document("node", text)
        assert doc.type == "kaybee"
        assert doc.body == text

    def test_complex_frontmatter(self):
        text = "---\ntype: person\nrole: researcher\nborn: 1912\ntags: [ai, math]\n---\nBio here."
        doc = make_document("turing", text)
        assert doc.type == "person"
        assert doc.meta["role"] == "researcher"
        assert doc.meta["born"] == "1912"
        assert doc.meta["tags"] == ["ai", "math"]
        assert doc.body == "Bio here."
