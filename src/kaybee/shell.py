"""Shell command adapter for KnowledgeGraph.

This module keeps CLI/repl command behavior separate from core graph storage logic.
"""

from __future__ import annotations

import re
import shlex
from typing import Any


def _cmd_ls(args: list[str], _stdin: str, tree: Any) -> str:
    if not args:
        return "\n".join(tree.ls())
    return "\n".join(tree.ls(args[0]))


def _cmd_cat(args: list[str], stdin: str, tree: Any) -> str:
    if not args:
        return stdin
    if len(args) == 1:
        return tree.cat(args[0])
    return "\n".join(tree.cat(a) for a in args)


def _cmd_touch(args: list[str], stdin: str, tree: Any) -> str:
    if len(args) < 1:
        raise ValueError("touch requires a name")
    name = args[0]
    content = " ".join(args[1:]) if len(args) > 1 else stdin
    tree.touch(name, content)
    return ""


def _cmd_write(args: list[str], stdin: str, tree: Any) -> str:
    if len(args) < 1:
        raise ValueError("write requires a name")
    name = args[0]
    content = " ".join(args[1:]) if len(args) > 1 else stdin
    tree.write(name, content)
    return ""


def _cmd_rm(args: list[str], _stdin: str, tree: Any) -> str:
    if not args:
        raise ValueError("rm requires a name")
    tree.rm(args[0])
    return ""


def _cmd_mv(args: list[str], _stdin: str, tree: Any) -> str:
    if len(args) != 2:
        raise ValueError("mv requires old_name and new_name")
    tree.mv(args[0], args[1])
    return ""


def _cmd_cp(args: list[str], _stdin: str, tree: Any) -> str:
    if len(args) != 2:
        raise ValueError("cp requires source and destination")
    tree.cp(args[0], args[1])
    return ""


def _cmd_tree(_args: list[str], _stdin: str, tree: Any) -> str:
    return tree.tree()


def _cmd_find(args: list[str], _stdin: str, tree: Any) -> str:
    name = None
    type_ = None

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "-name":
            if i + 1 >= len(args):
                raise ValueError("find -name requires a pattern")
            name = args[i + 1]
            i += 2
            continue
        if arg == "-type":
            if i + 1 >= len(args):
                raise ValueError("find -type requires a type name")
            type_ = args[i + 1]
            i += 2
            continue
        if arg.startswith("-"):
            raise ValueError(f"unknown find option: {arg}")
        i += 1

    return "\n".join(tree.find(name=name, type=type_))


def _cmd_grep(args: list[str], stdin: str, tree: Any) -> str:
    ignore_case = False
    invert = False
    count = False
    line_mode = False
    pattern: str | None = None
    type_filter: str | None = None
    flags_done = False

    i = 0
    while i < len(args):
        arg = args[i]

        if not flags_done:
            if arg == "--":
                flags_done = True
                i += 1
                continue
            if arg == "-t" or arg == "--type":
                if i + 1 >= len(args):
                    raise ValueError("grep -t requires a type name")
                type_filter = args[i + 1]
                i += 2
                continue
            if arg.startswith("-") and arg != "-":
                for flag in arg[1:]:
                    if flag == "i":
                        ignore_case = True
                    elif flag == "v":
                        invert = True
                    elif flag == "c":
                        count = True
                    elif flag == "n":
                        line_mode = True
                    else:
                        raise ValueError(f"unknown grep flag: -{flag}")
                i += 1
                continue

        if pattern is None:
            pattern = arg
        i += 1

    if pattern is None:
        if stdin:
            return stdin
        raise ValueError("grep requires a pattern")

    if stdin and type_filter is None:
        flags = re.IGNORECASE if ignore_case else 0
        regex = re.compile(pattern, flags)
        matched_lines = stdin.splitlines()
        if line_mode:
            result_lines = []
            for lineno, line in enumerate(matched_lines, 1):
                if bool(regex.search(line)) != invert:
                    result_lines.append(f"{lineno}:{line}")
            return "\n".join(result_lines)
        matched = [line for line in matched_lines if bool(regex.search(line)) != invert]
        if count:
            return str(len(matched))
        return "\n".join(matched)

    if line_mode:
        results = tree.grep(
            pattern,
            type=type_filter,
            ignore_case=ignore_case,
            invert=invert,
            lines=True,
        )
        return "\n".join(results)

    results = tree.grep(
        pattern,
        type=type_filter,
        content=True,
        ignore_case=ignore_case,
        invert=invert,
        count=count,
    )

    if count:
        return str(results)
    if isinstance(results, int):
        return str(results)
    return "\n".join(results)


