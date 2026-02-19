# grapy

A flat, SQLite-native knowledge graph with YAML frontmatter and wikilinks. Zero external dependencies.

## Install

```
pip install grapy
```

## Quick start

```python
from grapy import KnowledgeGraph

kg = KnowledgeGraph()
kg.add_type("concept")
kg.write("hello", "---\ntype: concept\ntags: [demo]\n---\nHello world.")
kg.ls("concept")   # -> ["hello"]
kg.tags("hello")    # -> ["demo"]
```
