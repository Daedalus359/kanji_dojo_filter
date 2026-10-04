#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

DEFAULT_FREQUENCY_THRESHOLD = 10000


@dataclass
class ScoringWeights:
    """Configurable weights for the scoring system."""
    no_frequency_entry: float = 0.15
    above_frequency_threshold: float = 0.45
    no_jmdict_match: float = 0.35
    uk_tag_bonus: float = -0.15
    forms_not_high_priority: float = 0.20
    ambiguous_expression: float = 0.20
    ambiguous_reading: float = 0.20
    forms_table_penalty: float = 0.10


@dataclass
class ScoringResult:
    """Result of scoring a single deck entry."""
    expression: str
    reading: str
    total_score: float
    frequency_component: float
    jpdb_rank: int | None
    has_jmdict_match: bool
    has_uk_tag: bool
    forms_high_priority: bool | None
    is_ambiguous_expression: bool
    is_ambiguous_reading: bool
    component_scores: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["total_score"] = round(self.total_score, 4)
        payload["frequency_component"] = round(self.frequency_component, 4)
        payload["component_scores"] = {
            k: round(v, 4) for k, v in self.component_scores.items()
        }
        return payload


def build_frequency_component(
    freq_rank: int | None, threshold: int = DEFAULT_FREQUENCY_THRESHOLD
) -> float:
    """Score low-frequency items as more risky; top words contribute zero."""
    if freq_rank is None:
        return 0.0

    if freq_rank <= threshold:
        return 0.0

    return min(1.0, (freq_rank - threshold) / max(1, threshold))


def compute_score(
    jpdb_rank: int | None,
    has_jmdict_match: bool,
    has_uk_tag: bool,
    forms_high_priority: bool | None,
    is_ambiguous_expression: bool,
    is_ambiguous_reading: bool,
    weights: ScoringWeights | None = None,
    threshold: int = DEFAULT_FREQUENCY_THRESHOLD,
) -> ScoringResult:
    """Compute a composite score for a deck entry.

    Returns a ScoringResult with the total score, frequency component,
    per-component breakdowns, and reasoning.
    """
    if weights is None:
        weights = ScoringWeights()

    score = 0.0
    component_scores: dict[str, float] = {}
    reasons: list[str] = []

    # Frequency component
    frequency_component = build_frequency_component(jpdb_rank, threshold=threshold)

    if jpdb_rank is None:
        component_scores["no_frequency_entry"] = weights.no_frequency_entry
        score += weights.no_frequency_entry
        reasons.append("no JPDBv2 frequency entry")
    else:
        if jpdb_rank > threshold:
            freq_penalty = weights.above_frequency_threshold * frequency_component
            component_scores["above_frequency_threshold"] = freq_penalty
            score += freq_penalty
            reasons.append(
                f"JPDBv2 rank {jpdb_rank} exceeds the {threshold}-word threshold"
            )
        else:
            reasons.append(f"JPDBv2 rank {jpdb_rank} is within the top {threshold}")

    # JMDict match component
    if not has_jmdict_match:
        component_scores["no_jmdict_match"] = weights.no_jmdict_match
        score += weights.no_jmdict_match
        reasons.append("no JMdict match")
    else:
        if has_uk_tag:
            component_scores["uk_tag_bonus"] = weights.uk_tag_bonus
            score += weights.uk_tag_bonus
            reasons.append("JMdict marks this as usually kana-only")
        elif forms_high_priority is False:
            component_scores["forms_not_high_priority"] = weights.forms_not_high_priority
            score += weights.forms_not_high_priority
            reasons.append("JMdict entry exists but is not marked high priority")

    # Ambiguity components
    if is_ambiguous_expression:
        component_scores["ambiguous_expression"] = weights.ambiguous_expression
        score += weights.ambiguous_expression
        reasons.append("expression has multiple readings")

    if is_ambiguous_reading:
        component_scores["ambiguous_reading"] = weights.ambiguous_reading
        score += weights.ambiguous_reading
        reasons.append("reading is shared by multiple expressions")

    # Forms table component
    if forms_high_priority is False:
        component_scores["forms_table_penalty"] = weights.forms_table_penalty
        score += weights.forms_table_penalty
        reasons.append("forms table does not prefer this expression/reading pair")

    # Clamp to [0, 1]
    score = max(0.0, min(1.0, score))

    return ScoringResult(
        expression="",  # Will be set by caller
        reading="",  # Will be set by caller
        total_score=score,
        frequency_component=frequency_component,
        jpdb_rank=jpdb_rank,
        has_jmdict_match=has_jmdict_match,
        has_uk_tag=has_uk_tag,
        forms_high_priority=forms_high_priority,
        is_ambiguous_expression=is_ambiguous_expression,
        is_ambiguous_reading=is_ambiguous_reading,
        component_scores=component_scores,
        reasons=reasons,
    )