def _cmd_info(args: list[str], _stdin: str, tree: Any) -> str:
    if not args:
        raise ValueError("info requires a name")
    info = tree.info(args[0])
    return "\n".join(f"{key}: {value}" for key, value in info.items())


def _cmd_sed(args: list[str], _stdin: str, tree: Any) -> str:
    ignore_case = False
    count = 0
    positional = []

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "-i":
            ignore_case = True
        elif arg == "-c" and i + 1 < len(args):
            count = int(args[i + 1])
            i += 1
        elif arg.startswith("-"):
            raise ValueError(f"unknown sed option: {arg}")
        else:
            positional.append(arg)
        i += 1

    if len(positional) != 3:
        raise ValueError("sed requires: name pattern replacement")

    name, pattern, replacement = positional
    content = tree.cat(name)
    flags = re.IGNORECASE if ignore_case else 0
    new_content = re.sub(pattern, replacement, content, count=count, flags=flags)
    tree.write(name, new_content)
    return ""


def _cmd_meta(args: list[str], _stdin: str, tree: Any) -> str:
    if not args:
        raise ValueError("meta requires a name")
    meta = tree.frontmatter(args[0])
    return "\n".join(f"{k}: {v}" for k, v in meta.items())


def _cmd_body(args: list[str], _stdin: str, tree: Any) -> str:
    if not args:
        raise ValueError("body requires a name")
    return tree.body(args[0])


def _cmd_links(args: list[str], _stdin: str, tree: Any) -> str:
    if not args:
        raise ValueError("links requires a name")
    name = args[0]
    out_lines = []
    for target, resolved in tree.links(name):
        if resolved:
            out_lines.append(f"[[{target}]] -> {resolved}")
        else:
            out_lines.append(f"[[{target}]] -> (unresolved)")
    return "\n".join(out_lines)


def _cmd_backlinks(args: list[str], _stdin: str, tree: Any) -> str:
    if not args:
        raise ValueError("backlinks requires a name")
    results = tree.backlinks(args[0])
    return "\n".join(results)


def _cmd_resolve(args: list[str], _stdin: str, tree: Any) -> str:
    if not args:
        raise ValueError("resolve requires a name")
    exact = "--exact" in args
    name = args[0]
    result = tree.resolve_wikilink(name, fuzzy=not exact)
    if result is None:
        raise KeyError(f"Cannot resolve: {name}")
    return result


def _cmd_schema(_args: list[str], _stdin: str, tree: Any) -> str:
    s = tree.schema()
    out_lines = []
    for type_name, keys in sorted(s.items()):
        out_lines.append(f"{type_name}: {', '.join(keys) if keys else '(no fields)'}")
    return "\n".join(out_lines)


def _cmd_query(args: list[str], _stdin: str, tree: Any) -> str:
    if not args:
        raise ValueError("query requires SQL")
    sql = " ".join(args)
    rows = tree.query(sql)
    return "\n".join("\t".join(str(c) for c in row) for row in rows)


def _cmd_addtype(args: list[str], _stdin: str, tree: Any) -> str:
    if not args:
        raise ValueError("addtype requires a type name")
    tree.add_type(args[0])
    return ""


def _cmd_rmtype(args: list[str], _stdin: str, tree: Any) -> str:
    if not args:
        raise ValueError("rmtype requires a type name")
    tree.remove_type(args[0])
    return ""


def _cmd_types(_args: list[str], _stdin: str, tree: Any) -> str:
    return "\n".join(tree.types())


