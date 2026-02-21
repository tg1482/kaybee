"""Tests for graph shell commands."""

import pytest

from kaybee.core import KnowledgeGraph
from kaybee.shell import (
    GRAPH_COMMANDS,
    register_graph_commands,
    _cmd_meta,
    _cmd_body,
    _cmd_links,
    _cmd_backlinks,
    _cmd_resolve,
    _cmd_schema,
    _cmd_query,
    _cmd_ls,
    _cmd_cat,
    _cmd_touch,
    _cmd_write,
    _cmd_rm,
    _cmd_mv,
    _cmd_cp,
    _cmd_tree,
    _cmd_find,
    _cmd_grep,
    _cmd_info,
    _cmd_addtype,
    _cmd_rmtype,
    _cmd_types,
    _cmd_tags,
    _cmd_help,
    _cmd_read,
)


@pytest.fixture
def graph_kg():
    kg = KnowledgeGraph()
    kg.add_type("concept")
    kg.write(
        "sa",
        "---\ntype: concept\ndescription: Spreading activation\ntags: [graph, cognition]\n---\nFollows [[at]] paths.",
    )
    kg.write(
        "at",
        "---\ntype: concept\ndescription: Agent traversal\n---\nUses [[sa]].",
    )
    return kg


class TestCmdMeta:
    def test_basic(self, graph_kg):
        result = _cmd_meta(["sa"], "", graph_kg)
        assert "type: concept" in result
        assert "description: Spreading activation" in result

    def test_no_args_raises(self, graph_kg):
        with pytest.raises(ValueError):
            _cmd_meta([], "", graph_kg)

    def test_empty_meta(self):
        kg = KnowledgeGraph()
        kg.touch("plain", "text")
        result = _cmd_meta(["plain"], "", kg)
        assert result == ""


class TestCmdBody:
    def test_basic(self, graph_kg):
        result = _cmd_body(["sa"], "", graph_kg)
        assert "Follows [[at]] paths." in result

    def test_no_args_raises(self, graph_kg):
        with pytest.raises(ValueError):
            _cmd_body([], "", graph_kg)


class TestCmdLinks:
    def test_basic(self, graph_kg):
        result = _cmd_links(["sa"], "", graph_kg)
        assert "[[at]]" in result

    def test_no_args_raises(self, graph_kg):
        with pytest.raises(ValueError):
            _cmd_links([], "", graph_kg)

    def test_unresolved_link(self):
        kg = KnowledgeGraph()
        kg.write("note", "See [[nonexistent]].")
        result = _cmd_links(["note"], "", kg)
        assert "(unresolved)" in result

    def test_no_links(self):
        kg = KnowledgeGraph()
        kg.touch("plain", "no links")
        result = _cmd_links(["plain"], "", kg)
        assert result == ""


class TestCmdBacklinks:
    def test_basic(self, graph_kg):
        result = _cmd_backlinks(["at"], "", graph_kg)
        assert "sa" in result

    def test_no_args_raises(self, graph_kg):
        with pytest.raises(ValueError):
            _cmd_backlinks([], "", graph_kg)


class TestCmdResolve:
    def test_basic(self, graph_kg):
        result = _cmd_resolve(["at"], "", graph_kg)
        assert result == "at"

    def test_exact_flag(self, graph_kg):
        result = _cmd_resolve(["at", "--exact"], "", graph_kg)
        assert result == "at"

    def test_no_args_raises(self, graph_kg):
        with pytest.raises(ValueError):
            _cmd_resolve([], "", graph_kg)

    def test_unresolvable_raises(self, graph_kg):
        with pytest.raises(KeyError):
            _cmd_resolve(["nonexistent"], "", graph_kg)


class TestCmdSchema:
    def test_basic(self, graph_kg):
        result = _cmd_schema([], "", graph_kg)
        assert "concept:" in result

    def test_empty(self):
        kg = KnowledgeGraph()
        result = _cmd_schema([], "", kg)
        assert result == ""


class TestCmdQuery:
    def test_basic(self, graph_kg):
        t = "_data"
        result = _cmd_query(["SELECT", "name", "FROM", t], "", graph_kg)
        assert "sa" in result
        assert "at" in result

    def test_no_args_raises(self, graph_kg):
        with pytest.raises(ValueError):
            _cmd_query([], "", graph_kg)


class TestCmdLs:
    def test_no_arg_lists_types(self, graph_kg):
        result = _cmd_ls([], "", graph_kg)
        assert "concept" in result

    def test_type_arg_lists_nodes(self, graph_kg):
        result = _cmd_ls(["concept"], "", graph_kg)
        assert "sa" in result
        assert "at" in result

    def test_star_lists_all(self, graph_kg):
        result = _cmd_ls(["*"], "", graph_kg)
        assert "sa" in result
        assert "at" in result


class TestCmdCat:
    def test_basic(self, graph_kg):
        result = _cmd_cat(["sa"], "", graph_kg)
        assert "Follows [[at]] paths." in result

    def test_stdin(self, graph_kg):
        result = _cmd_cat([], "hello", graph_kg)
        assert result == "hello"


