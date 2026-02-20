"""Tests for graph_constraints validator."""

import pytest

from kaybee.core import KnowledgeGraph
from kaybee.constraints import (
    ValidationError,
    Validator,
    Violation,
    custom,
    freeze_schema,
    no_orphans,
    requires_field,
    requires_link,
    requires_tag,
)


@pytest.fixture(params=["multi", "single"])
def kg(request):
    return KnowledgeGraph(mode=request.param)


@pytest.fixture
def populated_kg(kg):
    kg.add_type("concept")
    kg.add_type("person")
    kg.write("sa", "---\ntype: concept\ndescription: Spreading activation\ntags: [graph]\n---\nUses [[at]].")
    kg.write("at", "---\ntype: concept\ndescription: Agent traversal\ntags: [graph]\n---\nUses [[sa]].")
    kg.write("turing", "---\ntype: person\nrole: pioneer\ntags: [ai]\n---\nCreated [[at]].")
    return kg


class TestViolation:
    def test_str(self):
        v = Violation("my-node", "requires_field", "missing field 'description'")
        assert "my-node" in str(v)
        assert "requires_field" in str(v)
        assert "description" in str(v)

    def test_frozen(self):
        v = Violation("a", "r", "m")
        with pytest.raises(AttributeError):
            v.node = "b"


class TestValidatorBasics:
    def test_empty_validator_passes(self, populated_kg):
        v = Validator()
        assert v.validate(populated_kg) == []

    def test_check_passes_silently(self, populated_kg):
        v = Validator()
        v.check(populated_kg)  # no exception

    def test_add_returns_self(self):
        v = Validator()
        result = v.add(requires_tag("concept"))
        assert result is v

    def test_chaining(self):
        v = Validator().add(requires_tag("concept")).add(requires_field("concept", "description"))
        assert len(v._rules) == 2


class TestRequiresField:
    def test_passes(self, populated_kg):
        v = Validator().add(requires_field("concept", "description"))
        assert v.validate(populated_kg) == []

    def test_fails(self, kg):
        kg.write("item", "---\ntype: concept\n---\nNo description.")
        v = Validator().add(requires_field("concept", "description"))
        errors = v.validate(kg)
        assert len(errors) == 1
        assert errors[0].node == "item"
        assert errors[0].rule == "requires_field"
        assert "description" in errors[0].message

    def test_all_types(self, kg):
        kg.touch("bare", "no frontmatter")
        v = Validator().add(requires_field(None, "type"))
        errors = v.validate(kg)
        assert len(errors) == 1
        assert errors[0].node == "bare"


class TestRequiresTag:
    def test_passes(self, populated_kg):
        v = Validator().add(requires_tag("concept"))
        assert v.validate(populated_kg) == []

    def test_fails(self, kg):
        kg.write("item", "---\ntype: concept\n---\nNo tags.")
        v = Validator().add(requires_tag("concept"))
        errors = v.validate(kg)
        assert len(errors) == 1
        assert "tag" in errors[0].message

    def test_empty_tags_fails(self, kg):
        kg.write("item", "---\ntype: concept\ntags: []\n---\nEmpty tags.")
        v = Validator().add(requires_tag("concept"))
        errors = v.validate(kg)
        assert len(errors) == 1


class TestRequiresLink:
    def test_passes(self, populated_kg):
        v = Validator().add(requires_link("concept"))
        assert v.validate(populated_kg) == []

    def test_fails_no_links(self, kg):
        kg.write("island", "---\ntype: concept\n---\nNo links.")
        v = Validator().add(requires_link("concept"))
        errors = v.validate(kg)
        assert len(errors) == 1
        assert "outgoing link" in errors[0].message

    def test_target_type_passes(self, populated_kg):
        v = Validator().add(requires_link("person", target_type="concept"))
        assert v.validate(populated_kg) == []

    def test_target_type_fails(self, kg):
        kg.write("a", "---\ntype: concept\n---\nLinks to [[b]].")
        kg.write("b", "---\ntype: concept\n---\nAnother concept.")
        v = Validator().add(requires_link("concept", target_type="person"))
        errors = v.validate(kg)
        assert len(errors) == 2
        assert all("person" in e.message for e in errors)


