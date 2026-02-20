"""
Kaybee - A flat, SQLite-native knowledge graph with YAML frontmatter and wikilinks.

Usage:
    from kaybee import KnowledgeGraph

    kg = KnowledgeGraph()
    kg.add_type("concept")
    kg.write("hello", "---\\ntype: concept\\ntags: [demo]\\n---\\nHello world.")
    kg.ls("concept")  # -> ["hello"]
    kg.wikilinks("hello")  # -> []
"""

from .core import KnowledgeGraph, extract_wikilinks, parse_frontmatter, slugify
from .sync import sync_push, sync_pull
from .shell import GraphShell, register_graph_commands, GRAPH_COMMANDS, GRAPH_HELP
from .viz import build_viz_data, visualize
from .constraints import (
    Validator,
    Violation,
    ValidationError,
    requires_field,
    requires_tag,
    requires_link,
    no_orphans,
    custom,
    freeze_schema,
)

__version__ = "0.1.0"
__all__ = [
    "KnowledgeGraph",
    "extract_wikilinks",
    "parse_frontmatter",
    "slugify",
    "GraphShell",
    "register_graph_commands",
    "GRAPH_COMMANDS",
    "GRAPH_HELP",
    "build_viz_data",
    "visualize",
    "Validator",
    "Violation",
    "ValidationError",
    "requires_field",
    "requires_tag",
    "requires_link",
    "no_orphans",
    "custom",
    "freeze_schema",
    "sync_push",
    "sync_pull",
]
