# kaybee

Flat, SQLite-native knowledge graph for agent memory.

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

That's it. Types are tracked, links are resolved, backlinks work automatically.

Internally, all node data lives in a single `_data` table. A `_type_fields` table tracks which columns belong to which type. The `nodes` table is a thin index of name + type.

```python
# Raw SQL is available when you need it
kg.query("SELECT name, description FROM _data WHERE name = ?", ("spreading-activation",))
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

```bash
pip install kaybee
```

## License

MIT