class TestCmdTouchWrite:
    def test_touch(self):
        kg = KnowledgeGraph()
        _cmd_touch(["mynode", "content"], "", kg)
        assert kg.exists("mynode")

    def test_write(self):
        kg = KnowledgeGraph()
        _cmd_write(["mynode", "content"], "", kg)
        assert kg.cat("mynode") == "content"


class TestCmdRm:
    def test_basic(self):
        kg = KnowledgeGraph()
        kg.touch("x", "data")
        _cmd_rm(["x"], "", kg)
        assert not kg.exists("x")

    def test_no_args_raises(self):
        kg = KnowledgeGraph()
        with pytest.raises(ValueError):
            _cmd_rm([], "", kg)


class TestCmdMvCp:
    def test_mv(self):
        kg = KnowledgeGraph()
        kg.touch("a", "data")
        _cmd_mv(["a", "b"], "", kg)
        assert not kg.exists("a")
        assert kg.exists("b")

    def test_cp(self):
        kg = KnowledgeGraph()
        kg.touch("a", "data")
        _cmd_cp(["a", "b"], "", kg)
        assert kg.exists("a")
        assert kg.exists("b")


class TestCmdTree:
    def test_basic(self, graph_kg):
        result = _cmd_tree([], "", graph_kg)
        assert "concept/" in result


class TestCmdFind:
    def test_by_name(self, graph_kg):
        result = _cmd_find(["-name", "sa"], "", graph_kg)
        assert "sa" in result

    def test_by_type(self, graph_kg):
        result = _cmd_find(["-type", "concept"], "", graph_kg)
        assert "sa" in result
        assert "at" in result


class TestCmdGrep:
    def test_basic(self, graph_kg):
        result = _cmd_grep(["Follows", "-t", "concept"], "", graph_kg)
        assert "sa" in result

    def test_pipe_stdin(self, graph_kg):
        result = _cmd_grep(["hello"], "hello world\ngoodbye", graph_kg)
        assert "hello world" in result


class TestCmdInfo:
    def test_basic(self, graph_kg):
        result = _cmd_info(["sa"], "", graph_kg)
        assert "name: sa" in result
        assert "type: concept" in result


class TestCmdAddTypeRmType:
    def test_addtype(self):
        kg = KnowledgeGraph()
        _cmd_addtype(["idea"], "", kg)
        assert "idea" in kg.types()

    def test_rmtype(self):
        kg = KnowledgeGraph()
        kg.add_type("idea")
        _cmd_rmtype(["idea"], "", kg)
        assert "idea" not in kg.types()

    def test_rmtype_nonempty_raises(self):
        kg = KnowledgeGraph()
        kg.write("item", "---\ntype: idea\n---\nBody.")
        with pytest.raises(ValueError):
            _cmd_rmtype(["idea"], "", kg)


class TestCmdTypes:
    def test_basic(self):
        kg = KnowledgeGraph()
        kg.add_type("concept")
        kg.add_type("person")
        result = _cmd_types([], "", kg)
        assert "concept" in result
        assert "person" in result


class TestCmdTags:
    def test_node_tags(self, graph_kg):
        result = _cmd_tags(["sa"], "", graph_kg)
        assert "graph" in result
        assert "cognition" in result

    def test_all_tags(self, graph_kg):
        result = _cmd_tags([], "", graph_kg)
        assert "graph" in result


class TestCmdHelp:
    def test_basic(self, graph_kg):
        result = _cmd_help([], "", graph_kg)
        assert "Available commands:" in result
        assert "addtype" in result
        assert "tags" in result
        assert "meta" in result


class TestCmdRead:
    def test_depth_zero(self, graph_kg):
        result = _cmd_read(["sa"], "", graph_kg)
        assert result == graph_kg.cat("sa")

    def test_depth_flag(self, graph_kg):
        result = _cmd_read(["sa", "-d", "1"], "", graph_kg)
        assert "--- [[at]] ---" in result

    def test_no_args_stdin_passthrough(self, graph_kg):
        result = _cmd_read([], "piped content", graph_kg)
        assert result == "piped content"

    def test_no_args_no_stdin_raises(self, graph_kg):
        with pytest.raises(ValueError):
            _cmd_read([], "", graph_kg)

    def test_nonexistent_raises(self, graph_kg):
        with pytest.raises(KeyError):
            _cmd_read(["nonexistent"], "", graph_kg)


class TestRegister:
    def test_register_adds_all_commands(self):
        commands = {}
        register_graph_commands(commands)
        expected = {"meta", "body", "links", "backlinks", "resolve", "schema", "query",
                     "ls", "cat", "touch", "write", "rm", "mv", "cp",
                     "tree", "find", "grep", "info", "sed", "help",
                     "addtype", "rmtype", "types", "tags", "read"}
        assert expected.issubset(set(commands.keys()))

    def test_removes_dir_commands(self):
        commands = {"cd": None, "pwd": None, "mkdir": None, "du": None, "readlink": None, "ls": None}
        register_graph_commands(commands)
        assert "cd" not in commands
        assert "pwd" not in commands
        assert "mkdir" not in commands
        assert "du" not in commands
        assert "readlink" not in commands
        assert "ls" in commands  # overridden, not removed
