#!/usr/bin/env python3

from __future__ import annotations

import csv
from dataclasses import dataclass
import json
from enum import Enum
from itertools import groupby
from pathlib import Path
from typing import Any, ClassVar, Iterable, Literal, TypeAlias

from filter_lib import copy_to_clipboard

#clipboard stuff
import base64
import os
import subprocess

import pickle
from pprint import pprint


from quality_scorer import ScoringResult

from constants import JPDB_CUTOFF_FREQ_RANK, JPDB_RECOMMEND_DELAY_FREQ_RANK, CHANGE_TO_KANA_WORDS, CHANGE_TO_ANOTHER_KANJI_FORM, QUESTIONABLE_CHANGES, HAS_MULTIPLE_COMMON_ALT_READINGS, SAMPLE_WORDS, VERB_SAMPLES


class OutputFormat(str, Enum):
    TEXT = "text"
    JSON = "json"
    CSV = "csv"

def print_report(
    results: Iterable[ScoringResult],
    pair_set_with_rows,
    output_format: OutputFormat = OutputFormat.TEXT,
    output_file: Path | None = None,
    verbose: bool = False,
    summary: bool = True,

) -> None:
    """Generate and print a report of scoring results.

    Args:
        results: Iterable of ScoringResult objects (typically sorted by score).
        output_format: Format for the report (text, json, csv).
        output_file: If provided, write to this file instead of stdout.
        verbose: If True, include component breakdowns and reasons.
        summary: If True, include a summary section at the top.
    """
    results_list = list(results)

    if output_format == OutputFormat.JSON:
        _write_json_report(results_list, output_file)
    elif output_format == OutputFormat.CSV:
        _write_csv_report(results_list, output_file)
    else:  # TEXT
        _write_text_report(
            results_list, pair_set_with_rows, output_file, verbose=verbose, summary=summary
        )
        # _write_text_report(
        #     results_list, output_file, verbose=verbose, summary=summary
        # )

@dataclass(frozen=True)
class Keep:
    input_command: ClassVar[str] = ""
    action: Literal["Keep"] = "Keep"

@dataclass(frozen=True)
class Defer:
    input_command: ClassVar[str] = "d"
    action: Literal["Defer"] = "Defer"

@dataclass(frozen=True)
class Remove:
    input_command: ClassVar[str] = "r"
    action: Literal["Remove"] = "Remove"

@dataclass(frozen=True)
class UseKana:
    input_command: ClassVar[str] = "k"
    action: Literal["Use kana"] = "Use kana"

@dataclass(frozen=True)
class MoveDecks:
    input_command: ClassVar[str] = "m"
    action: Literal["Move decks"] = "Move decks"

@dataclass(frozen=True)
class SetEnglish:
    input_command: ClassVar[str] = "e"
    newdef: str
    action: Literal["Set English"] = "Set English"

@dataclass(frozen=True)
class ChangeSpelling:
    input_command: ClassVar[str] = "s"
    spelling: str
    action: Literal["Change spelling"] = "Change spelling"


ChangeDecision: TypeAlias = Keep | Defer | Remove | UseKana | MoveDecks | ChangeSpelling | SetEnglish

CYAN = "\033[36m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
RED = "\033[31m"
MAGENTA = "\033[35m"
RESET = "\033[0m"