def _cmd_tags(args: list[str], _stdin: str, tree: Any) -> str:
    if args:
        tag_list = tree.tags(args[0])
        return "\n".join(tag_list) if isinstance(tag_list, list) else ""
    tag_map = tree.tags()
    out_lines = []
    for tag, names in sorted(tag_map.items()):
        out_lines.append(f"{tag}: {', '.join(sorted(names))}")
    return "\n".join(out_lines)


def _cmd_read(args: list[str], stdin: str, tree: Any) -> str:
    depth = 0
    name: str | None = None

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "-d" and i + 1 < len(args):
            depth = int(args[i + 1])
            i += 2
            continue
        if name is None:
            name = arg
        i += 1

    if name is None:
        if stdin:
            return stdin
        raise ValueError("read requires a name")

    return tree.read(name, depth=depth)


def _cmd_echo(args: list[str], _stdin: str, _tree: Any) -> str:
    return " ".join(args)


def _cmd_printf(args: list[str], _stdin: str, _tree: Any) -> str:
    if not args:
        return ""
    fmt = args[0]
    values: tuple[Any, ...] = tuple(args[1:])
    try:
        return fmt % values if values else fmt
    except (TypeError, ValueError):
        return " ".join(args)


def _cmd_help(_args: list[str], _stdin: str, _tree: Any) -> str:
    return """Available commands:
  ls [type|*]           List types or nodes of a type
  cat <name>            Show node content
  touch <name> [content]  Create node
  write <name> [content]  Write to node
  rm <name>             Remove node
  mv <old> <new>        Rename node
  cp <src> <dst>        Copy node
  tree                  Type-grouped view
  find [-name regex] [-type type]
  grep <pattern> [-t type] [-i] [-v] [-c] [-n]
  info <name>           Show node metadata
  sed <name> <pat> <rep> [-i] [-c n]

  addtype <type>        Register a type
  rmtype <type>         Unregister a type (must be empty)
  types                 List registered types
  tags [name]           Show tags for a node or all tags

  meta <name>           Show frontmatter key-value pairs
  body <name>           Show content without frontmatter
  links <name>          Show outgoing [[wikilinks]]
  backlinks <name>      Show what points TO this node
  resolve <name> [--exact]  Resolve a wikilink name
  schema                Show all types and their fields
  query <sql>           Run SQL query

  read <name> [-d depth]  Read node with linked content
  echo <text>           Print text
  printf <fmt> [args]   Print formatted text
  help                  Show this help

Command chaining:
  cmd1 | cmd2           Pipe output
  cmd1 ; cmd2           Sequential (continue on failure)
  cmd1 && cmd2          Sequential (stop on failure)
  cmd1 || cmd2          Run cmd2 only if cmd1 fails"""


GRAPH_COMMANDS: dict[str, Any] = {
    "ls": _cmd_ls,
    "cat": _cmd_cat,
    "touch": _cmd_touch,
    "write": _cmd_write,
    "rm": _cmd_rm,
    "mv": _cmd_mv,
    "cp": _cmd_cp,
    "tree": _cmd_tree,
    "find": _cmd_find,
    "grep": _cmd_grep,
    "info": _cmd_info,
    "sed": _cmd_sed,
    "help": _cmd_help,
    "meta": _cmd_meta,
    "body": _cmd_body,
    "links": _cmd_links,
    "backlinks": _cmd_backlinks,
    "resolve": _cmd_resolve,
    "schema": _cmd_schema,
    "query": _cmd_query,
    "addtype": _cmd_addtype,
    "rmtype": _cmd_rmtype,
    "types": _cmd_types,
    "tags": _cmd_tags,
    "read": _cmd_read,
    "echo": _cmd_echo,
    "printf": _cmd_printf,
}

GRAPH_HELP = """
Graph commands (KnowledgeGraph):
  meta <name>              Show frontmatter key-value pairs
  body <name>              Show content without frontmatter
  links <name>             Show outgoing [[wikilinks]]
  backlinks <name>         Show what points TO this node
  resolve <name> [--exact] Resolve a wikilink name
  schema                   Show all types and their fields
  query <sql>              Run SQL query
  addtype <type>           Register a type
  rmtype <type>            Unregister a type
  types                    List registered types
  tags [name]              Show tags
  read <name> [-d depth]   Read node with linked content
"""


