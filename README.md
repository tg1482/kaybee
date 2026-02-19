# kaybee

A flat, SQLite-native knowledge graph with YAML frontmatter and wikilinks. Zero external dependencies.

## Install

```
pip install kaybee
```

## Quick start

```python
from kaybee import KnowledgeGraph

kg = KnowledgeGraph()
kg.add_type("concept")
kg.write("hello", "---\ntype: concept\ntags: [demo]\n---\nHello world.")
kg.ls("concept")   # -> ["hello"]
kg.tags("hello")    # -> ["demo"]
```