def capture_change_decision_input(result, pair_set_with_rows) -> ChangeDecision:
    while True: #loop until input is understood
        decision_input = input(
            "Input one of the following:"
            f"\n\t{GREEN}{Keep.input_command}{RESET} to keep"
            f"\n\t{YELLOW}{Defer.input_command}{RESET} to defer"
            f"\n\t{RED}{Remove.input_command}{RESET} to remove"
            f"\n\t{MAGENTA}{MoveDecks.input_command}{RESET} to move to a later deck (for low frequency words)"
            f"\n\t{CYAN}{UseKana.input_command}{RESET} to use the kana form as the expression"
            f"\n\t{CYAN}{ChangeSpelling.input_command}{RESET} to change spelling"
            f"\n\t{CYAN}{SetEnglish.input_command}{RESET} to set English meaning"
            f"\n\tb for breakpoint()"
            "\n: "
        ).strip().lower()

        if decision_input == Remove.input_command:
            print(f"🔴 Marking for {RED}Removal{RESET}")
            return Remove()

        if decision_input == Defer.input_command:
            print("🟡 Marking for Deferred Review")
            return Defer()

        if decision_input == "": #Keep.input_command is "[Enter]", which the user does not actually type out
            print("🟢 Marking to Keep")
            return Keep()

        if decision_input == ChangeSpelling.input_command:
            spelling = input("Enter the new spelling: ")
            print("✏️ Marking for Spelling Change")
            return ChangeSpelling(spelling=spelling)

        if decision_input == SetEnglish.input_command:
            newdef = input("Enter the new definition: ")
            print("✏️ Marking for Definition Change")
            return SetEnglish(newdef=newdef)

        if decision_input == UseKana.input_command:
            return UseKana()

        if decision_input == MoveDecks.input_command:
            return MoveDecks()

        if decision_input == "b":
            breakpoint()
            continue
            # interact #brings more vars into scope
            # [rrow for (rexp, rrdg, rrow) in pair_set_with_rows if rrdg = result.reading]

        print(f"Did not understand input {decision_input!r}. Trying again.")

def strip_reading_from_meaning(meaning, reading):
    return "\n".join(
        line for line in meaning.splitlines()
        if reading not in line
    )