def register_graph_commands(commands: dict[str, Any]) -> None:
    """Merge graph commands into a shell COMMANDS dict.

    Overrides base commands (ls, cat, etc.) with graph-aware versions
    and removes directory-based commands that don't apply.
    """
    commands.update(GRAPH_COMMANDS)
    for cmd in ("cd", "pwd", "mkdir", "du", "readlink"):
        commands.pop(cmd, None)


class GraphShell:
    """REPL-friendly command interface over a KnowledgeGraph instance."""

    def __init__(self, graph: Any, commands: dict[str, Any] | None = None) -> None:
        self.graph = graph
        self.commands = commands or GRAPH_COMMANDS

    def run(self, command: str, args: list[str] | None = None, stdin: str = "") -> str:
        argv = args or []
        if command not in self.commands:
            raise ValueError(f"unknown command: {command}")
        return self.commands[command](argv, stdin, self.graph)

    def execute(self, line: str, stdin: str = "") -> str:
        output, _exit_code = self.execute_with_status(line, stdin)
        return output

    def execute_with_status(self, line: str, stdin: str = "") -> tuple[str, int]:
        clauses = self._parse_line(line)
        if not clauses:
            return "", 0

        last_output = ""
        last_success = True

        for op, pipeline in clauses:
            if op == "&&" and not last_success:
                continue
            if op == "||" and last_success:
                continue

            last_output, last_success = self._run_pipeline(pipeline, stdin)
            stdin = ""

        return last_output, 0 if last_success else 1

    def _run_pipeline(self, pipeline: list[list[str]], stdin: str) -> tuple[str, bool]:
        stream = stdin
        for argv in pipeline:
            if not argv:
                continue
            cmd, args = argv[0], argv[1:]
            try:
                stream = self.run(cmd, args, stream)
            except Exception as exc:
                return str(exc), False
        return stream, True

    @staticmethod
    def _tokenize(line: str) -> list[str]:
        lexer = shlex.shlex(line, posix=True, punctuation_chars="|&;")
        lexer.whitespace_split = True
        raw = list(lexer)
        merged: list[str] = []
        i = 0
        while i < len(raw):
            tok = raw[i]
            if tok in {"&", "|"} and i + 1 < len(raw) and raw[i + 1] == tok:
                merged.append(tok + tok)
                i += 2
                continue
            merged.append(tok)
            i += 1
        return merged

    def _parse_line(self, line: str) -> list[tuple[str | None, list[list[str]]]]:
        tokens = self._tokenize(line)
        if not tokens:
            return []

        clauses: list[tuple[str | None, list[list[str]]]] = []
        current_pipe: list[list[str]] = []
        current_cmd: list[str] = []
        next_op: str | None = None

        def flush_command() -> None:
            nonlocal current_cmd
            if current_cmd:
                current_pipe.append(current_cmd)
                current_cmd = []

        def flush_clause() -> None:
            nonlocal current_pipe, next_op
            flush_command()
            if current_pipe:
                clauses.append((next_op, current_pipe))
                current_pipe = []
                next_op = None

        for tok in tokens:
            if tok == "|":
                flush_command()
                continue
            if tok in {";", "&&", "||"}:
                flush_clause()
                next_op = tok
                continue
            current_cmd.append(tok)

        flush_clause()
        return clauses


__all__ = [
    "GraphShell",
    "GRAPH_COMMANDS",
    "GRAPH_HELP",
    "register_graph_commands",
    "_cmd_ls",
    "_cmd_cat",
    "_cmd_touch",
    "_cmd_write",
    "_cmd_rm",
    "_cmd_mv",
    "_cmd_cp",
    "_cmd_tree",
    "_cmd_find",
    "_cmd_grep",
    "_cmd_info",
    "_cmd_sed",
    "_cmd_meta",
    "_cmd_body",
    "_cmd_links",
    "_cmd_backlinks",
    "_cmd_resolve",
    "_cmd_schema",
    "_cmd_query",
    "_cmd_addtype",
    "_cmd_rmtype",
    "_cmd_types",
    "_cmd_tags",
    "_cmd_read",
    "_cmd_help",
]
