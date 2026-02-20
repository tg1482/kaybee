# kaybee

Structured knowledge for agents. Zero dependencies. One SQLite file.

## What it is

A knowledge graph stored in SQLite. Nodes have YAML frontmatter, link to each other with `[[wikilinks]]`, and self-organize into typed tables. No schema upfront — it emerges from the data you write.

```python
from kaybee import KnowledgeGraph

kg = KnowledgeGraph("brain.db")

kg.write("spreading-activation", """---
type: concept
description: How activation propagates through a network
tags: [cognition, search]
---
Follows [[agent-traversal]] paths and uses [[semantic-similarity]].""")

kg.write("turing", """---
type: person
role: researcher
born: 1912
---
Pioneered computation and [[agent-traversal]].""")
```

That's it. `concept` and `person` tables now exist. Links are tracked. Backlinks resolve automatically.

## Storage modes

kaybee has two storage layouts. The API is identical — only the internal SQL changes.

### Multi mode (default)

```python
kg = KnowledgeGraph("brain.db")  # or mode="multi"
```

One SQL table per type: `concept`, `person`, `kaybee` (for untyped nodes). Each table has columns matching that type's frontmatter fields. Good for inspecting types independently.

### Single mode

```python
kg = KnowledgeGraph("brain.db", mode="single")
```

One unified `_data` table for all nodes. Columns are the union of all types' fields — rows have NULLs for fields that don't belong to their type. A `_type_fields` table tracks which fields belong to which type. Good for cross-type queries.

The mode is locked into the database file on first use. Reopening with the wrong mode raises `ValueError`.

### What changes between modes

The write path is the same in both modes: parse frontmatter, update the `nodes` index, upsert data, sync wikilinks. The difference is where data lands.

| Operation | Multi | Single |
|---|---|---|
| Write typed node | Row in `concept` table | Row in `_data` table |
| Write untyped node | Row in `kaybee` table | Row in `_data` table |
| Change type (concept → note) | Delete from `concept`, insert into `note` | Update in place in `_data` |
| Schema tracking | `PRAGMA table_info(concept)` | `_type_fields` table |
| Cross-type query | `UNION ALL` across tables | Single `SELECT` on `_data` |

```python
# Use data_table() to get the right table name for raw SQL
table = kg.data_table("concept")  # "concept" in multi, "_data" in single
kg.query(f"SELECT name, description FROM {table}")
```

## Core operations

```python
# Write and read
kg.write("name", "---\ntype: concept\n---\nBody text with [[links]].")
kg.cat("name")              # full content (frontmatter + body)
kg.body("name")             # body only
kg.frontmatter("name")      # metadata dict
kg.read("name", depth=1)    # this node + content of linked nodes

# Organize
kg.touch("name")             # create if not exists
kg.rm("name")                # delete
kg.mv("old", "new")          # rename
kg.cp("src", "dst")          # copy

# Search
kg.ls("concept")             # nodes of type
kg.find(name="activ.*")      # regex on names
kg.grep("pattern", content=True)  # regex across content
kg.tags()                    # {tag: [node, ...]} mapping

# Graph
kg.wikilinks("name")         # outgoing link targets
kg.backlinks("name")         # who links here
kg.graph()                   # full adjacency dict
kg.schema()                  # {type: [fields]} across all types

# Raw SQL
kg.query("SELECT name FROM nodes WHERE type = ?", ("concept",))
```

## Constraints

Free-form by default. Add structure when you want it.

```python
from kaybee import Validator, freeze_schema, requires_field, requires_link, no_orphans

v = Validator()
v.add(freeze_schema("concept", ["description", "tags"]))
v.add(requires_field("concept", "description"))
v.add(requires_link("paper", target_type="person"))
v.add(no_orphans())

v.check(kg)          # raises ValidationError with all violations
kg.set_validator(v)  # gatekeeper: blocks invalid writes before they persist
```

## Shell

```python
from kaybee import GraphShell

sh = GraphShell(kg)
sh.run("touch", ["neuron", "---\ntype: concept\n---\nA unit of [[computation]]."])
sh.run("ls", ["concept"])
sh.run("links", ["neuron"])
sh.execute("cat neuron | grep computation")
```

## Visualization

```python
from kaybee import visualize

visualize(kg, path="graph.html")  # self-contained interactive HTML
```

## Install

```
pip install kaybee
```

## License

MIT