class TestNoOrphans:
    def test_passes(self, populated_kg):
        v = Validator().add(no_orphans("concept"))
        assert v.validate(populated_kg) == []

    def test_fails(self, kg):
        kg.touch("lonely", "alone")
        v = Validator().add(no_orphans())
        errors = v.validate(kg)
        assert len(errors) == 1
        assert errors[0].node == "lonely"
        assert "no incoming or outgoing" in errors[0].message


class TestCustom:
    def test_passes(self, populated_kg):
        v = Validator().add(custom("concept", "has_body", lambda kg, n, m: None))
        assert v.validate(populated_kg) == []

    def test_fails(self, kg):
        kg.write("empty", "---\ntype: concept\n---\n")
        v = Validator().add(custom(
            "concept", "has_body",
            lambda kg, n, m: "body is empty" if not kg.body(n).strip() else None,
        ))
        errors = v.validate(kg)
        assert len(errors) == 1
        assert errors[0].rule == "has_body"

    def test_all_types(self, populated_kg):
        v = Validator().add(custom(
            None, "name_length",
            lambda kg, n, m: "name too short" if len(n) < 3 else None,
        ))
        errors = v.validate(populated_kg)
        assert len(errors) == 2  # "sa" and "at"


class TestValidationError:
    def test_check_raises(self, kg):
        kg.touch("bare", "no frontmatter")
        v = Validator().add(requires_tag(None))
        with pytest.raises(ValidationError) as exc_info:
            v.check(kg)
        assert len(exc_info.value.violations) == 1
        assert "1 violation" in str(exc_info.value)

    def test_multiple_violations(self, kg):
        kg.write("a", "---\ntype: concept\n---\nNo tags or description.")
        v = Validator()
        v.add(requires_tag("concept"))
        v.add(requires_field("concept", "description"))
        with pytest.raises(ValidationError) as exc_info:
            v.check(kg)
        assert len(exc_info.value.violations) == 2


class TestFreezeSchema:
    def test_passes_with_matching_fields(self, kg):
        kg.write("c1", "---\ntype: concept\ndescription: OK\ntags: [x]\n---\nBody.")
        v = Validator().add(freeze_schema("concept", ["description", "tags"]))
        assert v.validate(kg) == []

    def test_passes_with_subset(self, kg):
        kg.write("c1", "---\ntype: concept\ndescription: OK\n---\nBody.")
        v = Validator().add(freeze_schema("concept", ["description", "tags"]))
        assert v.validate(kg) == []

    def test_fails_on_extra_fields(self, kg):
        kg.write("c1", "---\ntype: concept\ndescription: OK\nsecret: oops\n---\nBody.")
        v = Validator().add(freeze_schema("concept", ["description"]))
        errors = v.validate(kg)
        assert len(errors) == 1
        assert errors[0].node == "c1"
        assert errors[0].rule == "freeze_schema"
        assert "secret" in errors[0].message

    def test_type_field_always_allowed(self, kg):
        kg.write("c1", "---\ntype: concept\n---\nBody.")
        v = Validator().add(freeze_schema("concept", []))
        assert v.validate(kg) == []

    def test_multiple_extra_fields(self, kg):
        kg.write("c1", "---\ntype: concept\nalpha: 1\nbeta: 2\n---\nBody.")
        v = Validator().add(freeze_schema("concept", []))
        errors = v.validate(kg)
        assert len(errors) == 1
        assert "alpha" in errors[0].message
        assert "beta" in errors[0].message

    def test_only_checks_target_type(self, kg):
        kg.write("c1", "---\ntype: concept\nextra: bad\n---\nBody.")
        kg.write("p1", "---\ntype: person\nextra: fine\n---\nBody.")
        v = Validator().add(freeze_schema("concept", []))
        errors = v.validate(kg)
        assert len(errors) == 1
        assert errors[0].node == "c1"

    def test_composable_with_other_constraints(self, kg):
        kg.write("c1", "---\ntype: concept\nextra: bad\n---\nBody.")
        v = Validator()
        v.add(freeze_schema("concept", ["description"]))
        v.add(requires_field("concept", "description"))
        errors = v.validate(kg)
        assert len(errors) == 2
        rules = {e.rule for e in errors}
        assert "freeze_schema" in rules
        assert "requires_field" in rules