def get_change_decision(
    result: ScoringResult, 
    pair_set_with_rows, 
    #matching_row = None, 
    verbose: bool = False
    ) -> None:
    """Print a single ScoringResult in human-readable text format."""
    # print()
    # print("------------------------------------------------")
    # print(f"{result.expression} [{result.reading}]")

    matching_row = result.matching_row

    exp = result.expression
    rdg = result.reading
    er = (exp, rdg)

    r = result

    print()
    print("="*50)
    print(f"{result.expression} [{result.reading}] (id {matching_row[0]} in deck_id {matching_row[1]})")
    # print(f"\tid is {matching_row[0]}. deck_id is {matching_row[1]}")
    #print("meaning (in Kanji Dojo user DB):")
    print("Definition (KD db):\n\t", strip_reading_from_meaning(matching_row[4], r.reading))
    print("- "*15)



    # if matching_row is not None:
    #      print(f"\tid is {matching_row[0]}. deck_id is {matching_row[1]}")

    

    flagged = False

    if matching_row is None:
        print("No matching row passed to _print_text_result for", expression, value)
        return (result, Defer())
    else:
        if r.has_uk_tag:
            if r.expression == r.reading:
                pass
                #print("Entry already corresponds to uk tag!")
            else:
                print(f"{CYAN}(か){RESET} Result has at least one sense tagged {CYAN}uk{RESET} (suggest {CYAN}{UseKana.input_command}{RESET}. Compare definition to Yomitan:")
                #print(matching_row[4])
                #print(matching_row)
                flagged = True
        if r.jpdb_rank is not None:
            if r.jpdb_rank > JPDB_CUTOFF_FREQ_RANK:
                print(f"⚠️⚠️ JPDB ranking above threshold to recommend {RED}removal{RESET}: {r.jpdb_rank}")
                flagged = True
            elif r.jpdb_rank > JPDB_RECOMMEND_DELAY_FREQ_RANK:
                flagged = True
                print(f"⚠️ JPDB ranking above threshold to recommend {MAGENTA}deprioritization{RESET} (suggest {MAGENTA}{MoveDecks.input_command}{RESET}): {r.jpdb_rank}")
                flagged = True
        if not r.has_jmdict_match:
            print(f"❓ No JMDict match found!")
            flagged = True
        if r.j_y_redirect_tgt is not None:
            (j_y_redirect_exp, j_y_redirect_rdg) = r.j_y_redirect_tgt
            print(f"🚨 JY redirect {r.expression_maybe_kana}[{r.reading}] -> {j_y_redirect_exp}[{j_y_redirect_rdg}]")
        if not r.forms_high_priority:
            print(f"⚠️ Form considered not the highest priority {CYAN}form{reset}. Review JMDict entry in Yomitan.")
            flagged = True
        if r.j_y_irregular:
            print(f"🚨 Jitendex_Yomitan data reports this form as {CYAN}irregular!{reset}")
            flagged=True
        if r.is_ambiguous_expression:
            #print(matching_row)
            print(f"\t🛈 The following are Kanji Dojo entries matching this expression:")
            for (rexp, rrdg, rrow) in pair_set_with_rows:
                if r.expression == rexp and not rrow == matching_row:
                    print(f"\t| {rexp} [{rrdg}]", strip_reading_from_meaning(rrow[4], rrdg).strip(), f"(id {rrow[0]} in deck_id {rrow[1]})")
                    #print("\t\t", )
                    #print(f"\t\tid {rrow[0]} in deck_id {rrow[1]}")
            # print("\t⊥")

            # flagged = True
        if r.is_ambiguous_reading:
            print(f"\t🛈 The following expressions share a reading with {result.expression}[{result.reading}]:")
            for (rexp, rrdg, rrow) in pair_set_with_rows:
                if r.reading == rrdg and not rrow == matching_row:
                    print(f"\t| {rexp} [{rrdg}]")
            #flagged = True #not sure if this is enough to flag
        if er in CHANGE_TO_KANA_WORDS:
            print(er)
            print(rdg)
            print(f"🧠 Recommend {CYAN}changing the spelling{RESET} to {rdg} based on a matching entry in CHANGE_TO_KANA_WORDS.")
            flagged = True
        if er in CHANGE_TO_ANOTHER_KANJI_FORM:
            recommended_form = CHANGE_TO_ANOTHER_KANJI_FORM[er]
            print(f"🧠Recommend {CYAN}changing the spelling{RESET} to {recommended_form} based on a matching entry in CHANGE_TO_ANOTHER_KANJI_FORM")
            flagged = True
        if er in QUESTIONABLE_CHANGES:
            questionable_change = QUESTIONABLE_CHANGES[er]
            print(f"⚠️ This pair appears in {YELLOW}QUESTIONABLE_CHANGES{RESET} with the value {questionable_change}")
            flagged = True
        if er in HAS_MULTIPLE_COMMON_ALT_READINGS:
            readings = [r for (e, r) in HAS_MULTIPLE_COMMON_ALT_READINGS if e == exp]
            print("\tHAS_MULTIPLE_COMMON_ALT_READINGS lists the following common readings:")
            for reading in readings:
                print(f"\t| {reading}")
            flagged = True
        if er in SAMPLE_WORDS and er not in VERB_SAMPLES:
            print("\tThis pair appears in SAMPLE_WORDS. Give it an extra look to be safe.")
            flagged = True



    if not flagged:
        print(f"✅No issues detected. {GREEN}Auto-proceeding{RESET}.")#✅
        return (result, Keep())


    if exp:
        copy_to_clipboard(exp)#to see on Yomitan
    else:
        copy_to_clipboard(rdg)

    #if we are here, there was at least one issue for the user to think about
    decision = capture_change_decision_input(result, pair_set_with_rows)
    if isinstance(decision, ChangeSpelling):
        print(decision.action, decision.spelling)
    elif isinstance(decision, Keep):
        pass
    elif isinstance(decision, UseKana):
        print(f"Decision to set expression to {rdg}")
    else:
        print(decision.action)

    

    return (result, decision)

