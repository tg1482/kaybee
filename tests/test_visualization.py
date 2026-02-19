"""Tests for graph_viz standalone visualization functions."""

import json
import os

import pytest

from kaybee.core import KnowledgeGraph
from kaybee.viz import build_viz_data, visualize


# -----------------------------------------------------------------------
# build_viz_data
# -----------------------------------------------------------------------


class TestBuildVizData:
    def test_structure(self, populated_kg):
        data = build_viz_data(populated_kg)
        assert "nodes" in data
        assert "wikilink_edges" in data
        assert "types" in data
        assert "all_tags" in data

    def test_nodes_contain_all_names(self, populated_kg):
        data = build_viz_data(populated_kg)
        ids = {n["id"] for n in data["nodes"]}
        assert "spreading-activation" in ids
        assert "agent-traversal" in ids
        assert "turing" in ids
        assert "readme" in ids

    def test_node_fields(self, populated_kg):
        data = build_viz_data(populated_kg)
        node = next(n for n in data["nodes"] if n["id"] == "spreading-activation")
        assert node["label"] == "spreading-activation"
        assert node["type"] == "concept"
        assert "tags" in node
        assert "graph" in node["tags"]

    def test_wikilink_edges(self, populated_kg):
        data = build_viz_data(populated_kg)
        edges = data["wikilink_edges"]
        assert any(
            e["source"] == "spreading-activation" and e["target"] == "agent-traversal"
            for e in edges
        )

    def test_types_sorted(self, populated_kg):
        data = build_viz_data(populated_kg)
        assert data["types"] == sorted(data["types"])
        assert "concept" in data["types"]
        assert "person" in data["types"]

    def test_all_tags(self, populated_kg):
        data = build_viz_data(populated_kg)
        assert "graph" in data["all_tags"]
        assert "cognition" in data["all_tags"]
        assert "nlp" in data["all_tags"]
        assert data["all_tags"] == sorted(data["all_tags"])

    def test_empty_graph(self, kg):
        data = build_viz_data(kg)
        assert data["nodes"] == []
        assert data["wikilink_edges"] == []
        assert data["types"] == []
        assert data["all_tags"] == []

    def test_unresolved_links_excluded(self, kg):
        kg.write("note", "Links to [[nonexistent]].")
        data = build_viz_data(kg)
        assert data["wikilink_edges"] == []

    def test_no_duplicate_edges(self, populated_kg):
        data = build_viz_data(populated_kg)
        edge_set = {(e["source"], e["target"]) for e in data["wikilink_edges"]}
        assert len(edge_set) == len(data["wikilink_edges"])


# -----------------------------------------------------------------------
# visualize()
# -----------------------------------------------------------------------


class TestVisualize:
    def test_returns_html(self, populated_kg):
        html = visualize(populated_kg)
        assert "<!DOCTYPE html>" in html
        assert "<canvas" in html

    def test_contains_node_data(self, populated_kg):
        html = visualize(populated_kg)
        assert "spreading-activation" in html
        assert "turing" in html

    def test_contains_both_views(self, populated_kg):
        html = visualize(populated_kg)
        assert "references" in html.lower()
        assert "tags" in html.lower()

    def test_writes_file(self, populated_kg, tmp_path):
        filepath = str(tmp_path / "graph.html")
        html = visualize(populated_kg, path=filepath)
        assert os.path.exists(filepath)
        with open(filepath) as f:
            content = f.read()
        assert content == html
        assert "<!DOCTYPE html>" in content

    def test_no_file_by_default(self, populated_kg):
        html = visualize(populated_kg)
        assert isinstance(html, str)
        assert len(html) > 0

    def test_empty_graph(self, kg):
        html = visualize(kg)
        assert "<!DOCTYPE html>" in html
        assert "<canvas" in html

    def test_data_is_valid_json_in_html(self, populated_kg):
        html = visualize(populated_kg)
        marker = "var DATA = "
        start = html.index(marker) + len(marker)
        end = html.index(";\n", start)
        data_json = html[start:end]
        data = json.loads(data_json)
        assert "nodes" in data
        assert "wikilink_edges" in data
        assert "all_tags" in data

    def test_self_contained_no_external_deps(self, populated_kg):
        html = visualize(populated_kg)
        assert "src=\"http" not in html
        assert "href=\"http" not in html

    def test_has_dark_theme(self, populated_kg):
        html = visualize(populated_kg)
        assert "#1e1e2e" in html

    def test_has_interactive_elements(self, populated_kg):
        html = visualize(populated_kg)
        assert "view-btn" in html
        assert "mousedown" in html
        assert "mousemove" in html
        assert "wheel" in html

    def test_large_graph(self, kg):
        for i in range(50):
            content = f"Node {i}"
            if i > 0:
                content += f" links to [[node-{i-1}]]"
            kg.write(f"node-{i}", f"---\ntype: item\n---\n{content}")
        html = visualize(kg)
        assert "<!DOCTYPE html>" in html
        assert "node-0" in html
        assert "node-49" in html

    def test_special_chars_in_node_names(self, kg):
        kg.touch("note-s", "it's a test")
        html = visualize(kg)
        assert "<!DOCTYPE html>" in html
        marker = "var DATA = "
        start = html.index(marker) + len(marker)
        end = html.index(";\n", start)
        data = json.loads(html[start:end])
        ids = {n["id"] for n in data["nodes"]}
        assert "note-s" in ids

    def test_file_write_creates_parent_dirs(self, populated_kg, tmp_path):
        filepath = str(tmp_path / "sub" / "dir" / "graph.html")
        os.makedirs(os.path.dirname(filepath))
        visualize(populated_kg, path=filepath)
        assert os.path.exists(filepath)
