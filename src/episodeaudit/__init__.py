"""Evidence-aware evaluation audits; no inference of biological identity."""

from .manifest import AuditInputError, Manifest, load_manifest, manifest_from_rows, write_manifest
from .integrity import audit_integrity, audit_lineage
from .episodes import build_episodes
from .sampling import sample_indices
from .metrics import evaluate_predictions, load_predictions

__version__ = "1.0.0"
__all__ = ["AuditInputError", "Manifest", "load_manifest", "manifest_from_rows", "write_manifest", "audit_integrity", "audit_lineage", "build_episodes", "sample_indices", "evaluate_predictions", "load_predictions"]
