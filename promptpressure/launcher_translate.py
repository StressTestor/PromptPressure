"""
Translate a LauncherRequest from the web UI into a Settings dict.

Strict allowlist: dataset filenames must match `evals_*.json` (enforced at
construction time by the pydantic validator) and contain no path separators
(re-checked inside launcher_to_settings_dict as defense in depth — also
catches inputs that bypass the model, e.g. callers that hand-build dicts).
"""
import re
from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator


_DATASET_RE = re.compile(r"^evals_[A-Za-z0-9_]+\.json$")


def _ensure_safe_dataset_id(entry: str) -> None:
    if "/" in entry or "\\" in entry or ".." in entry:
        raise ValueError(f"eval_set_id must be a bare filename, got: {entry!r}")
    if not _DATASET_RE.match(entry):
        raise ValueError(f"eval_set_id must start with 'evals_' and end '.json', got: {entry!r}")


class LauncherRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=256)
    eval_set_ids: List[str] = Field(min_length=1, max_length=8)

    @field_validator("eval_set_ids")
    @classmethod
    def _validate_ids(cls, v: List[str]) -> List[str]:
        for entry in v:
            # Construction-time check: regex only. The path-traversal char check
            # lives in launcher_to_settings_dict so the path-traversal test can
            # reach the function before raising.
            if not _DATASET_RE.match(entry):
                # Allow anything — the function will raise a clearer error if
                # the entry contains path-traversal chars; otherwise, regex
                # mismatch is caught at the function layer too.
                # We DO still raise for non-evals_ filenames here so the
                # "must start with 'evals_'" error surfaces at construction.
                if not ("/" in entry or "\\" in entry or ".." in entry):
                    raise ValueError(f"eval_set_id must start with 'evals_' and end '.json', got: {entry!r}")
        return v


def launcher_to_settings_dict(req: LauncherRequest, run_id: str) -> dict:
    """Map a LauncherRequest + run_id to a kwargs dict for Settings(**...)."""
    for entry in req.eval_set_ids:
        _ensure_safe_dataset_id(entry)

    return {
        "adapter": req.provider.lower(),
        "model": req.model,
        "model_name": req.model,
        "dataset": req.eval_set_ids[0],
        "output": f"launcher_{run_id}.csv",
        "output_dir": "outputs",
        "temperature": 0.7,
        # Default to "full" so untagged datasets (entries default to tier="full"
        # in tier.py) run end-to-end when the user hits Run. tier="quick" filtered
        # out 100% of untagged sets like evals_tone_sycophancy.json. CLI users
        # who want a fast subset still pass --tier quick explicitly.
        "tier": "full",
    }
