"""Validation constraints for KnowledgeGraph.

A pluggable "compiler" that checks graph-level rules before publishing.

Usage::

    from kaybee.constraints import Validator, requires_link, requires_field

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

# A rule is a 3-tuple: (type_filter, check_fn, structural).
# structural=True means the rule can be checked pre-write (no DB needed).
# For backward compat, 2-tuples are accepted (defaults structural=False).
RuleTuple = tuple[str | None, ConstraintFn, bool]


class Validator:
    """Collects constraints and validates a KnowledgeGraph against them."""

    def __init__(self) -> None:
        self._rules: list[RuleTuple] = []

    def add(self, rule: tuple[str | None, ConstraintFn] | RuleTuple) -> "Validator":
        """Add a constraint rule. Returns self for chaining.

        Accepts 2-tuple ``(type_filter, check_fn)`` (backward compat,
        defaults ``structural=False``) or 3-tuple
        ``(type_filter, check_fn, structural)``.
        """
        if len(rule) == 2:
            self._rules.append((rule[0], rule[1], False))
        else:
            self._rules.append(rule)  # type: ignore[arg-type]
        return self

    def validate(self, kg: KnowledgeGraph) -> list[Violation]:
        """Run all constraints. Returns list of Violations (empty = valid)."""
        violations: list[Violation] = []
        all_nodes = kg.ls("*")

        for type_filter, check_fn, _structural in self._rules:
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

    def validate_structural(self, name: str, meta: dict) -> list[Violation]:
        """Run only structural rules against a proposed write.

        This is used by the gatekeeper to block invalid writes before they
        persist. Does NOT require a KnowledgeGraph instance for checking —
        uses ``None`` as the kg parameter since structural rules only
        inspect name/meta.
        """
        violations: list[Violation] = []
        for type_filter, check_fn, structural in self._rules:
            if not structural:
                continue
            # Check type filter against the proposed meta
            proposed_type = meta.get("type")
            if type_filter is not None and proposed_type != type_filter:
                continue
            violations.extend(check_fn(None, name, meta))  # type: ignore[arg-type]
        return violations


# ---------------------------------------------------------------------------
# Built-in constraint factories
# ---------------------------------------------------------------------------


def requires_field(type_name: str | None, field: str) -> RuleTuple:
    """Every node (of type) must have ``field`` in frontmatter."""

    def _check(kg: KnowledgeGraph, name: str, meta: dict) -> list[Violation]:
        if field not in meta or not meta[field]:
            return [Violation(name, "requires_field", f"missing field '{field}'")]
        return []

    return (type_name, _check, True)


def requires_tag(type_name: str | None) -> RuleTuple:
    """Every node (of type) must have at least one tag."""

    def _check(kg: KnowledgeGraph, name: str, meta: dict) -> list[Violation]:
        tags = meta.get("tags", [])
        if not isinstance(tags, list) or len(tags) == 0:
            return [Violation(name, "requires_tag", "must have at least one tag")]
        return []

    return (type_name, _check, True)


def requires_link(
    type_name: str | None,
    target_type: str | None = None,
) -> RuleTuple:
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

    return (type_name, _check, False)


def no_orphans(type_name: str | None = None) -> RuleTuple:
    """Every node (of type) must have at least one link in or out."""

    def _check(kg: KnowledgeGraph, name: str, meta: dict) -> list[Violation]:
        if kg.wikilinks(name) or kg.backlinks(name):
            return []
        return [Violation(name, "no_orphans", "node has no incoming or outgoing links")]

    return (type_name, _check, False)


def custom(
    type_name: str | None,
    rule_name: str,
    fn: Callable[["KnowledgeGraph", str, dict], str | None],
    structural: bool = False,
) -> RuleTuple:
    """Create a constraint from an arbitrary function.

    ``fn(kg, name, meta)`` should return an error message string, or None if valid.
    """

    def _check(kg: KnowledgeGraph, name: str, meta: dict) -> list[Violation]:
        result = fn(kg, name, meta)
        if result:
            return [Violation(name, rule_name, result)]
        return []

    return (type_name, _check, structural)


def freeze_schema(
    type_name: str,
    allowed_fields: list[str],
) -> RuleTuple:
    """Prevent nodes of *type_name* from having fields outside *allowed_fields*.

    ``"type"`` is always implicitly allowed and does not need to be listed.
    """
    allowed = set(allowed_fields) | {"type"}

    def _check(kg: KnowledgeGraph, name: str, meta: dict) -> list[Violation]:
        extra = sorted(set(meta) - allowed)
        if extra:
            return [Violation(
                name, "freeze_schema",
                f"disallowed field(s): {', '.join(extra)}",
            )]
        return []

    return (type_name, _check, True)
