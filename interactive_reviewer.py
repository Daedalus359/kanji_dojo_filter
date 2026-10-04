#!/usr/bin/env python3

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from quality_scorer import ScoringResult
from removal_decision import RemovalDecision, RemovalDecisionLog


def print_deck_header(deck_id: int | None, deck_name: str | None = None) -> None:
    """Print a formatted header for a deck review session."""
    print("\n" + "=" * 80)
    if deck_id is None:
        print("Reviewing entries with no assigned deck")
    else:
        name_part = f" - {deck_name}" if deck_name else ""
        print(f"Reviewing deck {deck_id}{name_part}")
    print("=" * 80)


def print_entry_for_review(
    entry_num: int,
    total_entries: int,
    score_result: ScoringResult,
    existing_decision: RemovalDecision | None = None,
) -> None:
    """Print a formatted entry candidate for user review."""
    print(f"\n[{entry_num}/{total_entries}] {score_result.expression} [{score_result.reading}]")
    print(f"  Score: {score_result.total_score:.3f}")

    if score_result.jpdb_rank is not None:
        print(f"  JPDBv2 Rank: {score_result.jpdb_rank}")
    else:
        print(f"  JPDBv2 Rank: not found")

    print(f"  JMDict Match: {score_result.has_jmdict_match}")
    if score_result.has_uk_tag:
        print(f"    - Usually kana-only (uk tag)")
    if score_result.forms_high_priority is not None:
        status = "high priority" if score_result.forms_high_priority else "not high priority"
        print(f"    - Forms table: {status}")

    if score_result.is_ambiguous_expression or score_result.is_ambiguous_reading:
        print(f"  Ambiguity:")
        if score_result.is_ambiguous_expression:
            print(f"    - Expression has multiple readings")
        if score_result.is_ambiguous_reading:
            print(f"    - Reading is shared by multiple expressions")

    if score_result.reasons:
        print(f"  Reasons for score:")
        for reason in score_result.reasons:
            print(f"    - {reason}")

    if existing_decision and existing_decision.decision != "undecided":
        print(
            f"  [Previously decided: {existing_decision.decision.upper()} on {existing_decision.timestamp}]"
        )
        if existing_decision.user_notes:
            print(f"  [Previous notes: {existing_decision.user_notes}]")


def prompt_user_decision(
    score_result: ScoringResult,
    existing_decision: RemovalDecision | None = None,
) -> tuple[str, str]:
    """Prompt the user to decide whether to keep or remove an entry.

    Returns:
        (decision, notes) where decision is 'keep' or 'remove'
    """
    prompt_text = (
        "[k]eep, [r]emove, [n]otes only, [s]kip, [q]uit: "
        if existing_decision is None or existing_decision.decision == "undecided"
        else "[k]eep, [r]emove, [c]lear, [s]kip, [q]uit: "
    )

    while True:
        try:
            answer = input(prompt_text).strip().lower()
        except (KeyboardInterrupt, EOFError):
            return "skip", ""

        if answer in {"k", "keep"}:
            return "keep", ""
        elif answer in {"r", "remove"}:
            return "remove", ""
        elif answer in {"n", "notes"}:
            notes = input("Enter notes (or blank to skip): ").strip()
            if existing_decision:
                return existing_decision.decision, notes
            else:
                print("No decision made yet. Please choose keep [k] or remove [r].")
        elif answer in {"c", "clear"}:
            return "undecided", ""
        elif answer in {"s", "skip"}:
            return "skip", ""
        elif answer in {"q", "quit"}:
            return "quit", ""
        else:
            print("Please enter k, r, n, s, or q.")


def review_deck_entries(
    deck_id: int | None,
    candidates: list[ScoringResult],
    existing_log: RemovalDecisionLog,
    deck_name: str | None = None,
) -> tuple[bool, RemovalDecisionLog]:
    """Interactively review entries in a single deck.

    Returns:
        (should_continue, updated_log)
        If should_continue is False, the user quit.
    """
    print_deck_header(deck_id, deck_name)

    # Filter to candidates with nonzero score
    candidates_with_score = [c for c in candidates if c.total_score > 0]

    if not candidates_with_score:
        print("No entries to review in this deck.")
        existing_log.mark_deck_completed(deck_id)
        return True, existing_log

    print(f"Found {len(candidates_with_score)} entries to review.")
    print()

    for idx, candidate in enumerate(candidates_with_score, start=1):
        existing_decision = existing_log.find_decision(
            candidate.expression, candidate.reading, deck_id
        )

        print_entry_for_review(idx, len(candidates_with_score), candidate, existing_decision)

        decision, notes = prompt_user_decision(candidate, existing_decision)

        if decision == "quit":
            print("\nReview cancelled. Progress saved.")
            return False, existing_log

        if decision == "skip":
            print("Skipped.")
            continue

        # Update the log
        removal_decision = RemovalDecision(
            expression=candidate.expression,
            reading=candidate.reading,
            deck_id=deck_id,
            decision=decision,
            score=candidate.total_score,
            reasons=candidate.reasons,
            user_notes=notes,
            timestamp=datetime.now().isoformat(),
        )
        existing_log.add_or_update_decision(removal_decision)

        if decision == "keep":
            print("→ Marked to keep.")
        elif decision == "remove":
            print("→ Marked for removal.")
        elif decision == "undecided":
            print("→ Cleared decision.")

    existing_log.mark_deck_completed(deck_id)
    return True, existing_log


def prompt_continue_deck(
    deck_id: int | None, deck_name: str | None = None, num_candidates: int = 0
) -> bool:
    """Ask the user if they want to review a specific deck.

    Returns:
        True if the user wants to proceed, False if they want to quit.
    """
    deck_label = deck_name if deck_name else f"Deck {deck_id}" if deck_id is not None else "unassigned entries"
    print(f"\nProceed to review {deck_label} ({num_candidates} candidates)? [y]es, [n]o, [q]uit: ")

    while True:
        try:
            answer = input("").strip().lower()
        except (KeyboardInterrupt, EOFError):
            return False

        if answer in {"y", "yes"}:
            return True
        elif answer in {"n", "no"}:
            return False
        elif answer in {"q", "quit"}:
            return False
        else:
            print("Please enter y, n, or q.")
