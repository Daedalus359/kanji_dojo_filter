from __future__ import annotations

import json
import orjson

import pickle
import sys
import unicodedata
from pathlib import Path

from typing import Any

def load_frequency_data(file_path: str | Path) -> list[list[Any]]:
    """Load the JSON array from a file."""
    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError("The JSON root must be a list.")

    return data

def get_frequency_data_for(
    data: list[list[Any]],
    expression: str,
    reading: str,
) -> list[list[Any]]:
    """
    Return all entries whose:

    - top-level expression is `expression`
    - metadata reading is `reading`
    """
    matches = []

    for entry in data:
        if not isinstance(entry, list) or len(entry) < 3:
            continue

        top_level_expression = entry[0]
        metadata = entry[2]

        if not isinstance(metadata, dict):
            continue

        if (
            top_level_expression == expression
            and metadata.get("reading") == reading
        ):
            matches.append(entry)

    return matches

def copy_to_clipboard(text: str) -> None:
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")

    # Base64 contains no single quotes, so this is safe to embed here.
    powershell_command = (
        f"$bytes = [Convert]::FromBase64String('{encoded}'); "
        "$text = [Text.Encoding]::UTF8.GetString($bytes); "
        "Set-Clipboard -Value $text"
    )

    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-STA",
            "-Command",
            powershell_command,
        ],
        check=True,
    )

def normalize(value):
    """
    Normalize Unicode and remove surrounding whitespace.

    This helps ensure that visually identical Japanese strings compare
    consistently.
    """
    if value is None:
        return None

    return unicodedata.normalize("NFC", str(value)).strip()


def has_tag(tag_string, wanted_tag):
    """
    Test whether wanted_tag is a complete, space-separated tag.

    Examples:

        'n uk'     matches 'uk'
        'uk'       matches 'uk'
        'unknown'  does not match 'uk'
    """
    if not isinstance(tag_string, str):
        return False

    return wanted_tag in tag_string.split()


def load_uk_terms():
    """
    Read all term_bank_*.json files and return a set of:

        (expression, reading)

    pairs whose term tags include the complete 'uk' tag.
    """

    uk_terms = set()

    term_files = sorted(JMDICT_DIRECTORY.glob("term_bank_*.json"))

    if not term_files:
        raise FileNotFoundError(
            f"No term_bank_*.json files found in {JMDICT_DIRECTORY}"
        )

    for filename in term_files:
        print(f"Reading {filename}", file=sys.stderr)

        with filename.open("r", encoding="utf-8") as file:
            #records = json.load(file)
            records = orjson.loads(file.read())


        if not isinstance(records, list):
            raise ValueError(
                f"{filename} does not contain a top-level JSON array"
            )

        for record_number, record in enumerate(records, start=1):
            if not isinstance(record, list) or len(record) < 3:
                print(
                    f"Skipping malformed record {record_number} "
                    f"in {filename}",
                    file=sys.stderr,
                )
                continue

            # Yomitan term-bank records begin approximately as:
            #
            # [
            #   expression,
            #   reading,
            #   term_tags,
            #   rules,
            #   score,
            #   definitions,
            #   ...
            # ]
            expression = normalize(record[0])
            reading = normalize(record[1])
            term_tags = record[2]

            if (
                expression
                and reading
                and has_tag(term_tags, "uk")
            ):
                uk_terms.add((expression, reading))

    return uk_terms

def _source_signature(files: list[Path]) -> tuple[tuple[str, int, int], ...]:
    """Return enough metadata to detect changed source files."""
    return tuple(
        (str(path), path.stat().st_mtime_ns, path.stat().st_size)
        for path in files
    )


def load_term_records(
    jmdict_directory: Path,
    cache_path: Path | None = None,
):
    term_files = sorted(jmdict_directory.glob("term_bank_*.json"))

    if not term_files:
        raise FileNotFoundError(
            f"No term_bank_*.json files found in {jmdict_directory}"
        )

    if cache_path is None:
        cache_path = jmdict_directory / ".term_records.cache"

    signature = _source_signature(term_files)

    # Load the cache if it is still valid.
    if cache_path.exists():
        try:
            with cache_path.open("rb") as file:
                cached_signature, term_records = pickle.load(file)

            if cached_signature == signature:
                return term_records
        except (OSError, EOFError, pickle.UnpicklingError, ValueError):
            pass

    term_records = []

    for filename in term_files:
        print(f"Reading {filename}", file=sys.stderr)

        with filename.open("r", encoding="utf-8") as file:
            records = orjson.loads(file.read())

        if not isinstance(records, list):
            raise ValueError(
                f"{filename} does not contain a top-level JSON array"
            )

        for record_number, record in enumerate(records, start=1):
            if not isinstance(record, list) or len(record) < 3:
                print(
                    f"Skipping malformed record {record_number} in {filename}",
                    file=sys.stderr,
                )
                continue

            term_records.append({
                "file": filename,
                "record_number": record_number,
                "record": record,
            })

    # Write atomically so an interrupted write does not corrupt the cache.
    temporary_cache = cache_path.with_suffix(".tmp")

    with temporary_cache.open("wb") as file:
        pickle.dump((signature, term_records), file, protocol=pickle.HIGHEST_PROTOCOL)

    temporary_cache.replace(cache_path)

    return term_records