def _write_text_report(
    results: list[ExpressionInfo],
    pair_set_with_rows,
    output_file: Path | None = None,
    verbose: bool = False,
    summary: bool = True,
) -> None:
    """Write a human-readable text report."""
    output = open(output_file, "w", encoding="utf-8") if output_file else None

    def print_line(*args: Any, **kwargs: Any) -> None:
        print(*args, **kwargs, file=output)

    results_and_rows = []
    results_and_decisions = []

    # for r in results:
    #     if r.expression == "明日":
    #         print(r)
    #         breakpoint()


    try:
        if summary:
            uk_count = sum(1 for r in results if r.has_uk_tag)
            print_line(f"\tTotal entries with a uk tag to review: {uk_count}")

            rare_words_count = sum(1 for r in results if r.jpdb_rank is not None and r.jpdb_rank > JPDB_CUTOFF_FREQ_RANK)
            print(f"\tTotal entries with frequency rank above {JPDB_CUTOFF_FREQ_RANK}: {rare_words_count}")
            
            no_jmdict_match_ct = sum(1 for r in results if not r.has_jmdict_match)
            print(f"\tTotal entries with no match found in JMDict: {no_jmdict_match_ct}")
            
            low_priority_form_ct = sum(1 for r in results if not r.forms_high_priority)
            print(f"\tTotal entries considered a low-priority form: {low_priority_form_ct}")
            
            ambiguous_expression_ct = sum(1 for r in results if r.is_ambiguous_expression)
            print(f"\tTotal entries where the expression was amiguous: {ambiguous_expression_ct}")
            
            ambiguous_reading_ct = sum(1 for r in results if r.is_ambiguous_reading)
            print(f"\tTotal entries where the reading was shared by multiple expressions: {ambiguous_reading_ct}")
            
            # print("pair set with rows")
            # print(pair_set_with_rows)

            print_line()
        print_line()
        #print("Results considered low-priority:")
        # for result in results:
            # matching_row = None
            # for (expression, reading, row) in pair_set_with_rows:
            #     #print(expression, reading, row)
            #     if result.expression == expression and result.reading == reading:
            #         matching_row = row
            #         #print(matching_row)
            #         #breakpoint()
            #         break
            # results_and_rows.append((result, matching_row))
            # if (
            #     not result.forms_high_priority
            #     or result.has_uk_tag
            # ):
        # sorted_rrs = sorted(#results_and_rows:
        #     results_and_rows,
        #     key=lambda item: item[1][1],
        #     reverse=True
        # )

        sorted_results = sorted(
            results, 
            key=lambda item: (item.matching_row[1], item.expression), 
            #reverse=False
        )



        results_by_deck_id = {
            key: list(group)
            for key, group in groupby(
                sorted_results,
                key=lambda item: item.matching_row[1],
            )
        }

        for deck_id in results_by_deck_id:
            print(f"Number of entries with deck id {deck_id}: {len(results_by_deck_id[deck_id])}")
        #breakpoint()

        # for (result, matching_row) in sorted_rrs:
        #     print(result.expression)
        #     print(matching_row)
        
        for r in sorted_results:
            if r.expression == "ニ十日":
                print(r.matching_row)

        sample_results = [result for result in sorted_results if (result.expression, result.reading) in SAMPLE_WORDS and (result.expression, result.reading) not in VERB_SAMPLES]
        if False:
            print("⚠️⚠️⚠️WARNING: only iterating over matches to SAMPLE_WORDS due to hard-coded branch in report_generator.py.⚠️⚠️⚠️")
            sorted_results = sample_results

        
        total_results = len(sorted_results)
        results_processed = 0

        # for result in sorted_results:
        #     if result.expression == "音" and result.reading == "おん":
        #         pprint(result.expression, result.reading, result.row)
        # breakpoint()

        # for deck_id in results_by_deck_id:
        #     for result in results_by_deck_id[deck_id]:
        #         if result.expression == "音" and result.reading == "おん":
        #             print(result.expression, result.reading, result.matching_row)
        # breakpoint()

        for deck_id in results_by_deck_id:
            results_and_decisions_this_deck = []
            deck_results = results_by_deck_id[deck_id]
            
            deck_num_results = len(deck_results)
            pickle_path = Path(f"deck_{deck_id}_change_decisions.pkl")
            if pickle_path.exists():
                with pickle_path.open("rb") as f:
                    results_and_decisions_this_deck = pickle.load(f)
                    #results_and_decisions += results_and_decisions_this_deck
                print(f"💾 Loaded previously saved decisions for deck # {deck_id} from {pickle_path}.")
            else:
                print(f"No previously saved decisions found at {pickle_path}.")
                for (i, result) in enumerate(deck_results):
                    
                    print(f"{i}/{deck_num_results} for deck. {results_processed} / {total_results} of collection.")
                    if i % 10 == 0:
                        for (rd_result, decision) in results_and_decisions:
                            if not isinstance(decision, Keep):
                                print(rd_result.expression, rd_result.reading, "->", decision)
                    # if result.expression == "音" and result.reading == "おん":
                    #     print("ANOTHER ONE!!!")
                    #     print(i, deck_id, result.expression, result.reading)
                    #     breakpoint()
                    (result, change_decision) = get_change_decision(result, pair_set_with_rows, verbose=verbose)
                    results_and_decisions_this_deck.append((result, change_decision))
                    results_processed += 1

            results_and_decisions += results_and_decisions_this_deck
            print("=======================================================")
            print(f"Summary of decisions for deck {deck_id}:")
            keep_ct = 0
            for (result, decision) in results_and_decisions_this_deck:
                # print(decision)
                if not isinstance(decision, Keep):
                    print(f"{result.expression}[{result.reading}] ->", decision)
                else:
                    keep_ct += 1
            
            print(f"Keeping {keep_ct} entries / {deck_num_results} without modification.")
            
            #breakpoint()
            
            with open(pickle_path, "wb") as f:
                pickle.dump(results_and_decisions_this_deck, f)
                print(f"💾 Saved decisions for deck # {deck_id} to {pickle_path}.")
            print("Pause between decks.")
            proceed_decision = input("Press enter to proceed to next deck. Input x to exit: ")
            if proceed_decision == "":
                pass
            elif proceed_decision == "x":
                break
            else:
                print("Did not understand input.") 
                breakpoint()
            
            print("=======================================================")
            
        # breakpoint()
        # for (i, result) in enumerate(sorted_results):
        #     i += 1
        #     if i % 10 == 0:
        #         #print((i, result))
        #         print(f"{i}/{num_results}")
        #         print("Non-keep decisions so far:")
        #         for (result, decision) in results_and_decisions:
        #             if not isinstance(decision, Keep):
        #                 print(result.expression, result.reading, "->", decision)
        #     (result, change_decision) = get_change_decision(result, pair_set_with_rows, verbose=verbose)
        #     # change_decision = get_change_decision(result, verbose=verbose)
        #     results_and_decisions.append((result, change_decision))
        # #print("Results tagged uk for at least one non-archaic sense (compare against Kanji Dojo DB definition to decide:")

    finally:
        if output:
            output.close()


