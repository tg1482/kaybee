# kaybee

Structured knowledge for agents. Zero dependencies. One SQLite file.

<!-- TODO: replace with actual screenshot -->
![graph visualization](assets/graph.png)

## Why

kaybee is free-form by default — like Obsidian, but for agents. Write nodes with YAML frontmatter, link them with `[[wikilinks]]` inline in your text, and the graph builds itself. No schema to define upfront, no structure imposed.

When you *want* structure, you add it through **constraints**. Freeze a type's schema so agents can't add unplanned fields. Require every paper to link to a person. Ban orphan nodes. Constraints are opt-in rules that compile your free-form graph into something reliable.

## How it works

**Typed nodes with emergent schemas.** Every node belongs to a type. Each type gets its own SQL table, and the schema evolves automatically as you add frontmatter fields. Write a `concept` with `description` and `tags`, then later write one with `difficulty` — the schema expands.

```python
kg.write("spreading-activation", """---
type: concept
description: How activation propagates through a network
tags: [cognition, search]
---
Follows [[agent-traversal]] paths and uses [[semantic-similarity]].""")
```

**Inline wikilinks.** `[[double-bracket]]` links live inside sentences — `"Follows [[agent-traversal]] paths"` — so an agent can summon linked knowledge on demand. kaybee extracts them automatically and tracks outgoing links, backlinks, and fuzzy resolution.

**Read with depth.** An agent doesn't always need the full graph — just the neighborhood around a node. `read("spreading-activation", depth=1)` returns the node's content plus the content of every node it links to. Increase depth for wider context. Cycles and diamonds are handled automatically.

```python
kg.read("spreading-activation", depth=0)  # same as cat() — just this node
kg.read("spreading-activation", depth=1)  # this node + direct links
kg.read("spreading-activation", depth=2)  # two hops out
```

**Constraints.** The graph is free-form until you say otherwise. `freeze_schema` locks a type's allowed fields. `requires_field`, `requires_link`, and `no_orphans` enforce structural rules. `custom()` lets you write arbitrary checks. Compose them into a `Validator` and run it like a compiler pass.

```python
v = Validator()
v.add(freeze_schema("concept", ["description", "tags"]))  # no surprise fields
v.add(requires_field("concept", "description"))
v.add(requires_link("paper", target_type="person"))
v.add(no_orphans())
v.check(kg)  # raises ValidationError with all violations
```

## Install

```
pip install kaybee
```

## Quick start

```python
from kaybee import KnowledgeGraph, visualize

kg = KnowledgeGraph("brain.db")  # or KnowledgeGraph() for in-memory

# Typed nodes with frontmatter
kg.write("spreading-activation", """---
type: concept
description: How activation propagates through a network
tags: [cognition, search]
---
Follows [[agent-traversal]] paths and uses [[semantic-similarity]].""")

kg.write("agent-traversal", """---
type: concept
description: How agents navigate graph structures
tags: [agents, ai]
---
Combined with [[spreading-activation]] for discovery.""")

kg.write("turing", """---
type: person
role: researcher
born: 1912
---
Pioneered computation and [[agent-traversal]].""")

# Query
kg.ls("concept")                 # ['agent-traversal', 'spreading-activation']
kg.wikilinks("turing")           # ['agent-traversal']
kg.backlinks("agent-traversal")  # ['spreading-activation', 'turing']
kg.frontmatter("turing")         # {'type': 'person', 'role': 'researcher', 'born': '1912'}
kg.schema()                      # {'concept': ['description', 'tags'], 'person': ['role', 'born']}
kg.graph()                       # {'spreading-activation': ['agent-traversal', ...], ...}

# Read with depth — agent pulls in neighborhood context
kg.read("spreading-activation", depth=1)
# Returns this node's content + content of agent-traversal and semantic-similarity

# Visualize — self-contained interactive HTML
visualize(kg, path="graph.html")
```

### MCP server

MCP server support is not implemented in this repository yet.

### Shell commands

```python
from kaybee import GraphShell, KnowledgeGraph

kg = KnowledgeGraph()
sh = GraphShell(kg)

sh.run("touch", ["neuron", "---\ntype: concept\n---\nA unit of [[computation]]."])
sh.run("ls", ["concept"])     # "neuron"
sh.run("links", ["neuron"])   # "[[computation]] -> (unresolved)"
sh.run("schema")              # "concept: (no fields)"

# Includes simple command-line chaining and pipes
sh.execute("cat neuron | grep computation && echo done")
```

## API

| Method | Description |
|---|---|
| `write(name, content)` | Create or overwrite node |
| `touch(name, content="")` | Create if not exists |
| `cat(name)` / `body(name)` / `frontmatter(name)` | Read content, body, or metadata |
| `read(name, depth=0)` | Read node + linked content to N hops |
| `rm(name)` / `mv(old, new)` / `cp(src, dst)` | Delete, rename, copy |
| `ls(type)` / `find(name, type)` / `grep(pattern)` | Search |
| `tree()` | Type-grouped view |
| `wikilinks(name)` / `backlinks(name)` | Link traversal |
| `graph()` | Full adjacency dict |
| `tags(name)` / `schema()` / `info(name)` | Metadata |
| `query(sql, params)` | Raw SQL |
| `add_type(name)` / `remove_type(name)` / `types()` | Type registry |
| `GraphShell(graph)` | Shell/REPL command adapter |
| `visualize(kg, path)` | Interactive HTML graph |
| `freeze_schema(type, fields)` | Lock allowed frontmatter fields |

## Inspired by

- [Loopy](https://github.com/tg1482/loopy) — filesystem-like tree API
- [Skill graphs](https://github.com/arscontexta/SKILL.md) — structured knowledge networks for agents

## License

MIT