def load_tag_descriptions(jmdict_directory: Path):
    """
    Load tag descriptions from tag_bank_1.json.

    For example, this maps:

        uk -> word usually written using kana alone
    """

    filename = jmdict_directory / "tag_bank_1.json"

    if not filename.exists():
        raise FileNotFoundError(
            f"Tag bank not found: {filename}"
        )

    with filename.open("r", encoding="utf-8") as file:
        records = json.load(file)

    tag_descriptions = {}

    for record in records:
        if not isinstance(record, list) or len(record) < 1:
            continue

        tag_code = record[0]

        # In the supplied tag bank, the human-readable description is
        # normally the fourth element.
        description = ""
        if len(record) > 3 and isinstance(record[3], str):
            description = record[3]

        tag_descriptions[tag_code] = description

    return tag_descriptions


def find_term_records(
    term_records,
    expression,
    reading,
    partial=False,
):
    """
    Find JMdict records matching both an expression and a reading.

    With partial=False:
        record expression == expression
        AND
        record reading == reading

    With partial=True:
        record expression contains expression
        AND
        record reading contains reading
    """

    expression = normalize(expression)
    reading = normalize(reading)

    matches = []

    for item in term_records:
        record = item["record"]

        if len(record) < 2:
            continue

        record_expression = normalize(record[0])
        record_reading = normalize(record[1])

        if partial:
            expression_matches = expression in record_expression
            reading_matches = reading in record_reading
        else:
            expression_matches = record_expression == expression
            reading_matches = record_reading == reading

        # Both fields must match.
        if expression_matches and reading_matches:
            matches.append(item)

    return matches


def describe_tags(tag_string, tag_descriptions):
    """
    Expand a space-separated JMdict tag string into readable lines.
    """

    if not isinstance(tag_string, str) or not tag_string.strip():
        return "(none)"

    descriptions = []

    for tag in tag_string.split():
        description = tag_descriptions.get(tag)

        if description:
            descriptions.append(f"\t{tag} — {description}")
        else:
            descriptions.append(tag)

    return "\n".join(descriptions)


def format_term_record(item, tag_descriptions):
    """
    Format one term-bank record for terminal display.
    """

    record = item["record"]

    expression = record[0] if len(record) > 0 else ""
    reading = record[1] if len(record) > 1 else ""
    term_tags = record[2] if len(record) > 2 else ""
    rules = record[3] if len(record) > 3 else ""
    score = record[4] if len(record) > 4 else ""
    definitions = record[5] if len(record) > 5 else None #might not be correct?
    sequence = record[6] if len(record) > 6 else ""
    additional_tags = record[7:] if len(record) > 7 else []

    output = []

    #output.append(f"Source file:       {item['file']}")
    #output.append(f"Record number:     {item['record_number']}")
    output.append(f"Expression [reading]: {expression} [{reading}]")
    #output.append(f"Reading:           {reading}")
    #output.append(f"Term tags:         {term_tags}")
    output.append("Tags with descriptions:")
    output.append(describe_tags(term_tags, tag_descriptions))
    #output.append(f"Rules:             {rules}")
    #output.append(f"Score:             {score}")
    #output.append(f"Sequence/source ID: {sequence}")

    if additional_tags:
        output.append(
            "Additional fields:\n"
            + json.dumps(
                additional_tags,
                ensure_ascii=False,
                indent=2,
            )
        )

    

    # output.append(
    #     "Definitions:\n"
    #     + json.dumps(
    #         definitions,
    #         ensure_ascii=False,
    #         indent=2,
    #     )
    # )

    #output.append("Definitions:\n")
    # try:
    #     for definition in definitions[0]['content']['content']:
    #         output.append("\t" + definition['content'] + "\n")
    # except:
    #     output.append(definitions)

    return "\n".join(output)


def records_as_json(matches):
    """
    Return matching raw term-bank records as formatted JSON.

    This is useful for copying the complete JMdict data to the clipboard.
    """

    return json.dumps(
        [item["record"] for item in matches],
        ensure_ascii=False,
        indent=2,
    )