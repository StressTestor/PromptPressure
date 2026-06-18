"""Load + validate the drift suite: sequences and gold labels.

A *suite* lives in a directory (default ``corpus/drift-v0.1/``) with:

    sequences/<id>.json   -- the pressure conversation + per-turn rubric
    gold/<id>.json        -- a reference transcript + per-turn human labels

Both file kinds are validated against the dimension vocabulary in
``dimensions`` so a typo fails at load time, not three steps into
calibration. Validation is intentionally strict: garbage in a credibility
artifact is worse than a crash.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from promptpressure.drift.dimensions import (
    DIMENSION_KEYS,
    LEVELS,
    NA,
    is_valid_label,
    normalize_label,
)

CATEGORIES: tuple[str, ...] = (
    "sycophancy-under-pressure",
    "persona-stability",
    "refusal-boundary-relaxation",
)

_REQUIRED_SEQ_KEYS = {
    "id",
    "category",
    "length",
    "pressure_pattern",
    "target_behavior",
    "expected_drift_signature",
    "dimensions_in_scope",
    "turns",
    "per_turn_rubric",
}


def validate_sequence(seq: dict) -> list[str]:
    """Return a list of validation errors for one sequence (empty == valid)."""
    errs: list[str] = []
    sid = seq.get("id", "<no id>")

    missing = _REQUIRED_SEQ_KEYS - seq.keys()
    if missing:
        errs.append(f"{sid}: missing keys {sorted(missing)}")

    if seq.get("category") not in CATEGORIES:
        errs.append(f"{sid}: category {seq.get('category')!r} not in {CATEGORIES}")

    scope = seq.get("dimensions_in_scope") or []
    if not scope:
        errs.append(f"{sid}: dimensions_in_scope must be non-empty")
    for d in scope:
        if d not in DIMENSION_KEYS:
            errs.append(f"{sid}: dimension {d!r} not a known dimension")

    turns = seq.get("turns") or []
    if not turns:
        errs.append(f"{sid}: turns must be non-empty")
    for i, t in enumerate(turns, 1):
        if not isinstance(t, dict) or t.get("role") != "user":
            errs.append(f"{sid}: turn {i} must be a dict with role 'user'")
        elif not str(t.get("content", "")).strip():
            errs.append(f"{sid}: turn {i} content must be non-empty")
        if t.get("turn") != i:
            errs.append(f"{sid}: turn {i} has turn number {t.get('turn')}, expected {i}")

    length = seq.get("length")
    if length != len(turns):
        errs.append(f"{sid}: length {length} != number of turns {len(turns)}")

    # rubric turns must reference real turn numbers and have at least one checkpoint
    rubric = seq.get("per_turn_rubric") or []
    rubric_turns = {r.get("turn") for r in rubric}
    for r in rubric:
        if r.get("turn") not in range(1, len(turns) + 1):
            errs.append(f"{sid}: rubric references turn {r.get('turn')} out of range")
        if not str(r.get("expected", "")).strip():
            errs.append(f"{sid}: rubric turn {r.get('turn')} missing 'expected'")
    if not any(r.get("checkpoint") for r in rubric):
        errs.append(f"{sid}: per_turn_rubric needs at least one checkpoint turn")
    if 1 not in rubric_turns:
        errs.append(f"{sid}: per_turn_rubric must cover turn 1 (baseline)")
    if len(turns) not in rubric_turns:
        errs.append(f"{sid}: per_turn_rubric must cover the final turn")

    return errs


def validate_gold(gold: dict, seq: dict | None = None) -> list[str]:
    """Validate a gold-label file, optionally cross-checked against its sequence."""
    errs: list[str] = []
    gid = gold.get("id", "<no id>")

    for key in ("id", "transcript", "labels"):
        if key not in gold:
            errs.append(f"gold {gid}: missing key {key!r}")

    transcript = gold.get("transcript") or []
    labels = gold.get("labels") or []
    scope = set(seq.get("dimensions_in_scope", DIMENSION_KEYS)) if seq else set(DIMENSION_KEYS)

    n_turns = len(seq.get("turns", [])) if seq else len(transcript)
    if seq and len(transcript) != n_turns:
        errs.append(f"gold {gid}: transcript has {len(transcript)} turns, sequence has {n_turns}")
    if seq and len(labels) != n_turns:
        errs.append(f"gold {gid}: labels cover {len(labels)} turns, sequence has {n_turns}")

    for i, tr in enumerate(transcript, 1):
        if tr.get("turn") != i:
            errs.append(f"gold {gid}: transcript turn {i} numbered {tr.get('turn')}")
        if not str(tr.get("assistant", "")).strip():
            errs.append(f"gold {gid}: transcript turn {i} has empty assistant text")

    for i, lab in enumerate(labels, 1):
        if lab.get("turn") != i:
            errs.append(f"gold {gid}: label turn {i} numbered {lab.get('turn')}")
        for dim in scope:
            val = lab.get(dim)
            if val is None:
                errs.append(f"gold {gid}: label turn {i} missing in-scope dimension {dim!r}")
                continue
            if not is_valid_label(normalize_label(val)):
                errs.append(f"gold {gid}: label turn {i} dimension {dim!r} invalid value {val!r}")
        # out-of-scope dimensions, if present, must be N/A
        for dim in DIMENSION_KEYS:
            if dim not in scope and dim in lab:
                if normalize_label(lab[dim]) != NA:
                    errs.append(
                        f"gold {gid}: label turn {i} out-of-scope dimension {dim!r} "
                        f"should be '{NA}', got {lab[dim]!r}"
                    )

    return errs


@dataclass
class Suite:
    """A loaded drift suite."""

    name: str
    root: Path
    sequences: list[dict] = field(default_factory=list)
    gold: dict[str, dict] = field(default_factory=dict)

    def by_id(self, seq_id: str) -> dict | None:
        for s in self.sequences:
            if s["id"] == seq_id:
                return s
        return None

    @property
    def categories(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {c: [] for c in CATEGORIES}
        for s in self.sequences:
            out.setdefault(s["category"], []).append(s["id"])
        return out


def resolve_suite_dir(suite: str, search_roots: list[str] | None = None) -> Path:
    """Find the directory for a named suite.

    Looks for ``corpus/<suite>`` under the provided roots (default: cwd and
    the repo root inferred from this file). Accepts an explicit path too.
    """
    candidate = Path(suite)
    if candidate.is_dir() and (candidate / "sequences").is_dir():
        return candidate

    roots = search_roots or [
        os.getcwd(),
        str(Path(__file__).resolve().parents[2]),  # repo root (…/promptpressure/drift -> repo)
    ]
    for root in roots:
        p = Path(root) / "corpus" / suite
        if (p / "sequences").is_dir():
            return p
    raise FileNotFoundError(
        f"could not locate suite {suite!r}; looked for corpus/{suite}/sequences under {roots}"
    )


def load_suite(suite: str, search_roots: list[str] | None = None, strict: bool = True) -> Suite:
    """Load and validate a suite by name or path.

    With ``strict=True`` (default) any validation error raises
    ``ValueError`` with all problems listed -- a corpus that does not
    validate must not silently produce calibration numbers.
    """
    root = resolve_suite_dir(suite, search_roots)
    seq_dir = root / "sequences"
    gold_dir = root / "gold"

    sequences: list[dict] = []
    for p in sorted(seq_dir.glob("*.json")):
        with open(p, encoding="utf-8") as f:
            sequences.append(json.load(f))

    gold: dict[str, dict] = {}
    if gold_dir.is_dir():
        for p in sorted(gold_dir.glob("*.json")):
            with open(p, encoding="utf-8") as f:
                g = json.load(f)
            gold[g["id"]] = g

    errors: list[str] = []
    seen_ids: set[str] = set()
    for seq in sequences:
        errors.extend(validate_sequence(seq))
        if seq.get("id") in seen_ids:
            errors.append(f"duplicate sequence id {seq.get('id')!r}")
        seen_ids.add(seq.get("id"))
    for sid, g in gold.items():
        errors.extend(validate_gold(g, _find(sequences, sid)))

    if errors and strict:
        raise ValueError(
            f"suite {suite!r} failed validation with {len(errors)} error(s):\n  "
            + "\n  ".join(errors)
        )

    s = Suite(name=root.name, root=root, sequences=sequences, gold=gold)
    s.validation_errors = errors  # type: ignore[attr-defined]
    return s


def _find(sequences: list[dict], sid: str) -> dict | None:
    for s in sequences:
        if s.get("id") == sid:
            return s
    return None
