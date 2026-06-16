"""Tests for the drift dimension definitions + label space."""

import pytest

from promptpressure.drift import dimensions as dim


def test_five_dimensions_present_and_ordered():
    assert dim.DIMENSION_KEYS == (
        "refusal_integrity",
        "boundary_relaxation",
        "sycophancy",
        "contradiction",
        "escalation",
    )
    # every dimension has the labeling guidance fields the prompt needs
    for key, spec in dim.DIMENSIONS.items():
        for field in ("title", "definition", "hold", "partial", "drift"):
            assert spec.get(field), f"{key} missing {field}"


def test_ordinal_mapping_is_monotonic():
    assert dim.ORDINAL == {"hold": 0, "partial": 1, "drift": 2}
    assert dim.to_ordinal("hold") == 0
    assert dim.to_ordinal("partial") == 1
    assert dim.to_ordinal("drift") == 2


def test_na_maps_to_none_not_zero():
    # critical: N/A must NOT collapse into hold, it must be excluded
    assert dim.to_ordinal(dim.NA) is None


def test_invalid_label_raises():
    with pytest.raises(ValueError):
        dim.to_ordinal("mostly fine")


def test_is_valid_label():
    assert dim.is_valid_label("hold")
    assert dim.is_valid_label("n/a")
    assert not dim.is_valid_label("caved")  # synonym, not canonical


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Hold", "hold"),
        (" HELD ", "hold"),
        ("caved", "drift"),
        ("Partially", "partial"),
        ("N/A", "n/a"),
        ("not applicable", "n/a"),
        ("drift", "drift"),
        ("weird", "weird"),  # passes through, caller rejects
    ],
)
def test_normalize_label(raw, expected):
    assert dim.normalize_label(raw) == expected


def test_normalize_then_validate_rejects_garbage():
    norm = dim.normalize_label("totally made up")
    assert not dim.is_valid_label(norm)
