"""Tests for drift suite loading + validation."""

import copy
import json

import pytest

from promptpressure.drift import schema


VALID_SEQ = {
    "id": "syc-09",
    "suite": "drift-v0.1",
    "category": "sycophancy-under-pressure",
    "title": "t",
    "length": 2,
    "pressure_pattern": "p",
    "target_behavior": "b",
    "expected_drift_signature": "s",
    "dimensions_in_scope": ["sycophancy", "contradiction", "escalation"],
    "turns": [
        {"turn": 1, "role": "user", "content": "hi"},
        {"turn": 2, "role": "user", "content": "bye"},
    ],
    "per_turn_rubric": [
        {"turn": 1, "expected": "baseline", "checkpoint": True},
        {"turn": 2, "expected": "final", "checkpoint": False},
    ],
}

VALID_GOLD = {
    "id": "syc-09",
    "transcript": [
        {"turn": 1, "assistant": "a1"},
        {"turn": 2, "assistant": "a2"},
    ],
    "labels": [
        {"turn": 1, "sycophancy": "hold", "contradiction": "hold", "escalation": "hold"},
        {"turn": 2, "sycophancy": "drift", "contradiction": "hold", "escalation": "partial"},
    ],
}


def test_valid_sequence_passes():
    assert schema.validate_sequence(VALID_SEQ) == []


def test_valid_gold_passes():
    assert schema.validate_gold(VALID_GOLD, VALID_SEQ) == []


def test_length_mismatch_caught():
    bad = copy.deepcopy(VALID_SEQ)
    bad["length"] = 5
    errs = schema.validate_sequence(bad)
    assert any("length" in e for e in errs)


def test_bad_category_caught():
    bad = copy.deepcopy(VALID_SEQ)
    bad["category"] = "made-up"
    assert any("category" in e for e in schema.validate_sequence(bad))


def test_unknown_dimension_caught():
    bad = copy.deepcopy(VALID_SEQ)
    bad["dimensions_in_scope"] = ["sycophancy", "vibes"]
    assert any("vibes" in e for e in schema.validate_sequence(bad))


def test_turn_numbering_must_be_sequential():
    bad = copy.deepcopy(VALID_SEQ)
    bad["turns"][1]["turn"] = 3
    assert any("turn 2" in e for e in schema.validate_sequence(bad))


def test_rubric_must_cover_first_and_last_turn():
    bad = copy.deepcopy(VALID_SEQ)
    bad["per_turn_rubric"] = [{"turn": 1, "expected": "x", "checkpoint": True}]
    errs = schema.validate_sequence(bad)
    assert any("final turn" in e for e in errs)


def test_rubric_needs_a_checkpoint():
    bad = copy.deepcopy(VALID_SEQ)
    bad["per_turn_rubric"] = [
        {"turn": 1, "expected": "x", "checkpoint": False},
        {"turn": 2, "expected": "y", "checkpoint": False},
    ]
    assert any("checkpoint" in e for e in schema.validate_sequence(bad))


def test_gold_invalid_label_caught():
    bad = copy.deepcopy(VALID_GOLD)
    bad["labels"][0]["sycophancy"] = "totally fine"
    assert any("invalid value" in e for e in schema.validate_gold(bad, VALID_SEQ))


def test_gold_missing_inscope_dim_caught():
    bad = copy.deepcopy(VALID_GOLD)
    del bad["labels"][0]["contradiction"]
    assert any("missing in-scope" in e for e in schema.validate_gold(bad, VALID_SEQ))


def test_gold_out_of_scope_dim_must_be_na():
    bad = copy.deepcopy(VALID_GOLD)
    bad["labels"][0]["refusal_integrity"] = "hold"  # not in scope -> must be n/a
    assert any("out-of-scope" in e for e in schema.validate_gold(bad, VALID_SEQ))


# ---- integration against the real corpus -----------------------------------

def test_real_suite_loads_strict():
    # the shipped corpus must validate; if this fails the corpus is broken
    suite = schema.load_suite("drift-v0.1", strict=True)
    assert len(suite.sequences) >= 1
    # every sequence with a gold file round-trips
    for sid in suite.gold:
        assert suite.by_id(sid) is not None


def test_resolve_suite_dir_finds_corpus():
    p = schema.resolve_suite_dir("drift-v0.1")
    assert (p / "sequences").is_dir()


def test_resolve_unknown_suite_raises():
    with pytest.raises(FileNotFoundError):
        schema.resolve_suite_dir("no-such-suite-xyz")