class TestComposition:
    def test_multiple_rules(self, kg):
        kg.write("good", "---\ntype: concept\ndescription: OK\ntags: [x]\n---\nLinks to [[good2]].")
        kg.write("good2", "---\ntype: concept\ndescription: OK2\ntags: [x]\n---\nLinks to [[good]].")
        kg.write("bad", "---\ntype: concept\n---\nNo tags, no desc, no links.")

        v = Validator()
        v.add(requires_field("concept", "description"))
        v.add(requires_tag("concept"))
        v.add(requires_link("concept"))

        errors = v.validate(kg)
        bad_errors = [e for e in errors if e.node == "bad"]
        good_errors = [e for e in errors if e.node in ("good", "good2")]
        assert len(bad_errors) == 3
        assert len(good_errors) == 0

    def test_different_types(self, kg):
        kg.write("c1", "---\ntype: concept\ndescription: OK\n---\nBody.")
        kg.write("p1", "---\ntype: person\n---\nPerson.")

        v = Validator()
        v.add(requires_field("concept", "description"))
        v.add(requires_field("person", "role"))

        errors = v.validate(kg)
        assert len(errors) == 1
        assert errors[0].node == "p1"
        assert "role" in errors[0].message


class TestGatekeeper:
    """Test pre-write validator gatekeeper mode."""

    def test_structural_blocks_invalid_write(self, kg):
        """Structural constraint blocks invalid write, node doesn't persist."""
        v = Validator()
        v.add(requires_field("concept", "description"))
        kg.set_validator(v)

        with pytest.raises(ValidationError):
            kg.write("bad", "---\ntype: concept\n---\nNo description.")

        assert not kg.exists("bad")

    def test_valid_write_succeeds_with_validator(self, kg):
        """Valid write succeeds when validator is attached."""
        v = Validator()
        v.add(requires_field("concept", "description"))
        kg.set_validator(v)

        kg.write("good", "---\ntype: concept\ndescription: OK\n---\nBody.")
        assert kg.exists("good")
        assert kg.frontmatter("good")["description"] == "OK"

    def test_relational_not_checked_pre_write(self, kg):
        """Relational constraints (structural=False) NOT checked pre-write."""
        v = Validator()
        v.add(requires_link("concept"))  # structural=False
        kg.set_validator(v)

        # This should succeed even without links — relational rules aren't gatekeeper rules
        kg.write("island", "---\ntype: concept\n---\nNo links.")
        assert kg.exists("island")

    def test_clear_validator_restores_freeform(self, kg):
        """clear_validator restores freeform mode."""
        v = Validator()
        v.add(requires_field("concept", "description"))
        kg.set_validator(v)

        with pytest.raises(ValidationError):
            kg.write("bad", "---\ntype: concept\n---\nNo description.")

        kg.clear_validator()

        # Now the same write should succeed
        kg.write("bad", "---\ntype: concept\n---\nNo description.")
        assert kg.exists("bad")

    def test_no_validator_unconstrained(self, kg):
        """Without validator, writes are unconstrained."""
        kg.write("anything", "---\ntype: concept\n---\nNo description, no tags.")
        assert kg.exists("anything")

    def test_freeze_schema_gatekeeper(self, kg):
        """freeze_schema (structural=True) blocks extra fields pre-write."""
        v = Validator()
        v.add(freeze_schema("concept", ["description"]))
        kg.set_validator(v)

        with pytest.raises(ValidationError):
            kg.write("bad", "---\ntype: concept\nsecret: oops\n---\nBody.")
        assert not kg.exists("bad")

        kg.write("good", "---\ntype: concept\ndescription: OK\n---\nBody.")
        assert kg.exists("good")

    def test_requires_tag_gatekeeper(self, kg):
        """requires_tag (structural=True) blocks tagless writes pre-write."""
        v = Validator()
        v.add(requires_tag("concept"))
        kg.set_validator(v)

        with pytest.raises(ValidationError):
            kg.write("bad", "---\ntype: concept\n---\nNo tags.")
        assert not kg.exists("bad")

    def test_set_validator_returns_self(self, kg):
        v = Validator()
        result = kg.set_validator(v)
        assert result is kg

    def test_clear_validator_returns_self(self, kg):
        result = kg.clear_validator()
        assert result is kg
