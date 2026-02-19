"""Validation constraints for KnowledgeGraph.

A pluggable "compiler" that checks graph-level rules before publishing.

Usage::

    from grapy.constraints import Validator, requires_link, requires_field

    v = Validator()
    v.add(requires_link("paper", target_type="person"))
    v.add(requires_field("concept", "description"))

    errors = v.validate(kg)       # list of Violations
    v.check(kg)                   # raises if any violations
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .core import KnowledgeGraph


@dataclass(frozen=True)
class Violation:
    node: str
    rule: str
    message: str

    def __str__(self) -> str:
        return f"{self.node}: [{self.rule}] {self.message}"


class ValidationError(Exception):
    """Raised by Validator.check() when violations exist."""

    def __init__(self, violations: list[Violation]) -> None:
        self.violations = violations
        summary = f"{len(violations)} violation(s):\n" + "\n".join(
            f"  - {v}" for v in violations
        )
        super().__init__(summary)


# Type alias for a constraint function.
# Takes (kg, node_name, meta_dict) -> list of Violations (empty = pass).
ConstraintFn = Callable[["KnowledgeGraph", str, dict], list[Violation]]


class Validator:
    """Collects constraints and validates a KnowledgeGraph against them."""

    def __init__(self) -> None:
        self._rules: list[tuple[str | None, ConstraintFn]] = []

    def add(self, rule: tuple[str | None, ConstraintFn]) -> "Validator":
        """Add a constraint rule. Returns self for chaining."""
        self._rules.append(rule)
        return self

    def validate(self, kg: KnowledgeGraph) -> list[Violation]:
        """Run all constraints. Returns list of Violations (empty = valid)."""
        violations: list[Violation] = []
        all_nodes = kg.ls("*")

        for type_filter, check_fn in self._rules:
            if type_filter is None:
                names = all_nodes
            else:
                names = kg.ls(type_filter)

            for name in names:
                meta = kg.frontmatter(name)
                violations.extend(check_fn(kg, name, meta))

        return violations

    def check(self, kg: KnowledgeGraph) -> None:
        """Validate and raise ValidationError if any violations found."""
        violations = self.validate(kg)
        if violations:
            raise ValidationError(violations)


# ---------------------------------------------------------------------------
# Built-in constraint factories
# ---------------------------------------------------------------------------


def requires_field(type_name: str | None, field: str) -> tuple[str | None, ConstraintFn]:
    """Every node (of type) must have ``field`` in frontmatter."""

    def _check(kg: KnowledgeGraph, name: str, meta: dict) -> list[Violation]:
        if field not in meta or not meta[field]:
            return [Violation(name, "requires_field", f"missing field '{field}'")]
        return []

    return (type_name, _check)


def requires_tag(type_name: str | None) -> tuple[str | None, ConstraintFn]:
    """Every node (of type) must have at least one tag."""

    def _check(kg: KnowledgeGraph, name: str, meta: dict) -> list[Violation]:
        tags = meta.get("tags", [])
        if not isinstance(tags, list) or len(tags) == 0:
            return [Violation(name, "requires_tag", "must have at least one tag")]
        return []

    return (type_name, _check)


def requires_link(
    type_name: str | None,
    target_type: str | None = None,
) -> tuple[str | None, ConstraintFn]:
    """Every node (of type) must have at least one outgoing wikilink.

    If ``target_type`` is given, at least one link must point to a node of
    that type.
    """

    def _check(kg: KnowledgeGraph, name: str, meta: dict) -> list[Violation]:
        links = kg.wikilinks(name)
        if not links:
            msg = "must have at least one outgoing link"
            if target_type:
                msg += f" to type '{target_type}'"
            return [Violation(name, "requires_link", msg)]

        if target_type is not None:
            for link_target in links:
                resolved = kg.resolve_wikilink(link_target)
                if resolved and kg.exists(resolved):
                    target_meta = kg.frontmatter(resolved)
                    if target_meta.get("type") == target_type:
                        return []
            return [Violation(
                name, "requires_link",
                f"must link to at least one node of type '{target_type}'",
            )]

        return []

    return (type_name, _check)


def no_orphans(type_name: str | None = None) -> tuple[str | None, ConstraintFn]:
    """Every node (of type) must have at least one link in or out."""

    def _check(kg: KnowledgeGraph, name: str, meta: dict) -> list[Violation]:
        if kg.wikilinks(name) or kg.backlinks(name):
            return []
        return [Violation(name, "no_orphans", "node has no incoming or outgoing links")]

    return (type_name, _check)


def custom(
    type_name: str | None,
    rule_name: str,
    fn: Callable[["KnowledgeGraph", str, dict], str | None],
) -> tuple[str | None, ConstraintFn]:
    """Create a constraint from an arbitrary function.

    ``fn(kg, name, meta)`` should return an error message string, or None if valid.
    """

    def _check(kg: KnowledgeGraph, name: str, meta: dict) -> list[Violation]:
        result = fn(kg, name, meta)
        if result:
            return [Violation(name, rule_name, result)]
        return []

    return (type_name, _check)
