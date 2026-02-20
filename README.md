# kaybee

Flat, SQLite-native knowledge graph for agent memory.

- Free-form notes with YAML frontmatter + `[[wikilinks]]`
- Emergent per-type schema in SQLite tables
- Optional constraints when you need structure
- Pure core (`KnowledgeGraph`) + separate shell adapter (`GraphShell`)

## Install

```bash
pip install kaybee
```

## Quick Start

```python
from kaybee import KnowledgeGraph

kg = KnowledgeGraph("brain.db")  # or KnowledgeGraph() for in-memory

kg.write("spreading-activation", """---
type: concept
description: How activation propagates
tags: [cognition, search]
---
Uses [[agent-traversal]].""")

kg.write("agent-traversal", """---
type: concept
description: How agents navigate graphs
---
Connected to [[spreading-activation]].""")

print(kg.ls("concept"))
print(kg.wikilinks("spreading-activation"))
print(kg.backlinks("agent-traversal"))
print(kg.read("spreading-activation", depth=1))
```

## Constraints (Optional)

```python
from kaybee import KnowledgeGraph
from kaybee.constraints import Validator, freeze_schema, requires_field

kg = KnowledgeGraph()
kg.write("c1", """---
type: concept
description: OK
---
Body""")

v = Validator()
v.add(freeze_schema("concept", ["description", "tags"]))
v.add(requires_field("concept", "description"))
v.check(kg)  # raises ValidationError if invalid

kg.set_validator(v)  # block invalid future writes
```

## Shell Adapter

```python
from kaybee import GraphShell, KnowledgeGraph

kg = KnowledgeGraph()
sh = GraphShell(kg)

sh.run("touch", ["n1", "---\ntype: concept\n---\nSee [[n2]]."])
sh.run("touch", ["n2", "linked node"])

print(sh.run("links", ["n1"]))
print(sh.execute("cat n1 | grep n2 && echo done"))
```

## API Surface

`KnowledgeGraph`:
- Write/manage: `write`, `touch`, `rm`, `mv`, `cp`
- Read/query: `cat`, `body`, `frontmatter`, `read`, `info`, `query`
- Graph: `wikilinks`, `links`, `backlinks`, `graph`
- Search/index: `ls`, `find`, `grep`, `tree`, `tags`, `schema`
- Types/validation: `add_type`, `remove_type`, `types`, `set_validator`, `clear_validator`

Other exports:
- Shell: `GraphShell`, `GRAPH_COMMANDS`, `register_graph_commands`
- Constraints: `Validator`, `freeze_schema`, `requires_field`, `requires_tag`, `requires_link`, `no_orphans`, `custom`
- Viz: `visualize`

## MCP

MCP server support is not implemented in this repository yet.
