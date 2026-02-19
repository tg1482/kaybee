# kaybee

Structured knowledge for agents. Zero dependencies. One SQLite file.

<!-- TODO: replace with actual screenshot -->
![graph visualization](assets/graph.png)

## Why

A single skill file can summarize, review code, or follow a checklist. But real depth — a therapy agent that draws on CBT patterns, attachment theory, and emotional regulation frameworks — requires interconnected knowledge that no single file can hold.

kaybee gives you a knowledge graph where every node has a **type**, every type builds its own **schema** from frontmatter, nodes connect through **wikilinks** embedded in prose, and a **validator** enforces structural rules across the whole graph. One SQLite file, zero dependencies.

## How it works

**Typed nodes with emergent schemas.** Every node belongs to a type. Each type gets its own SQL table, and the schema evolves automatically as you add frontmatter fields. Write a `concept` with `description` and `tags`, then later write one with `difficulty` — the schema expands. Query any type's fields with `kg.schema()`.

```python
kg.write("spreading-activation", """---
type: concept
description: How activation propagates through a network
tags: [cognition, search]
---
Follows [[agent-traversal]] paths and uses [[semantic-similarity]].""")
```

**Wikilinks as prose.** Links aren't metadata — they're woven into sentences, so they carry meaning. An agent reads "Follows [[agent-traversal]] paths" and knows *why* to follow that link. kaybee tracks outgoing links, backlinks, and resolution (including fuzzy matching) automatically.

**Validation as compilation.** The `Validator` enforces graph-level constraints — every paper must link to a person, every concept needs a description, no orphan nodes. Built-in rules compose, and `custom()` lets you write arbitrary checks. Think of it as a compiler for your knowledge graph: it catches structural problems before they matter.

```python
v = Validator()
v.add(requires_field("concept", "description"))
v.add(requires_link("paper", target_type="person"))
v.add(no_orphans())
v.add(custom("concept", "has-examples",
    lambda kg, name, meta: "needs examples section"
    if "## Examples" not in kg.body(name) else None))
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

# Visualize — self-contained interactive HTML
visualize(kg, path="graph.html")
```

### MCP server

kaybee ships as a [Loopy](https://github.com/tg1482/loopy) MCP tool:

```json
{
  "mcpServers": {
    "kaybee": {
      "command": "uvx",
      "args": ["--from", "loopy", "loopy-mcp"]
    }
  }
}
```

### Shell commands

```python
from kaybee import KnowledgeGraph, GRAPH_COMMANDS

kg = KnowledgeGraph()
run = lambda cmd, args=[], stdin="": GRAPH_COMMANDS[cmd](args, stdin, kg)

run("touch", ["neuron", "---\ntype: concept\n---\nA unit of [[computation]]."])
run("ls", ["concept"])     # "neuron"
run("links", ["neuron"])   # "[[computation]] -> (unresolved)"
run("schema")              # "concept: (no fields)"
```

## API

| Method | Description |
|---|---|
| `write(name, content)` | Create or overwrite node |
| `touch(name, content="")` | Create if not exists |
| `cat(name)` / `body(name)` / `frontmatter(name)` | Read content, body, or metadata |
| `rm(name)` / `mv(old, new)` / `cp(src, dst)` | Delete, rename, copy |
| `ln(source, dest)` | Symlink |
| `ls(type)` / `find(name, type)` / `grep(pattern)` | Search |
| `tree()` | Type-grouped view |
| `wikilinks(name)` / `backlinks(name)` | Link traversal |
| `graph()` | Full adjacency dict |
| `tags(name)` / `schema()` / `info(name)` | Metadata |
| `query(sql, params)` | Raw SQL |
| `add_type(name)` / `remove_type(name)` / `types()` | Type registry |
| `visualize(kg, path)` | Interactive HTML graph |

## Inspired by

- [Loopy](https://github.com/tg1482/loopy) — filesystem-like tree API
- [Skill graphs](https://github.com/arscontexta/SKILL.md) — structured knowledge networks for agents

## License

MIT
