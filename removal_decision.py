#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal
from constants import JPDB_CUTOFF_FREQ_RANK


@dataclass
class RemovalDecision:
    """A single user decision about whether to remove an entry."""

    expression: str
    reading: str
    deck_id: int | None
    decision: Literal["keep", "remove", "undecided"]
    score: float
    reasons: list[str] = field(default_factory=list)
    user_notes: str = ""
    timestamp: str = ""  # ISO 8601 format

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RemovalDecisionLog:
    """A serializable log of all user decisions across decks."""

    decisions: list[RemovalDecision] = field(default_factory=list)
    completed_decks: set[int | None] = field(default_factory=set)
    frequency_threshold: int = JPDB_CUTOFF_FREQ_RANK
    jmdict_directory: str = ""
    frequency_data_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "decisions": [d.to_dict() for d in self.decisions],
            "completed_decks": sorted(list(self.completed_decks)),
            "frequency_threshold": self.frequency_threshold,
            "jmdict_directory": self.jmdict_directory,
            "frequency_data_path": self.frequency_data_path,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> RemovalDecisionLog:
        log = RemovalDecisionLog(
            frequency_threshold=data.get("frequency_threshold", JPDB_CUTOFF_FREQ_RANK),
            jmdict_directory=data.get("jmdict_directory", ""),
            frequency_data_path=data.get("frequency_data_path", ""),
        )
        log.completed_decks = set(data.get("completed_decks", []))
        log.decisions = [
            RemovalDecision(**d) for d in data.get("decisions", [])
        ]
        return log

    def find_decision(
        self, expression: str, reading: str, deck_id: int | None
    ) -> RemovalDecision | None:
        """Look up an existing decision for this entry."""
        for decision in self.decisions:
            if (
                decision.expression == expression
                and decision.reading == reading
                and decision.deck_id == deck_id
            ):
                return decision
        return None

    def add_or_update_decision(self, decision: RemovalDecision) -> None:
        """Add or update a decision."""
        existing = self.find_decision(
            decision.expression, decision.reading, decision.deck_id
        )
        if existing:
            self.decisions.remove(existing)
        self.decisions.append(decision)

    def mark_deck_completed(self, deck_id: int | None) -> None:
        """Mark a deck as having been reviewed."""
        self.completed_decks.add(deck_id)
