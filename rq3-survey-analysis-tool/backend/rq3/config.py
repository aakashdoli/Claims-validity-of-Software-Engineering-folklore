"""Configuration loading.

Every tunable value in this tool lives in ``config.yaml`` at the repository
root. This module is the ONLY place that reads it, and no other module may
define a statistical constant of its own. The loaded config is serialised
verbatim into every run manifest so that a result set can always be matched
back to the settings that produced it.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"


class ConfigError(RuntimeError):
    """Raised when the config file is missing a value the pipeline needs."""


@dataclass(frozen=True)
class Config:
    """Thin, validated wrapper around the parsed YAML."""

    raw: dict[str, Any]
    path: Path

    # -- section accessors ---------------------------------------------------
    def section(self, name: str) -> dict[str, Any]:
        try:
            return self.raw[name]
        except KeyError as exc:  # pragma: no cover - guarded by validation
            raise ConfigError(f"config.yaml is missing section '{name}'") from exc

    def get(self, dotted: str) -> Any:
        """Fetch a nested value, e.g. ``cfg.get("belief.threshold")``."""
        node: Any = self.raw
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                raise ConfigError(f"config.yaml is missing key '{dotted}'")
            node = node[part]
        return node

    def resolve_path(self, dotted: str) -> Path:
        value = self.get(dotted)
        p = Path(value)
        return p if p.is_absolute() else (PROJECT_ROOT / p)

    # -- frequently used values ---------------------------------------------
    @property
    def likert_values(self) -> list[int]:
        lo = int(self.get("likert.min"))
        hi = int(self.get("likert.max"))
        return list(range(lo, hi + 1))

    @property
    def idk_code(self) -> int:
        return int(self.get("likert.idk_code"))

    @property
    def missing_code(self) -> int:
        return int(self.get("likert.missing_code"))

    @property
    def idk_dominance_threshold(self) -> float:
        """Share of the FULL sample above which a claim is IDK-dominant."""
        return float(self.get("belief.idk_dominance.threshold"))

    @property
    def majority_threshold(self) -> float:
        """Share of the DIRECTIONAL denominator a side must exceed."""
        return float(self.get("belief.majority.threshold"))

    @property
    def min_subgroup_size(self) -> int:
        return int(self.get("comparisons.min_subgroup_size"))

    @property
    def alpha(self) -> float:
        return float(self.get("comparisons.alpha"))

    def to_dict(self) -> dict[str, Any]:
        """Deep copy for embedding in manifests/exports."""
        return copy.deepcopy(self.raw)


_REQUIRED_KEYS = (
    "dataset.input_file",
    "dataset.claims_file",
    "dataset.evidence_file",
    "likert.min",
    "likert.max",
    "likert.idk_code",
    "likert.missing_code",
    "descriptives.bimodality.rule",
    "comparisons.min_subgroup_size",
    "comparisons.variables",
    "effect_size.thresholds.small",
    "correction.method",
    "belief.idk_dominance.threshold",
    "belief.majority.threshold",
    "belief.evidence_labels",
    "experience_split.variable",
    "experience_split.group_1",
    "experience_split.group_2",
    "quality.low_effort.max_distinct_values",
    "reporting.sampling_caveat",
)


def load_config(path: str | Path | None = None) -> Config:
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not cfg_path.exists():
        raise ConfigError(f"config file not found: {cfg_path}")
    with cfg_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ConfigError(f"config file did not parse to a mapping: {cfg_path}")
    cfg = Config(raw=raw, path=cfg_path)
    for key in _REQUIRED_KEYS:
        cfg.get(key)  # raises ConfigError with the offending key name
    if cfg.min_subgroup_size < 1:
        raise ConfigError("comparisons.min_subgroup_size must be >= 1")
    if not (0 < cfg.alpha < 1):
        raise ConfigError("comparisons.alpha must be strictly between 0 and 1")
    return cfg
