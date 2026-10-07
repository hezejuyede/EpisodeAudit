"""Matched sampling interventions and exposure accounting for all groups."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any, Iterable

import numpy as np

from .manifest import AuditInputError, Manifest, _group_kind_conflicts, group_key, membership_key


def _rank(values: np.ndarray) -> np.ndarray:
    """Average ranks, including ties; avoids an optional scipy dependency."""
    order = np.argsort(values, kind="stable")
    ranks = np.empty(len(values), dtype=float)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and values[order[end]] == values[order[start]]:
            end += 1
        ranks[order[start:end]] = (start + end - 1) / 2
        start = end
    return ranks


def _spearman(left: np.ndarray, right: np.ndarray) -> float | None:
    if len(left) < 2 or np.all(left == left[0]) or np.all(right == right[0]):
        return None
    return float(np.corrcoef(_rank(left), _rank(right))[0, 1])


def sample_indices(manifest: Manifest, n_draws: int, *, strategy: str = "image", seed: int = 0,
                   image_replace: bool = False, splits: Iterable[str] | None = None) -> dict[str, Any]:
    """Return indices into the original manifest, keeping the draw budget fixed.

    image: uniform without replacement by default, matching an epoch shuffle;
           image_replace=True enables uniform independent replacement draws.
    group: draw a provided group uniformly, then a member uniformly, with replacement.
    episode: same distribution as group, but requires group_kind='episode'.

    The expected exposure difference is an algebraic property of sampling,
    not an estimated biological effect or a new scientific principle.
    """
    if isinstance(n_draws, bool) or not isinstance(n_draws, (int, np.integer)) or n_draws < 0:
        raise AuditInputError("n_draws must be a nonnegative integer.")
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)) or seed < 0:
        raise AuditInputError("seed must be a nonnegative integer.")
    if strategy not in {"image", "group", "episode"}:
        raise AuditInputError("strategy must be image, group, or episode.")
    if not isinstance(image_replace, bool):
        raise AuditInputError("image_replace must be boolean.")
    if isinstance(splits, str):
        raise AuditInputError("splits must be a sequence of names, not a single string.")
    split_set = set(splits) if splits is not None else None
    if split_set is not None and (not split_set or any(not isinstance(s, str) or not s for s in split_set)):
        raise AuditInputError("splits must contain nonempty string names.")
    selected = [i for i, row in enumerate(manifest.rows) if split_set is None or row.get("split") in split_set]
    if not selected:
        raise AuditInputError("Sampling selection contains no records.")
    keys = [membership_key(manifest.rows[i]) for i in selected]
    if len(keys) != len(set(keys)):
        raise AuditInputError("Sampling requires unique collection/sample membership within the selection.")
    if _group_kind_conflicts(manifest.rows[i] for i in selected):
        raise AuditInputError("Conflicting group-kind metadata for one namespace/group ID; group exposure calculations are ambiguous.")
    missing = [i for i in selected if group_key(manifest.rows[i]) is None]
    members: dict[tuple, list[int]] = {}
    for i in selected:
        key = group_key(manifest.rows[i])
        if key is not None:
            members.setdefault(key, []).append(i)
    if strategy in {"group", "episode"} and missing:
        raise AuditInputError("Group-balanced sampling cannot infer missing group identifiers.")
    if strategy == "episode" and any(manifest.rows[i].get("group_kind") != "episode" for i in selected):
        raise AuditInputError("Episode-balanced sampling requires episode group_kind for every selected record; use group for other supplied groupings.")
    if strategy == "image" and not image_replace and n_draws > len(selected):
        raise AuditInputError("Image sampling without replacement cannot exceed the number of selected records.")
    rng = np.random.default_rng(int(seed))
    sorted_groups = sorted(members)
    if strategy == "image":
        if image_replace:
            chosen = rng.choice(np.asarray(selected), size=int(n_draws), replace=True)
        else:
            chosen = rng.permutation(np.asarray(selected))[:int(n_draws)]
    else:
        group_draws = rng.integers(0, len(sorted_groups), size=int(n_draws))
        chosen = np.empty(int(n_draws), dtype=np.int64)
        for position, code in enumerate(group_draws):
            candidates = members[sorted_groups[int(code)]]
            chosen[position] = candidates[int(rng.integers(0, len(candidates)))]
    counts = Counter(group_key(manifest.rows[int(i)]) for i in chosen)
    exposures = [{"key": list(key), "n_images": len(members[key]), "n_draws": counts[key]} for key in sorted_groups]
    exposure_array = np.asarray([r["n_draws"] for r in exposures], dtype=float)
    sizes = np.asarray([r["n_images"] for r in exposures], dtype=float)
    complete_groups = not missing
    mean = float(exposure_array.mean()) if len(exposure_array) else 0.0
    cv = float(exposure_array.std(ddof=0) / mean) if complete_groups and mean > 0 else None
    seen = int(np.count_nonzero(exposure_array))
    probability = [{"key": list(key),
                    "expected_draws": float(n_draws / len(members) if strategy in {"group", "episode"}
                                            else n_draws * len(members[key]) / len(selected))}
                   for key in sorted_groups]
    return {"schema_version": "1.0", "audit": "sampling", "strategy": strategy, "seed": int(seed),
            "n_selected": len(selected), "n_draws": int(n_draws), "replacement": strategy != "image" or image_replace,
            "splits": sorted(split_set) if split_set is not None else None,
            "indices": [int(i) for i in chosen],
            "selected_members": [list(membership_key(manifest.rows[int(i)])) for i in chosen],
            "group_evidence_status": "PASS" if complete_groups and all(manifest.rows[i].get("group_kind", "unknown") != "unknown" for i in selected) else "UNKNOWN",
            "group_exposures": exposures, "expected_group_exposures": probability,
            "n_missing_group_records": len(missing), "n_groups": len(members), "groups_seen": seen,
            "group_coverage": float(seen / len(members)) if complete_groups and members else None,
            "draw_count_cv": cv,
            "spearman_group_size_vs_draws": _spearman(sizes, exposure_array) if complete_groups else None,
            "limitation": "Every supplied group is counted, including zero-draw groups. Group evidence and biological identity remain separate."}