def _write_json_report(
    results: list[ScoringResult], output_file: Path | None = None
) -> None:
    """Write results as JSON."""
    data = [r.to_dict() for r in results]
    output = open(output_file, "w", encoding="utf-8") if output_file else None

    try:
        json.dump(
            data,
            output or __import__("sys").stdout,
            ensure_ascii=False,
            indent=2,
        )
    finally:
        if output:
            output.close()


def _write_csv_report(
    results: list[ScoringResult], output_file: Path | None = None
) -> None:
    """Write results as CSV."""
    output = open(output_file, "w", encoding="utf-8", newline="") if output_file else None

    try:
        fieldnames = [
            "expression",
            "reading",
            "total_score",
            "jpdb_rank",
            "has_jmdict_match",
            "has_uk_tag",
            "forms_high_priority",
            "is_ambiguous_expression",
            "is_ambiguous_reading",
            "reasons",
        ]
        writer = csv.DictWriter(output or __import__("sys").stdout, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            row = {
                "expression": result.expression,
                "reading": result.reading,
                "total_score": round(result.total_score, 4),
                "jpdb_rank": result.jpdb_rank or "",
                "has_jmdict_match": result.has_jmdict_match,
                "has_uk_tag": result.has_uk_tag,
                "forms_high_priority": result.forms_high_priority or "",
                "is_ambiguous_expression": result.is_ambiguous_expression,
                "is_ambiguous_reading": result.is_ambiguous_reading,
                "reasons": "; ".join(result.reasons),
            }
            writer.writerow(row)
    finally:
        if output:
            output.close()
